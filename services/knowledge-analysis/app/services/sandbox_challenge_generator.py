"""LLM-authored, runtime-verified sandbox coding challenges.

Flow per batch:
  1. Gemini (``Task.QUESTION_GEN``) writes N original Java exercises ramping easy->hard,
     each with a student-facing ``starter_code`` AND a complete ``reference_solution``.
  2. Every reference solution is executed through the ai-engine (`POST /api/execute`),
     and its REAL stdout becomes the authoritative ``expected_output``. A solution that
     fails to compile/run, or whose output is empty, is discarded — never served.
  3. Anything short of the requested count is topped up from a hand-verified seed bank,
     so a Gemini/ai-engine outage still yields a usable, correct set.

The ``reference_solution`` is stored server-side only; the client view strips it.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import httpx
from bson import ObjectId

from app.core.config import AI_ENGINE_URL
from app.db.database import get_database
from app.models.sandbox import GeneratedChallengeBatch
from app.services.llm import Task, get_router

logger = logging.getLogger(__name__)

_SEED_PATH = Path(__file__).resolve().parent.parent / "data" / "sandbox_seed_challenges.json"
CHALLENGE_SCHEMA_VERSION = "kaa-sandbox-challenge-v1.0"
DIFFICULTY_ORDER = ["easy", "medium", "hard"]
SANDBOX_DEFAULT_TOPICS = ["Loops", "Arrays", "Strings", "Recursion", "Collections"]
_VERIFY_TIMEOUT_SECONDS = 35.0


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- seed
@lru_cache(maxsize=1)
def load_seed_challenges() -> list[dict[str, Any]]:
    try:
        raw = json.loads(_SEED_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:  # pragma: no cover - packaging error
        logger.error("Could not load sandbox_seed_challenges.json: %s", exc)
        return []
    out: list[dict[str, Any]] = []
    for c in raw:
        c = dict(c)
        c["source"] = "seed"
        out.append(c)
    return out


def client_view(c: dict[str, Any]) -> dict[str, Any]:
    """Student-safe view — the reference solution is withheld; expected_output stays
    (the sandbox UI already shows the expected output)."""
    return {
        "id": c.get("id"),
        "title": c.get("title"),
        "topic": c.get("topic"),
        "difficulty": c.get("difficulty"),
        "prompt": c.get("prompt"),
        "starter_code": c.get("starter_code"),
        "expected_output": c.get("expected_output"),
        "stdin": c.get("stdin"),
        "source": c.get("source"),
    }


def _by_difficulty(challenges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        challenges,
        key=lambda c: DIFFICULTY_ORDER.index(c["difficulty"])
        if c.get("difficulty") in DIFFICULTY_ORDER
        else len(DIFFICULTY_ORDER),
    )


# ------------------------------------------------------------------- verification
async def _run_java(code: str, stdin: Optional[str]) -> Optional[dict[str, Any]]:
    """Execute Java through the ai-engine. Returns its result dict, or None on failure."""
    try:
        async with httpx.AsyncClient(timeout=_VERIFY_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                f"{AI_ENGINE_URL}/api/execute",
                json={"code": code, "stdin": stdin or "", "context": "sandbox-challenge-verify"},
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:  # ai-engine down / timeout / non-2xx
        logger.warning("ai-engine verification call failed: %s", exc)
        return None


# ----------------------------------------------------------------------- LLM gen
def _generation_prompt(topics: list[str], count: int) -> str:
    return (
        f"Generate {count} original Java coding exercises that ramp from simple to hard "
        f"(order them easy, then medium, then hard as the count allows).\n"
        f"Draw topics from: {', '.join(topics)}.\n\n"
        "For EACH exercise provide:\n"
        "- title: a short title (2-4 words)\n"
        "- topic: one of the listed topics\n"
        "- difficulty: 'easy' | 'medium' | 'hard'\n"
        "- prompt: one or two sentences telling the student EXACTLY what to print. The "
        "required output MUST be deterministic (a single fixed correct answer).\n"
        "- starter_code: a COMPLETE, compilable 'public class Main' with a main method "
        "skeleton where the core logic is replaced by a '// TODO' comment.\n"
        "- reference_solution: a COMPLETE, correct 'public class Main' that solves the "
        "prompt and prints ONLY the required output. It MUST compile and run.\n"
        "- stdin: the exact standard input the program reads, or null if it reads none.\n\n"
        "Rules: pure stdout only; no randomness, no current date/time, no external "
        "libraries or network; keep each program under 40 lines. Mentally execute the "
        "reference_solution to be sure it prints the intended deterministic output.\n"
        "Return ONLY the JSON object matching the schema."
    )


async def _generate_and_verify(
    topics: list[str], count: int, force_provider: Optional[str] = None
) -> list[dict[str, Any]]:
    raw = await get_router().generate_json(
        prompt=_generation_prompt(topics, count),
        schema=GeneratedChallengeBatch,
        task=Task.QUESTION_GEN,
        temperature=0.9,  # high temperature -> fresh, varied questions each refresh
        force_provider=force_provider,
    )
    batch = GeneratedChallengeBatch.model_validate(raw)
    if not batch.challenges:
        return []

    # Verify every reference solution concurrently (cuts wall-clock vs sequential).
    runs = await asyncio.gather(
        *[_run_java(ch.reference_solution, ch.stdin) for ch in batch.challenges]
    )

    verified: list[dict[str, Any]] = []
    for ch, run in zip(batch.challenges, runs):
        if not run or not run.get("success"):
            continue
        output = (run.get("output") or "").strip()
        if not output:
            continue  # no deterministic output to grade against -> drop
        verified.append(
            {
                "id": str(ObjectId()),
                "title": ch.title,
                "topic": ch.topic,
                "difficulty": ch.difficulty,
                "prompt": ch.prompt,
                "starter_code": ch.starter_code,
                "reference_solution": ch.reference_solution,
                "expected_output": output,  # authoritative: real stdout, not the LLM's guess
                "stdin": ch.stdin,
                "source": "generated",
                "verified": True,
            }
        )
    return verified


# ---------------------------------------------------------------------- assembly
async def build_challenge_batch(
    student: Any,
    count: int = 3,
    topics: Optional[list[str]] = None,
    force_provider: Optional[str] = None,
) -> dict[str, Any]:
    """Return ``{"challenges": [...client views...], "source", "degraded"}``."""
    topics = topics or list(SANDBOX_DEFAULT_TOPICS)

    generated: list[dict[str, Any]] = []
    try:
        generated = await _generate_and_verify(topics, count, force_provider=force_provider)
    except Exception as exc:  # any LLM/router/validation failure -> seed fallback
        logger.warning("Sandbox challenge generation failed (%s); using seed bank", exc)

    challenges = list(generated)
    seed_used = False
    if len(challenges) < count:
        seeds = [dict(c) for c in load_seed_challenges()]
        random.shuffle(seeds)
        for s in seeds:
            if len(challenges) >= count:
                break
            s["id"] = s.get("id") or str(ObjectId())
            challenges.append(s)
            seed_used = True

    challenges = _by_difficulty(challenges[:count])

    if not generated:
        source, degraded = "seed", True
    elif seed_used:
        source, degraded = "mixed", True
    else:
        source, degraded = "generated", False

    # Persist full challenges (incl. reference_solution) for audit/reuse — best effort.
    try:
        db = get_database()
        now = _utcnow()
        await db.sandbox_challenges.insert_many(
            [
                {
                    **c,
                    "student_id": getattr(student, "id", None),
                    "schema_version": CHALLENGE_SCHEMA_VERSION,
                    "verified_at": now,
                    "created_at": now,
                }
                for c in challenges
            ],
            ordered=False,
        )
    except Exception:  # pragma: no cover - persistence is non-critical
        pass

    return {
        "challenges": [client_view(c) for c in challenges],
        "source": source,
        "degraded": degraded,
    }


async def ensure_sandbox_challenge_indexes() -> None:
    db = get_database()
    await db.sandbox_challenges.create_index([("created_at", -1)])
    await db.sandbox_challenges.create_index([("difficulty", 1), ("topic", 1)])
