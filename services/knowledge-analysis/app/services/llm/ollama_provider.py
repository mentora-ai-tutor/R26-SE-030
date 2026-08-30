"""
Ollama provider — last-resort offline tier.

Wraps the existing OllamaClient so we don't duplicate transport code, and
adds JSON-mode + Pydantic validation on top.
"""
from __future__ import annotations
import json
import logging
import re
from typing import Any, Optional, Type

from pydantic import BaseModel, ValidationError

from app.services.llm.base import (
    LLMClient,
    LLMTransientError,
    LLMPermanentError,
    LLMSchemaError,
)
from app.services.llm import config as cfg
from app.services.ollama_client import OllamaClient

logger = logging.getLogger(__name__)

# Strip optional ```json fences, plus leading/trailing prose. Schema mode should
# avoid these, but keeping this parser makes older Ollama builds safer.
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


def _extract_json(text: str) -> str:
    m = _FENCE_RE.search(text)
    if m:
        return m.group(1).strip()
    # Find the outermost { ... } if the model added prose.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text.strip()


class OllamaProvider(LLMClient):
    def __init__(self, model_id: str = cfg.OLLAMA_MODEL):
        self.name = f"ollama:{model_id}"
        self._client = OllamaClient(base_url=cfg.OLLAMA_URL, model=model_id)

    async def generate_json(
        self,
        *,
        prompt: str,
        schema: Type[BaseModel],
        thinking: str = "medium",
        cached_content: Optional[str] = None,
        tools: Optional[list[Any]] = None,
        temperature: float = 0.4,
    ) -> dict[str, Any]:
        # Include the schema both in the prompt and in Ollama's structured output
        # format. The prompt helps older models; format enforces JSON shape.
        schema_str = json.dumps(schema.model_json_schema(), indent=2)
        full_prompt = (
            f"Return ONLY a JSON object that validates the schema below. "
            f"No prose, no markdown fences.\n\n"
            f"SCHEMA:\n{schema_str}\n\n"
            f"USER:\n{prompt}"
        )
        try:
            result = await self._client.generate(
                prompt=full_prompt,
                stream=False,
                temperature=temperature,
                response_format=schema.model_json_schema(),
            )
        except Exception as e:
            raise LLMTransientError(f"Ollama call failed: {e}") from e

        text = result.get("response", "")
        if not text:
            raise LLMTransientError("Empty response from Ollama")

        cleaned = _extract_json(text)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            raise LLMSchemaError(f"Ollama output is not JSON: {e}; head={cleaned[:200]!r}")

        try:
            schema.model_validate(data)
        except ValidationError as e:
            raise LLMSchemaError(str(e))

        return data

    async def probe(self) -> bool:
        from pydantic import BaseModel as _BM

        class _Probe(_BM):
            ok: bool

        try:
            await self.generate_json(
                prompt='Return JSON {"ok": true}.',
                schema=_Probe,
                temperature=0.0,
            )
            return True
        except Exception as e:
            logger.warning("Ollama probe failed: %s", e)
            return False
