from __future__ import annotations

import pytest

from app.services.github_review_service import normalize_llm_choice


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("gemini", "gemini"),
        ("ollama", "ollama"),
        ("OLLAMA", "ollama"),
        (" Ollama ", "ollama"),
        (None, "gemini"),
        ("", "gemini"),
        ("bogus-engine", "gemini"),
    ],
)
def test_normalize_llm_choice(value: str | None, expected: str) -> None:
    assert normalize_llm_choice(value) == expected