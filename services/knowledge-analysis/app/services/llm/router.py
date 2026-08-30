"""
Tiered LLM router with retry + dead-tier caching.

Fallback chain (default order):
    0  gemini-3.1-pro-preview
    0t gemini-3.1-pro-preview-customtools  (only when tools= is passed)
    1  gemini-2.5-pro
    2  gemini-2.5-flash
    3  ollama:llama3

Per-task primary tier is mapped in TASK_TIER_MAP — we never start at tier 0
for trivially cheap work like question generation.
"""
from __future__ import annotations
import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Type

from pydantic import BaseModel

from app.services.llm.base import (
    LLMClient,
    LLMError,
    LLMTransientError,
    LLMPermanentError,
    LLMAuthError,
    LLMSchemaError,
)
from app.services.llm import config as cfg
from app.services.llm.gemini_provider import GeminiProvider
from app.services.llm.ollama_provider import OllamaProvider

logger = logging.getLogger(__name__)


class Task(str, Enum):
    """Logical workload — used to pick primary tier + thinking level."""
    REPO_REVIEW          = "repo_review"
    JAVA_LEVEL_INFER     = "java_level_infer"
    QUESTION_GEN         = "question_gen"
    SHORT_CODE_GRADE     = "short_code_grade"
    AGENTIC_TOOL_CALL    = "agentic_tool_call"
    CAREER_NARRATIVE     = "career_narrative"
    PROBE                = "probe"


@dataclass
class TierSpec:
    key: str                        # e.g. "tier0", "tier0t"
    provider: LLMClient
    supports_tools: bool = False    # can take a tools= list


@dataclass
class _DeadMarker:
    until: float = 0.0


# Task -> (primary tier key, thinking_level)
TASK_TIER_MAP: dict[Task, tuple[str, str]] = {
    Task.REPO_REVIEW:       ("tier0",  "high"),
    Task.JAVA_LEVEL_INFER:  ("tier0",  "medium"),
    Task.QUESTION_GEN:      ("tier2",  "low"),
    Task.SHORT_CODE_GRADE:  ("tier1",  "medium"),
    Task.AGENTIC_TOOL_CALL: ("tier0t", "high"),
    Task.CAREER_NARRATIVE:  ("tier2",  "low"),
    Task.PROBE:             ("tier0",  "minimal"),
}

# When the primary tier is dead/skipped, we walk this order:
DEMOTION_ORDER: list[str] = ["tier0", "tier0t", "tier1", "tier2", "tier3"]


class LLMRouter:
    def __init__(self, tiers: dict[str, TierSpec]):
        self.tiers = tiers
        self._dead: dict[str, _DeadMarker] = {k: _DeadMarker() for k in tiers}

    # ------------------------------------------------------------------ utils
    def _is_dead(self, key: str) -> bool:
        m = self._dead.get(key)
        return bool(m and m.until > time.monotonic())

    def _mark_dead(self, key: str, ttl: int = cfg.DEAD_TIER_TTL_SECONDS) -> None:
        self._dead[key].until = time.monotonic() + ttl
        logger.warning("Marking tier %s dead for %ds", key, ttl)

    def _walk(self, start_key: str, *, need_tools: bool = False) -> list[TierSpec]:
        """Return the ordered list of tiers to try, starting at `start_key`."""
        try:
            start = DEMOTION_ORDER.index(start_key)
        except ValueError:
            start = 0
        out: list[TierSpec] = []
        for k in DEMOTION_ORDER[start:]:
            spec = self.tiers.get(k)
            if not spec:
                continue
            if need_tools and not spec.supports_tools:
                # Skip tiers that can't carry the tool calls (only tier0t does).
                continue
            if self._is_dead(k):
                continue
            out.append(spec)
        return out

    # ----------------------------------------------------------------- public
    async def generate_json(
        self,
        *,
        prompt: str,
        schema: Type[BaseModel],
        task: Task,
        cached_content: Optional[str] = None,
        tools: Optional[list[Any]] = None,
        temperature: float = 0.4,
        thinking: Optional[str] = None,
        force_provider: Optional[str] = None,
    ) -> dict[str, Any]:
        """Run a JSON-mode generation against the tier chain for `task`.

        Walks the chain top-down. For each tier:
          - 1 retry on transient error
          - 1 schema-repair pass on schema error
          - on permanent or auth (auth bubbles): demote and continue.

        `force_provider` lets a caller pin the engine for this one request:
          - "ollama": run ONLY the local tier3 lane (no Gemini fallback). If
            tier3 is dead/unconfigured this raises — strict by design.
          - "gemini" / None: normal tiered chain (which may still fall through
            to tier3 as the offline floor).
        """
        primary, default_think = TASK_TIER_MAP[task]
        thinking = thinking or default_think

        if force_provider == "ollama":
            spec = self.tiers.get("tier3")
            if not spec or self._is_dead("tier3"):
                raise LLMError(
                    "Ollama (tier3) is not available; cannot honor force_provider='ollama'"
                )
            chain = [spec]
        else:
            chain = self._walk(primary, need_tools=bool(tools))
        if not chain:
            raise LLMError(f"No live tiers available for task={task.value}")

        last_exc: Optional[Exception] = None
        for spec in chain:
            try:
                return await self._call_with_repair(
                    spec=spec,
                    prompt=prompt,
                    schema=schema,
                    thinking=thinking,
                    cached_content=cached_content,
                    tools=tools,
                    temperature=temperature,
                )
            except LLMAuthError:
                # Misconfigured SA / wrong project — never silently mask.
                raise
            except LLMPermanentError as e:
                last_exc = e
                self._mark_dead(spec.key)
                continue
            except LLMTransientError as e:
                last_exc = e
                # Already retried inside _call_with_repair; demote without
                # marking dead (tier may recover).
                logger.warning("Tier %s transient exhaust: %s", spec.key, e)
                continue
            except LLMSchemaError as e:
                last_exc = e
                logger.warning("Tier %s schema exhaust: %s", spec.key, e)
                continue

        raise LLMError(
            f"All tiers exhausted for task={task.value}. Last error: {last_exc}"
        )

    async def _call_with_repair(
        self,
        *,
        spec: TierSpec,
        prompt: str,
        schema: Type[BaseModel],
        thinking: str,
        cached_content: Optional[str],
        tools: Optional[list[Any]],
        temperature: float,
    ) -> dict[str, Any]:
        attempts = cfg.MAX_RETRIES_PER_TIER + 1
        last_schema_exc: Optional[LLMSchemaError] = None
        for attempt in range(attempts):
            try:
                return await spec.provider.generate_json(
                    prompt=prompt,
                    schema=schema,
                    thinking=thinking,
                    cached_content=cached_content,
                    tools=tools,
                    temperature=temperature,
                )
            except LLMTransientError as e:
                if attempt == attempts - 1:
                    raise
                backoff = min(2 ** attempt, 8)
                logger.info(
                    "Tier %s transient (attempt %d/%d): %s — sleep %ds",
                    spec.key, attempt + 1, attempts, e, backoff,
                )
                await asyncio.sleep(backoff)
            except LLMSchemaError as e:
                last_schema_exc = e
                # One repair pass at the same tier, then bubble up to demote.
                if attempt == attempts - 1:
                    raise
                prompt = (
                    "Your previous output failed schema validation.\n"
                    f"Validation errors:\n{e}\n\n"
                    "Return ONLY a corrected JSON object validating the schema. "
                    "No prose. No markdown fences.\n\n"
                    "Original task:\n" + prompt
                )
        # Should be unreachable, but keep mypy happy.
        if last_schema_exc:
            raise last_schema_exc
        raise LLMError("call_with_repair: exhausted without returning")

    # ------------------------------------------------------------------ boot
    async def boot_probe(self) -> dict[str, bool]:
        """Probe each non-redundant tier once at boot. Mark dead tiers as such.

        Auth errors are NOT swallowed here — we want a loud failure on
        misconfigured service accounts.
        """
        results: dict[str, bool] = {}
        # Probe one provider per "lane" — tier0 and tier0t share a backend story
        # but advertise differently. We still probe both.
        for key in DEMOTION_ORDER:
            spec = self.tiers.get(key)
            if not spec:
                continue
            try:
                ok = await spec.provider.probe()
            except LLMAuthError:
                raise  # bubble
            except Exception as e:
                logger.warning("Probe error on %s: %s", key, e)
                ok = False
            results[key] = ok
            if not ok:
                self._mark_dead(key)
        return results


# --------------------------------------------------------------------- factory
_router_singleton: Optional[LLMRouter] = None


def _build_default_router() -> LLMRouter:
    tiers: dict[str, TierSpec] = {}

    if cfg.LLM_PROVIDER == "gemini":
        tiers["tier0"]  = TierSpec("tier0",  GeminiProvider(cfg.GEMINI_MODEL_PRIMARY))
        tiers["tier0t"] = TierSpec("tier0t", GeminiProvider(cfg.GEMINI_MODEL_TOOLS),
                                   supports_tools=True)
        tiers["tier1"]  = TierSpec("tier1",  GeminiProvider(cfg.GEMINI_MODEL_GA))
        tiers["tier2"]  = TierSpec("tier2",  GeminiProvider(cfg.GEMINI_MODEL_FAST))

    # Always wire Ollama as the last lane so we have an offline floor.
    tiers["tier3"] = TierSpec("tier3", OllamaProvider(cfg.OLLAMA_MODEL))

    return LLMRouter(tiers)


def get_router() -> LLMRouter:
    global _router_singleton
    if _router_singleton is None:
        _router_singleton = _build_default_router()
    return _router_singleton
