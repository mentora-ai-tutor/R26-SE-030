"""
Gemini provider via the Vertex AI path of `google-genai`.

Service-account auth is wired through GOOGLE_APPLICATION_CREDENTIALS — the
SDK reads it automatically. We never read the JSON ourselves.
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
    LLMAuthError,
    LLMSchemaError,
)
from app.services.llm import config as cfg

logger = logging.getLogger(__name__)

# Lazy import + lazy client so the module loads even when the SDK is missing
# (e.g. when LLM_PROVIDER=ollama in dev).
_genai = None
_types = None
_client = None

# Thinking controls are SDK-version dependent. Some `google-genai` builds expose
# `thinking_level`; the current Vertex SDK exposes `thinking_budget` instead.
# Match Gemini major version >= 3 so GA fallback calls stay conservative.
_THINKING_LEVEL_RE = re.compile(r"^gemini-(\d+)", re.IGNORECASE)
_THINKING_BUDGET_BY_LEVEL = {
    "minimal": 0,
    "low": 1024,
    "medium": 4096,
    "high": 8192,
}


def _supports_thinking_level(model_id: str) -> bool:
    m = _THINKING_LEVEL_RE.match(model_id or "")
    if not m:
        return False
    try:
        return int(m.group(1)) >= 3
    except (TypeError, ValueError):
        return False


def _build_http_options():
    """Return HttpOptions carrying a per-request timeout, if the SDK supports it.

    google-genai expresses HttpOptions.timeout in MILLISECONDS. Older builds
    (we pin only >=0.4.0) may lack the field, so we degrade gracefully and let
    the outer per-repo asyncio budget remain the only bound.
    """
    http_options_cls = getattr(_types, "HttpOptions", None)
    if http_options_cls is None:
        return None
    if "timeout" not in getattr(http_options_cls, "model_fields", {}):
        return None
    return http_options_cls(timeout=cfg.GEMINI_REQUEST_TIMEOUT_SECONDS * 1000)


def _build_thinking_config(model_id: str, thinking: str):
    """Return a ThinkingConfig compatible with the installed google-genai SDK."""
    if not thinking or not _supports_thinking_level(model_id):
        return None

    fields = getattr(_types.ThinkingConfig, "model_fields", {})
    if "thinking_level" in fields:
        return _types.ThinkingConfig(thinking_level=thinking)
    if "thinking_budget" in fields:
        budget = _THINKING_BUDGET_BY_LEVEL.get(thinking, -1)
        return _types.ThinkingConfig(thinking_budget=budget)

    logger.debug(
        "Skipping thinking=%s on %s; installed google-genai has no supported "
        "ThinkingConfig field",
        thinking,
        model_id,
    )
    return None


def _ensure_sdk() -> None:
    global _genai, _types
    if _genai is not None:
        return
    try:
        from google import genai as _g
        from google.genai import types as _t
    except ImportError as e:  # pragma: no cover
        raise LLMPermanentError(
            "google-genai SDK is not installed; pip install google-genai"
        ) from e
    _genai = _g
    _types = _t


def _ensure_client():
    global _client
    if _client is not None:
        return _client
    _ensure_sdk()
    try:
        _client = _genai.Client(
            vertexai=True,
            project=cfg.GCP_PROJECT,
            location=cfg.GCP_LOCATION,
        )
        logger.info(
            "Gemini client initialized: project=%s location=%s",
            cfg.GCP_PROJECT, cfg.GCP_LOCATION,
        )
    except Exception as e:
        raise LLMAuthError(f"Failed to init Vertex AI client: {e}") from e
    return _client


def _classify_error(exc: Exception) -> Exception:
    """Map SDK / HTTP exceptions to our typed errors.

    Order matters:
      1. Filesystem exceptions     -> AuthError (credentials misconfig)
      2. HTTP-shaped errors        -> Auth/Permanent/Transient by status code
      3. Bare "File ... not found" (no HTTP context) -> AuthError
      4. Unknown                   -> Transient (router gets one retry)
    """
    # 1. Filesystem-level exceptions are always config errors.
    if isinstance(exc, (FileNotFoundError, PermissionError, IsADirectoryError)):
        return LLMAuthError(f"Credentials file unreadable: {exc}")

    msg = str(exc)
    msg_l = msg.lower()
    code = getattr(exc, "code", None)
    status = getattr(exc, "status_code", None) or code

    # 2. HTTP-shaped errors. Inspect status codes and Google API error patterns
    #    BEFORE falling back to substring heuristics, so a 404 from Vertex
    #    ("Publisher Model ... was not found") doesn't get mis-classified as
    #    a credentials issue.
    is_http_404 = (
        status == 404
        or msg.startswith("404")
        or "publisher model" in msg_l           # Vertex-specific
        or "model not found" in msg_l
        or "does not have access to it" in msg_l
    )
    if is_http_404:
        return LLMPermanentError(msg)

    if status in (401, 403) or "permission_denied" in msg_l or "unauthenticated" in msg_l:
        return LLMAuthError(msg)
    if "invalid_argument" in msg_l or status == 400 or msg.startswith("400"):
        return LLMPermanentError(msg)
    if (
        status in (429, 500, 502, 503, 504)
        or msg.startswith(("429", "500", "502", "503", "504"))
        or "rate limit" in msg_l
        or "unavailable" in msg_l
        or "deadline" in msg_l
        or "timed out" in msg_l
        or "timeout" in msg_l
        or isinstance(exc, TimeoutError)
    ):
        return LLMTransientError(msg)

    # 3. Bare credentials-file message from google-auth (no HTTP context).
    #    Pattern: "File /path/to/sa.json was not found."
    if msg.startswith("File ") and ("was not found" in msg_l or "no such file" in msg_l):
        return LLMAuthError(msg)

    # 4. Unknown — treat as transient so the router gets one retry before demoting.
    return LLMTransientError(msg)


class GeminiProvider(LLMClient):
    def __init__(self, model_id: str):
        self.name = model_id
        self.model_id = model_id

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
        client = _ensure_client()

        # Build config. Only include knobs the model + installed SDK support.
        kwargs: dict[str, Any] = dict(
            response_mime_type="application/json",
            response_schema=schema.model_json_schema(),
            temperature=temperature,
        )
        thinking_config = _build_thinking_config(self.model_id, thinking)
        if thinking_config is not None:
            kwargs["thinking_config"] = thinking_config
        elif thinking:
            logger.debug(
                "Skipping thinking=%s on %s (not supported by this model/SDK)",
                thinking, self.model_id,
            )
        if cached_content:
            kwargs["cached_content"] = cached_content
        if tools:
            kwargs["tools"] = tools
        http_options = _build_http_options()
        if http_options is not None and "http_options" in getattr(
            _types.GenerateContentConfig, "model_fields", {}
        ):
            kwargs["http_options"] = http_options

        try:
            cfg_obj = _types.GenerateContentConfig(**kwargs)
            resp = await client.aio.models.generate_content(
                model=self.model_id,
                contents=prompt,
                config=cfg_obj,
            )
        except Exception as e:
            raise _classify_error(e) from e

        text = getattr(resp, "text", None) or ""
        if not text:
            # Some preview models return empty text when thinking is over budget.
            raise LLMTransientError("Empty response from model")

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise LLMSchemaError(f"Model output is not JSON: {e}; head={text[:200]!r}")

        # Validate against the Pydantic schema. We don't return the validated
        # object — we return the raw dict so callers can choose how to bind.
        try:
            schema.model_validate(data)
        except ValidationError as e:
            raise LLMSchemaError(str(e))

        return data

    async def probe(self) -> bool:
        """Tiny call used at startup to verify this tier is alive.

        Returns True on success, False on permanent unavailability.
        Raises LLMAuthError on auth misconfig (so we don't silently mask it).
        """
        from pydantic import BaseModel as _BM

        class _Probe(_BM):
            ok: bool

        try:
            await self.generate_json(
                prompt='Return JSON {"ok": true}.',
                schema=_Probe,
                thinking="minimal",
                temperature=0.0,
            )
            return True
        except LLMAuthError:
            # Always bubble — config issues should never look like dead tiers.
            raise
        except LLMPermanentError as e:
            logger.warning("Probe permanent failure on %s: %s", self.model_id, e)
            return False
        except LLMTransientError as e:
            # Re-classify in case a credentials-file error snuck through as
            # transient. Tight pattern only — must look like a filesystem
            # message ("File ... was not found"), not an HTTP 404 body.
            msg = str(e)
            if msg.startswith("File ") and ("was not found" in msg.lower()
                                            or "no such file" in msg.lower()):
                raise LLMAuthError(msg)
            logger.warning("Probe transient failure on %s: %s", self.model_id, e)
            return False
        except Exception as e:  # noqa: BLE001
            logger.warning("Probe unknown failure on %s: %s", self.model_id, e)
            return False
