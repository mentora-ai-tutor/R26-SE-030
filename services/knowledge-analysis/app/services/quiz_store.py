"""Persistence + adaptive serving for the Java quiz.

Three Mongo collections in the ``knowledge_analysis`` database:
  * ``quiz_sessions``       — one doc per skill-check run (the laddered pool, the
    student's answers, current difficulty rung, and the final ``results`` once complete).
  * ``quiz_question_bank``  — every served question, tagged source ``seed``/``generated``
    and ``verified_at`` (matches ``PHASE_2_SANDBOX_QUIZ_POPUP_PLAN.md §6.6``), kept for
    audit/reuse.
  * ``quiz_results``        — one doc per COMPLETED quiz: the cross-team result record
    (score + per-topic ``QuizPerformance`` + per-question detail). This is what other
    services consume; shape documented in ``app.models.quiz.QuizResultRecord``.

The adaptive rule is the literal "simple -> hard" the brief asked for: start at
``easy``, climb a rung on a correct answer, step down on a wrong one. The pure helpers
(``climb``/``step_down``/``select_next``/``summarize``) are import-free of Mongo so they
can be unit-tested without a database.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from bson import ObjectId
from fastapi import HTTPException, status
from pymongo.errors import DuplicateKeyError

from app.core.constants import (
    QUIZ_DEFAULT_MAX_QUESTIONS,
    QUIZ_DIFFICULTY_ORDER,
    QUIZ_SCHEMA_VERSION,
)
from app.db.database import get_database
from app.models.quiz import AnswerQuizRequest, StartQuizRequest
from app.services.quiz_generator import build_quiz_pool

# Modules that need a student context import this lazily to avoid a cycle.
import logging
import random

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------- pure adaptive logic
def climb(difficulty: str) -> str:
    """One rung harder, capped at the top."""
    try:
        idx = QUIZ_DIFFICULTY_ORDER.index(difficulty)
    except ValueError:
        return QUIZ_DIFFICULTY_ORDER[0]
    return QUIZ_DIFFICULTY_ORDER[min(idx + 1, len(QUIZ_DIFFICULTY_ORDER) - 1)]


def step_down(difficulty: str) -> str:
    """One rung easier, floored at the bottom."""
    try:
        idx = QUIZ_DIFFICULTY_ORDER.index(difficulty)
    except ValueError:
        return QUIZ_DIFFICULTY_ORDER[0]
    return QUIZ_DIFFICULTY_ORDER[max(idx - 1, 0)]


def _search_order(difficulty: str) -> list[str]:
    """Difficulty preference when the exact rung is exhausted: exact, then harder, then easier."""
    try:
        idx = QUIZ_DIFFICULTY_ORDER.index(difficulty)
    except ValueError:
        idx = 0
    harder = QUIZ_DIFFICULTY_ORDER[idx + 1:]
    easier = list(reversed(QUIZ_DIFFICULTY_ORDER[:idx]))
    return [QUIZ_DIFFICULTY_ORDER[idx], *harder, *easier]


def select_next(
    pool: list[dict[str, Any]],
    asked_qids: list[str],
    difficulty: str,
) -> Optional[dict[str, Any]]:
    """Pick an unserved question, preferring the current rung (random within a rung)."""
    asked = set(asked_qids)
    remaining = [q for q in pool if q.get("qid") not in asked]
    if not remaining:
        return None
    for rung in _search_order(difficulty):
        bucket = [q for q in remaining if q.get("difficulty") == rung]
        if bucket:
            return random.choice(bucket)
    return random.choice(remaining)


def strip_question(q: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Client-safe view of a question — the answer key and explanation are withheld."""
    if not q:
        return None
    return {
        "qid": q.get("qid"),
        "topic": q.get("topic"),
        "difficulty": q.get("difficulty"),
        "type": q.get("type", "mcq"),
        "question": q.get("question"),
        "code_snippet": q.get("code_snippet"),
        "options": q.get("options", []),
    }


def summarize(answers: list[dict[str, Any]]) -> dict[str, Any]:
    """Score the session and emit a ``QuizPerformance``-shaped per-topic breakdown.

    The ``quiz_performance`` list matches ``schemas.QuizPerformance`` exactly, so it can
    be fed straight into ``POST /analyze`` as ``quiz_sessions``.
    """
    total = len(answers)
    correct = sum(1 for a in answers if a.get("correct"))
    by_topic: dict[str, dict[str, Any]] = {}
    for a in answers:
        topic = a.get("topic", "Unknown")
        bucket = by_topic.setdefault(topic, {"topic": topic, "correct": 0, "total": 0, "time": 0.0})
        bucket["total"] += 1
        bucket["time"] += float(a.get("time_seconds", 0) or 0)
        if a.get("correct"):
            bucket["correct"] += 1
    quiz_performance = [
        {
            "topic": b["topic"],
            "correct": b["correct"],
            "total": b["total"],
            "avg_time_seconds": round(b["time"] / b["total"], 1) if b["total"] else 0.0,
            "retry_count": 0,
        }
        for b in by_topic.values()
    ]
    return {
        "score_percent": round(correct / total * 100, 1) if total else 0.0,
        "correct": correct,
        "total": total,
        "quiz_performance": quiz_performance,
    }


def grade(question: dict[str, Any], chosen_option_id: str) -> bool:
    return question.get("correct_option_id") == chosen_option_id


def _highest_difficulty(answers: list[dict[str, Any]]) -> str:
    """The hardest rung the student actually ANSWERED (not the adaptive next rung)."""
    answered = [a.get("difficulty") for a in answers if a.get("difficulty") in QUIZ_DIFFICULTY_ORDER]
    if not answered:
        return QUIZ_DIFFICULTY_ORDER[0]
    return max(answered, key=lambda d: QUIZ_DIFFICULTY_ORDER.index(d))


# ------------------------------------------------------------------------- indexes
async def ensure_quiz_indexes() -> None:
    db = get_database()
    await db.quiz_sessions.create_index([("student_id", 1), ("created_at", -1)])
    await db.quiz_sessions.create_index([("job_id", 1)])
    await db.quiz_question_bank.create_index([("topic", 1), ("difficulty", 1)])
    await db.quiz_question_bank.create_index([("source", 1)])
    # quiz_results: the cross-team result record, queried by student + recency.
    await db.quiz_results.create_index([("public_student_id", 1), ("completed_at", -1)])
    await db.quiz_results.create_index([("student_id", 1), ("completed_at", -1)])
    # Unique: exactly one result document per completed session (guards the
    # one-result-per-session contract against concurrent-completion races).
    await db.quiz_results.create_index([("session_id", 1)], unique=True)


# --------------------------------------------------------------------- session ops
def _find_in_pool(pool: list[dict[str, Any]], qid: str) -> Optional[dict[str, Any]]:
    return next((q for q in pool if q.get("qid") == qid), None)


def _pending_qid(doc: dict[str, Any]) -> Optional[str]:
    """The served-but-not-yet-answered question id (last asked beyond answered count)."""
    asked = doc.get("asked", [])
    answered = {a.get("qid") for a in doc.get("answers", [])}
    for qid in reversed(asked):
        if qid not in answered:
            return qid
    return None


def _progress(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "answered": len(doc.get("answers", [])),
        "total_planned": doc.get("max_questions", 0),
        "difficulty": doc.get("current_difficulty"),
        "status": doc.get("status"),
    }


async def create_session(student: Any, req: StartQuizRequest) -> dict[str, Any]:
    db = get_database()
    pool_info = await build_quiz_pool(topics=req.topics, mode=req.mode)
    pool = pool_info["questions"]
    if not pool:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="No quiz questions are available right now. Please retry shortly.",
        )

    for q in pool:
        q["qid"] = str(ObjectId())

    max_questions = min(req.max_questions or QUIZ_DEFAULT_MAX_QUESTIONS, len(pool))
    start_difficulty = QUIZ_DIFFICULTY_ORDER[0]  # always "simple to hard"
    first = select_next(pool, [], start_difficulty)
    now = _utcnow()

    doc = {
        "student_id": student.id,
        "public_student_id": student.student_id,
        "mode": req.mode,
        "topics": req.topics,
        "job_id": req.job_id,
        "status": "active",
        "source": pool_info["source"],
        "degraded": pool_info["degraded"],
        "current_difficulty": start_difficulty,
        "max_questions": max_questions,
        "pool": pool,
        "asked": [first["qid"]] if first else [],
        "answers": [],
        "schema_version": QUIZ_SCHEMA_VERSION,
        "created_at": now,
        "updated_at": now,
    }
    result = await db.quiz_sessions.insert_one(doc)
    session_id = str(result.inserted_id)

    # Best-effort audit/reuse bank; never block the student if this fails.
    try:
        await db.quiz_question_bank.insert_many(
            [
                {
                    "qid": q["qid"],
                    "session_id": session_id,
                    "topic": q.get("topic"),
                    "difficulty": q.get("difficulty"),
                    "type": q.get("type"),
                    "payload": q,
                    "source": q.get("source", pool_info["source"]),
                    "verified_at": now if q.get("source") == "seed" else None,
                    "created_at": now,
                }
                for q in pool
            ],
            ordered=False,
        )
    except Exception:  # pragma: no cover - bank is non-critical
        pass

    return {
        "session_id": session_id,
        "mode": req.mode,
        "source": pool_info["source"],
        "degraded": pool_info["degraded"],
        "total_planned": max_questions,
        "answered": 0,
        "difficulty": start_difficulty,
        "question": strip_question(first),
    }


async def _load_owned_session(student: Any, session_id: str) -> dict[str, Any]:
    if not ObjectId.is_valid(session_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid session id")
    db = get_database()
    doc = await db.quiz_sessions.find_one(
        {"_id": ObjectId(session_id), "student_id": student.id}
    )
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Quiz session not found")
    return doc


async def answer_question(
    student: Any, session_id: str, payload: AnswerQuizRequest
) -> dict[str, Any]:
    db = get_database()
    doc = await _load_owned_session(student, session_id)

    if doc.get("status") == "completed":
        return {
            "result": None,
            "completed": True,
            "answered": len(doc.get("answers", [])),
            "total_planned": doc.get("max_questions", 0),
            "difficulty": doc.get("current_difficulty"),
            "next_question": None,
            "results": doc.get("results") or summarize(doc.get("answers", [])),
        }

    pending = _pending_qid(doc)
    if pending is None or payload.qid != pending:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This question is not the one currently awaiting an answer.",
        )

    pool = doc.get("pool", [])
    question = _find_in_pool(pool, payload.qid)
    if not question:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")

    correct = grade(question, payload.chosen_option_id)
    now = _utcnow()
    answer_record = {
        "qid": payload.qid,
        "topic": question.get("topic"),
        "difficulty": question.get("difficulty"),
        "type": question.get("type"),
        "chosen_option_id": payload.chosen_option_id,
        "correct": correct,
        "time_seconds": payload.time_seconds,
        "answered_at": now,
    }
    answers = doc.get("answers", []) + [answer_record]

    # Adapt the rung: harder on a hit, easier on a miss -> "simple to hard".
    next_difficulty = climb(doc["current_difficulty"]) if correct else step_down(doc["current_difficulty"])

    asked = list(doc.get("asked", []))
    completed = len(answers) >= doc.get("max_questions", 0)
    next_question = None
    if not completed:
        next_question = select_next(pool, asked, next_difficulty)
        if next_question is None:
            completed = True
        else:
            asked.append(next_question["qid"])

    new_status = "completed" if completed else "active"
    results_summary = summarize(answers) if completed else None

    update_fields: dict[str, Any] = {
        "answers": answers,
        "asked": asked,
        "current_difficulty": next_difficulty,
        "status": new_status,
        "updated_at": now,
    }
    if completed:
        # Persist the computed results ON the session (queryable without recomputation)
        # AND write the dedicated cross-team quiz_results record below.
        update_fields["results"] = results_summary
        update_fields["completed_at"] = now

    await db.quiz_sessions.update_one({"_id": doc["_id"]}, {"$set": update_fields})

    if completed:
        await _persist_quiz_result(
            db, doc, answers, results_summary, _highest_difficulty(answers), now
        )

    return {
        "result": {
            "qid": payload.qid,
            "correct": correct,
            "correct_option_id": question.get("correct_option_id"),
            "explanation": question.get("explanation"),
            "concept_tested": question.get("concept_tested"),
        },
        "completed": completed,
        "answered": len(answers),
        "total_planned": doc.get("max_questions", 0),
        "difficulty": next_difficulty,
        "next_question": strip_question(next_question),
        "results": results_summary,
    }


async def get_session_view(student: Any, session_id: str) -> dict[str, Any]:
    doc = await _load_owned_session(student, session_id)
    pending = _pending_qid(doc)
    pending_question = _find_in_pool(doc.get("pool", []), pending) if pending else None
    completed = doc.get("status") == "completed"
    return {
        "session_id": session_id,
        "mode": doc.get("mode"),
        "status": doc.get("status"),
        "source": doc.get("source"),
        "degraded": doc.get("degraded"),
        "answered": len(doc.get("answers", [])),
        "total_planned": doc.get("max_questions", 0),
        "difficulty": doc.get("current_difficulty"),
        "pending_question": strip_question(pending_question),
        "results": (doc.get("results") or summarize(doc.get("answers", []))) if completed else None,
    }


# ----------------------------------------------------------------- result records
def _build_result_record(
    session_doc: dict[str, Any],
    answers: list[dict[str, Any]],
    summary: dict[str, Any],
    difficulty_reached: str,
    completed_at: datetime,
) -> dict[str, Any]:
    """Assemble the cross-team quiz result document (see models.quiz.QuizResultRecord).

    ``topic_performance`` is exactly ``schemas.QuizPerformance`` shaped, so other services
    can feed it straight into ``POST /analyze`` as ``quiz_sessions``.
    """
    return {
        "session_id": str(session_doc.get("_id")),
        "student_id": session_doc.get("student_id"),
        "public_student_id": session_doc.get("public_student_id"),
        "mode": session_doc.get("mode"),
        "job_id": session_doc.get("job_id"),
        "schema_version": QUIZ_SCHEMA_VERSION,
        "score_percent": summary["score_percent"],
        "correct": summary["correct"],
        "total": summary["total"],
        "difficulty_reached": difficulty_reached,
        "topic_performance": summary["quiz_performance"],
        "questions": [
            {
                "qid": a.get("qid"),
                "topic": a.get("topic"),
                "difficulty": a.get("difficulty"),
                "type": a.get("type"),
                "correct": a.get("correct"),
                "chosen_option_id": a.get("chosen_option_id"),
                "time_seconds": a.get("time_seconds"),
            }
            for a in answers
        ],
        "completed_at": completed_at,
        "created_at": completed_at,
    }


async def _persist_quiz_result(
    db: Any,
    session_doc: dict[str, Any],
    answers: list[dict[str, Any]],
    summary: dict[str, Any],
    difficulty_reached: str,
    completed_at: datetime,
) -> None:
    """Insert the dedicated cross-team result record. Best-effort: the same data also
    lives on the session doc (``results``), so a failure here is recoverable, never fatal
    to the student's flow."""
    record = _build_result_record(session_doc, answers, summary, difficulty_reached, completed_at)
    try:
        await db.quiz_results.insert_one(record)
    except DuplicateKeyError:
        # Concurrent completion already wrote this session's result — one-per-session holds.
        pass
    except Exception as exc:  # pragma: no cover - non-critical, recoverable from session
        logger.warning(
            "Failed to write quiz_results for session %s: %s", record["session_id"], exc
        )


def _serialize_result(doc: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not doc:
        return None
    out = dict(doc)
    _id = out.pop("_id", None)
    if _id is not None:
        out["result_id"] = str(_id)
    for key in ("completed_at", "created_at"):
        value = out.get(key)
        if isinstance(value, datetime):
            out[key] = value.isoformat()
    return out


def _student_query(student_id: str) -> dict[str, Any]:
    # Key on the PUBLIC student id only — the cross-service identity (matches
    # mastery_profiles). Internal ids are not exposed via the read API.
    return {"public_student_id": student_id}


def _result_from_session(session_doc: dict[str, Any]) -> dict[str, Any]:
    """Reconstruct a result-record view from a completed session — the fallback used when
    the dedicated quiz_results insert did not land, so the cross-team contract still holds."""
    answers = session_doc.get("answers", [])
    summary = session_doc.get("results") or summarize(answers)
    completed_at = session_doc.get("completed_at") or session_doc.get("updated_at")
    record = _build_result_record(
        session_doc, answers, summary, _highest_difficulty(answers), completed_at
    )
    record["recovered_from"] = "quiz_sessions"  # transparency for consumers
    return _serialize_result(record) or {}


async def get_latest_result(student_id: str) -> Optional[dict[str, Any]]:
    """Latest completed quiz result for a student (public student id).

    Reads the dedicated ``quiz_results`` collection; if no record exists (e.g. its insert
    failed), falls back to the completed ``quiz_sessions`` doc so the contract still holds.
    """
    db = get_database()
    doc = await db.quiz_results.find_one(_student_query(student_id), sort=[("completed_at", -1)])
    if doc:
        return _serialize_result(doc)
    session = await db.quiz_sessions.find_one(
        {**_student_query(student_id), "status": "completed"},
        sort=[("completed_at", -1), ("updated_at", -1)],
    )
    return _result_from_session(session) if session else None


async def list_results(student_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """Recent completed quiz results for a student, newest first (with session fallback)."""
    db = get_database()
    cursor = db.quiz_results.find(_student_query(student_id)).sort("completed_at", -1).limit(limit)
    docs = await cursor.to_list(length=limit)
    if docs:
        return [r for r in (_serialize_result(d) for d in docs) if r]
    # Fallback: no dedicated result docs — reconstruct from completed sessions.
    scursor = (
        db.quiz_sessions.find({**_student_query(student_id), "status": "completed"})
        .sort("completed_at", -1)
        .limit(limit)
    )
    sdocs = await scursor.to_list(length=limit)
    return [r for r in (_result_from_session(d) for d in sdocs) if r]
