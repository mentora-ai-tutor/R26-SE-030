"""Abstract base for LLM providers."""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Optional, Type
from pydantic import BaseModel


class LLMError(Exception):
    """Base for all LLM-layer errors."""


class LLMTransientError(LLMError):
    """Retryable: 429, 500, 503, network blip."""


class LLMPermanentError(LLMError):
    """Permanent: model not found, preview not enabled, invalid argument.
    Triggers tier demotion."""


class LLMAuthError(LLMError):
    """Auth misconfiguration. Bubble up — never silently fall through."""


class LLMSchemaError(LLMError):
    """Output failed Pydantic validation."""


class LLMClient(ABC):
    """Provider contract. Each tier implements this."""

    name: str  # e.g. "gemini-3.1-pro-preview"

    @abstractmethod
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
        """Generate a JSON object validating against `schema`.

        Raises:
            LLMTransientError: caller should retry or demote.
            LLMPermanentError: caller should demote.
            LLMAuthError:      caller should bubble up.
            LLMSchemaError:    output didn't validate.
        """
        ...

    @abstractmethod
    async def probe(self) -> bool:
        """Cheap call used at boot to verify the tier is reachable."""
        ...
