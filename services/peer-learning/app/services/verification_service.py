from datetime import datetime
from typing import Dict, Any, Optional
from loguru import logger
from app.core.database import get_db
from app.core.config import settings
from app.services.pool_service import add_to_verified_pool


async def check_verification_criteria(student_id: str, topic_id: str) -> Dict[str, Any]:
    """
    Phase 10: Check if student meets all verification criteria.
    Criteria (ALL must be met):
    1. 3 consecutive group sessions with score >= 90%
    2. Demonstrated teaching ability
    3. No hints used in last 2 sessions
    4. Solved unfamiliar problem independently
    """
    db = get_db()

    pool_entry = await db.improved_pools.find_one(
        {"student_id": student_id, "topic_id": topic_id}, {"_id": 0}
    )
    if not pool_entry:
        return {"eligible": False, "reason": "Not in improved pool"}

    # Criterion 1: 3 consecutive group sessions >= 90%
    consecutive = pool_entry.get("consecutive_group_sessions_above_threshold", 0)
    if consecutive < settings.verification_consecutive_sessions:
        return {
            "eligible": False,
            "reason": f"Need {settings.verification_consecutive_sessions} consecutive sessions >=90%, have {consecutive}",
        }

    # Criterion 2: Demonstrated teaching ability
    has_taught = await _check_teaching_ability(student_id, topic_id)

    # Criterion 3: No hints used in last 2 group sessions
    no_hints = await _check_no_hints_last_sessions(student_id, topic_id)

    # Criterion 4: Check group session independence
    independent = await _check_independent_performance(student_id, topic_id)

    if not has_taught:
        return {"eligible": False, "reason": "Must demonstrate teaching ability first"}

    if not no_hints:
        return {"eligible": False, "reason": "Must complete last 2 sessions without hints"}

    # All criteria met → verify
    final_mastery = pool_entry.get("mastery_score", 90.0)
    topic_name = pool_entry.get("topic_name", topic_id)

    result = await add_to_verified_pool(
        student_id=student_id,
        topic_id=topic_id,
        topic_name=topic_name,
        final_mastery_score=final_mastery,
    )

    # Generate performance history
    history = await generate_topic_performance_history(student_id, topic_id)

    logger.info(f"Student {student_id} VERIFIED for topic {topic_id}!")
    return {
        "eligible": True,
        "verified": True,
        "student_id": student_id,
        "topic_id": topic_id,
        "final_mastery": final_mastery,
        "performance_history": history,
        **result,
    }


async def _check_teaching_ability(student_id: str, topic_id: str) -> bool:
    """Check if student has successfully taught this topic."""
    db = get_db()
    teaching_sessions = await db.pair_sessions.count_documents(
        {
            "teacher_id": student_id,
            "topic_id": topic_id,
            "status": "completed",
            "teacher_score": {"$gte": 50},
        }
    )
    return teaching_sessions > 0


async def _check_no_hints_last_sessions(student_id: str, topic_id: str) -> bool:
    """Check no hints used in last 2 group sessions for this topic."""
    db = get_db()
    # Get last 2 group sessions
    recent_group = await db.group_sessions.find(
        {
            "topic_id": topic_id,
            "members.student_id": student_id,
            "status": "completed",
        },
        {"_id": 0},
    ).sort("completed_at", -1).limit(2).to_list(length=None)

    if len(recent_group) < 2:
        # Not enough sessions yet - give benefit of doubt
        return True

    # Check pair sessions for hint usage in last 2
    recent_pair = await db.pair_sessions.find(
        {
            "topic_id": topic_id,
            "learner_id": student_id,
            "status": "completed",
        },
        {"_id": 0},
    ).sort("completed_at", -1).limit(2).to_list(length=None)

    for session in recent_pair:
        if session.get("hints_used_by_learner", 0) > 0:
            return False

    return True


async def _check_independent_performance(student_id: str, topic_id: str) -> bool:
    """Check if student solved a problem independently (high score, no help)."""
    db = get_db()
    independent_sessions = await db.pair_sessions.count_documents(
        {
            "learner_id": student_id,
            "topic_id": topic_id,
            "status": "completed",
            "performance_score": {"$gte": 90},
            "hints_used_by_learner": 0,
            "help_requests": 0,
        }
    )
    return independent_sessions > 0


async def generate_topic_performance_history(student_id: str, topic_id: str) -> Dict[str, Any]:
    """Generate complete performance history for a student and topic."""
    db = get_db()

    pair_sessions = await db.pair_sessions.find(
        {"$or": [{"learner_id": student_id}, {"teacher_id": student_id}], "topic_id": topic_id},
        {"_id": 0, "question_log": 0},
    ).to_list(length=None)

    group_sessions = await db.group_sessions.find(
        {"members.student_id": student_id, "topic_id": topic_id},
        {"_id": 0, "chat_log": 0},
    ).to_list(length=None)

    teaching_sessions = [s for s in pair_sessions if s.get("teacher_id") == student_id]

    verified = await db.verified_pools.find_one(
        {"student_id": student_id, "topic_id": topic_id}, {"_id": 0}
    )

    return {
        "student_id": student_id,
        "topic_id": topic_id,
        "pair_sessions": pair_sessions,
        "group_sessions": group_sessions,
        "teaching_sessions": teaching_sessions,
        "final_mastery": verified.get("final_mastery_score") if verified else None,
        "verification_date": verified.get("verification_date") if verified else None,
    }
