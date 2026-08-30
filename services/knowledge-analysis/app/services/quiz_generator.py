"""Adaptive Java quiz generator.

Produces a difficulty-laddered pool of multiple-choice / predict-output questions
that the Skill Check panel and the sandbox serve "simple -> hard". The LLM router's
``Task.QUESTION_GEN`` tier (Gemini Flash) is the primary source; a hand-verified seed
bank is the deterministic fallback so a Gemini outage never blocks a student
(``PHASE_2_SANDBOX_QUIZ_POPUP_PLAN.md`` risk #6).

Every question — generated or seed — is structurally validated before it leaves this
module: at least two options and a ``correct_option_id`` that actually exists. Bad
LLM output is dropped, not served.
"""
from __future__ import annotations

import json
import logging
import random
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from app.core.constants import QUIZ_DEFAULT_TOPICS, QUIZ_DIFFICULTY_ORDER
from app.models.quiz import GeneratedQuestionBatch
from app.services.llm import Task, get_router

logger = logging.getLogger(__name__)

_SEED_PATH = Path(__file__).resolve().parent.parent / "data" / "seed_questions.json"
_ALL_TYPES = ["mcq", "predict_output"]


# --------------------------------------------------------------------------- seed
@lru_cache(maxsize=1)
def load_seed_questions() -> list[dict[str, Any]]:
    """Load and stamp the offline fallback question bank (cached)."""
    try:
        raw = json.loads(_SEED_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:  # pragma: no cover - packaging error
        logger.error("Could not load seed_questions.json: %s", exc)
        return []
    cleaned: list[dict[str, Any]] = []
    for q in raw:
        q = dict(q)
        q["source"] = "seed"
        if _is_valid_question(q):
            cleaned.append(q)
    return cleaned


def _is_valid_question(q: dict[str, Any]) -> bool:
    options = q.get("options") or []
    ids = {o.get("id") for o in options if isinstance(o, dict)}
    return (
        bool(q.get("question"))
        and len(options) >= 2
        and q.get("correct_option_id") in ids
        and q.get("difficulty") in QUIZ_DIFFICULTY_ORDER
    )


def build_seed_pool(
    topics: Optional[list[str]],
    types: list[str],
    per_difficulty: int,
    only_difficulty: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Draw a difficulty-laddered sample from the seed bank (no LLM, no I/O beyond cache)."""
    seeds = [q for q in load_seed_questions() if q.get("type") in types]
    if topics:
        topical = [q for q in seeds if q.get("topic") in topics]
        if topical:  # only narrow when the topic filter actually matches something
            seeds = topical

    difficulties = [only_difficulty] if only_difficulty else QUIZ_DIFFICULTY_ORDER
    out: list[dict[str, Any]] = []
    for difficulty in difficulties:
        bucket = [dict(q) for q in seeds if q.get("difficulty") == difficulty]
        random.shuffle(bucket)
        out.extend(bucket[:per_difficulty])
    return out


# ----------------------------------------------------------------------- LLM gen
def _generation_prompt(topics: list[str], types: list[str], per_difficulty: int) -> str:
    topic_list = ", ".join(topics)
    return (
        "You are a Java instructor writing a short adaptive quiz that ramps from "
        "simple to hard. Produce fresh, original multiple-choice questions.\n\n"
        f"Topics to cover (spread across them): {topic_list}.\n"
        f"Question types allowed: {', '.join(types)}.\n"
        f"Generate exactly {per_difficulty} questions for EACH difficulty: "
        "'easy', 'medium', 'hard'.\n\n"
        "Rules:\n"
        "- Each question MUST have exactly 4 options with ids 'A','B','C','D' and "
        "exactly one correct answer.\n"
        "- For type 'predict_output', put runnable, correct Java in 'code_snippet' "
        "and make the options candidate program outputs. Double-check the expected "
        "output by mentally executing the code.\n"
        "- For type 'mcq', code_snippet may be null.\n"
        "- 'explanation' must briefly justify the correct answer.\n"
        "- 'concept_tested' is a short tag (e.g. 'loop boundary conditions').\n"
        "- Keep questions self-contained and unambiguous. Vary them; do not reuse "
        "textbook clichés verbatim.\n"
        "Return ONLY the JSON object matching the schema."
    )


async def _generate_with_llm(
    topics: list[str], types: list[str], per_difficulty: int
) -> list[dict[str, Any]]:
    raw = await get_router().generate_json(
        prompt=_generation_prompt(topics, types, per_difficulty),
        schema=GeneratedQuestionBatch,
        task=Task.QUESTION_GEN,
        temperature=0.85,  # higher temperature -> more variety / "random" feel
    )
    batch = GeneratedQuestionBatch.model_validate(raw)
    out: list[dict[str, Any]] = []
    for question in batch.questions:
        q = question.model_dump()
        q["source"] = "generated"
        if _is_valid_question(q):
            out.append(q)
    return out


def _group_by_difficulty(questions: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {d: [] for d in QUIZ_DIFFICULTY_ORDER}
    for q in questions:
        grouped.setdefault(q.get("difficulty", "easy"), []).append(q)
    return grouped


async def build_quiz_pool(
    topics: Optional[list[str]] = None,
    mode: str = "sandbox",
    per_difficulty: int = 2,
) -> dict[str, Any]:
    """Build the laddered question pool for a session.

    Returns ``{"questions": [...], "source": "generated"|"seed"|"mixed",
    "degraded": bool}``. Always returns a non-empty pool as long as the seed bank
    loads, so the caller never has to handle "no questions".
    """
    topics = topics or list(QUIZ_DEFAULT_TOPICS)
    types = ["mcq"] if mode == "onboarding" else _ALL_TYPES

    generated: list[dict[str, Any]] = []
    try:
        generated = await _generate_with_llm(topics, types, per_difficulty)
    except Exception as exc:  # broad: any LLM/router/validation failure -> seed bank
        logger.warning("Quiz LLM generation failed (%s); using seed bank", exc)

    grouped = _group_by_difficulty(generated)
    seed_topped_up = False
    for difficulty in QUIZ_DIFFICULTY_ORDER:
        if not grouped.get(difficulty):
            grouped[difficulty] = build_seed_pool(
                topics, types, per_difficulty, only_difficulty=difficulty
            )
            if grouped[difficulty]:
                seed_topped_up = True

    pool = [q for difficulty in QUIZ_DIFFICULTY_ORDER for q in grouped.get(difficulty, [])]

    if not generated:
        source, degraded = "seed", True
    elif seed_topped_up:
        source, degraded = "mixed", True
    else:
        source, degraded = "generated", False

    return {"questions": pool, "source": source, "degraded": degraded}
