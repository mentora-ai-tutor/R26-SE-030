"""Tests for the per-request LLM choice (Gemini default vs pinned Ollama)."""
from __future__ import annotations

import asyncio
from typing import Any, Optional, Type

import pytest
from pydantic import BaseModel, ValidationError

from app.api.github_review_routes import ReviewTopFiveRequest
from app.services.github_review_service import normalize_llm_choice
from app.services.llm.base import LLMClient
from app.services.llm.router import LLMRouter, Task, TierSpec


class _Probe(BaseModel):
    ok: bool


class _RecordingProvider(LLMClient):
    """Fake provider that records calls and returns a schema-valid stub."""

    def __init__(self, name: str):
        self.name = name
        self.calls = 0

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
        self.calls += 1
        return {"ok": True}

    async def probe(self) -> bool:
        return True


def _router() -> tuple[LLMRouter, _RecordingProvider, _RecordingProvider]:
    gemini = _RecordingProvider("gemini")
    ollama = _RecordingProvider("ollama")
    tiers = {
        "tier0": TierSpec("tier0", gemini),
        "tier3": TierSpec("tier3", ollama),
    }
    return LLMRouter(tiers), gemini, ollama


def test_force_ollama_pins_to_tier3_only() -> None:
    router, gemini, ollama = _router()
    asyncio.run(
        router.generate_json(
            prompt="x", schema=_Probe, task=Task.REPO_REVIEW, force_provider="ollama"
        )
    )
    assert ollama.calls == 1
    assert gemini.calls == 0  # strict: Gemini is never touched


def test_default_uses_gemini_primary() -> None:
    router, gemini, ollama = _router()
    asyncio.run(
        router.generate_json(prompt="x", schema=_Probe, task=Task.REPO_REVIEW)
    )
    assert gemini.calls == 1
    assert ollama.calls == 0  # no fallback needed when primary succeeds


def test_force_ollama_raises_when_tier3_missing() -> None:
    from app.services.llm.base import LLMError

    gemini = _RecordingProvider("gemini")
    router = LLMRouter({"tier0": TierSpec("tier0", gemini)})  # no tier3
    with pytest.raises(LLMError):
        asyncio.run(
            router.generate_json(
                prompt="x", schema=_Probe, task=Task.REPO_REVIEW, force_provider="ollama"
            )
        )


@pytest.mark.parametrize(
    "value,expected",
    [
        ("gemini", "gemini"),
        ("ollama", "ollama"),
        ("OLLAMA", "ollama"),
        (" gemini ", "gemini"),
        (None, "gemini"),
        ("bogus", "gemini"),
    ],
)
def test_normalize_llm_choice(value: str | None, expected: str) -> None:
    assert normalize_llm_choice(value) == expected


def test_request_model_defaults_to_gemini() -> None:
    assert ReviewTopFiveRequest().llm == "gemini"
    assert ReviewTopFiveRequest(repos=["a/b"], llm="ollama").llm == "ollama"


def test_request_model_rejects_unknown_engine() -> None:
    with pytest.raises(ValidationError):
        ReviewTopFiveRequest(llm="gpt4")  # type: ignore[arg-type]
