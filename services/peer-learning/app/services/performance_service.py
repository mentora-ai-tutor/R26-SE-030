from datetime import datetime
from typing import Dict, Any, List, Optional
from app.core.database import get_db


async def get_student_performance(student_id: str) -> Dict[str, Any]:
    """Get overall performance summary for a student."""
    db = get_db()
    student = await db.students.find_one({"student_id": student_id}, {"_id": 0})
    if not student:
        return {"error": "Student not found"}

    pair_sessions = await db.pair_sessions.find(
        {"$or": [{"learner_id": student_id}, {"teacher_id": student_id}]},
        {"_id": 0, "question_log": 0},
    ).to_list(length=None)

    group_sessions = await db.group_sessions.find(
        {"members.student_id": student_id},
        {"_id": 0, "chat_log": 0},
    ).to_list(length=None)

    learner_sessions = [s for s in pair_sessions if s.get("learner_id") == student_id and s.get("status") == "completed"]
    teacher_sessions = [s for s in pair_sessions if s.get("teacher_id") == student_id and s.get("status") == "completed"]
    completed_groups = [s for s in group_sessions if s.get("status") == "completed"]

    avg_learner_score = (
        sum(s.get("performance_score", 0) for s in learner_sessions) / len(learner_sessions)
        if learner_sessions else 0
    )
    avg_teacher_score = (
        sum(s.get("teacher_score", 0) for s in teacher_sessions) / len(teacher_sessions)
        if teacher_sessions else 0
    )

    return {
        "student_id": student_id,
        "status": student.get("status"),
        "initial_mastery": student.get("initial_mastery_score"),
        "current_mastery": student.get("mastery_profile", {}).get("overall_mastery_score"),
        "topics_improved": student.get("improved_topics", []),
        "topics_mastered": student.get("mastered_topics", []),
        "remaining_gaps": len(student.get("mastery_profile", {}).get("knowledge_gaps", [])),
        "pair_sessions_as_learner": len(learner_sessions),
        "pair_sessions_as_teacher": len(teacher_sessions),
        "group_sessions_completed": len(completed_groups),
        "avg_learner_score": round(avg_learner_score, 2),
        "avg_teacher_score": round(avg_teacher_score, 2),
        "current_session_id": student.get("current_session_id"),
    }


async def get_student_topic_performance(student_id: str, topic_id: str) -> Dict[str, Any]:
    """Get performance for a specific student-topic pair."""
    from app.services.verification_service import generate_topic_performance_history
    return await generate_topic_performance_history(student_id, topic_id)


async def generate_completion_report(student_id: str) -> Dict[str, Any]:
    """Phase 11: Generate full completion report for a student."""
    db = get_db()
    student = await db.students.find_one({"student_id": student_id}, {"_id": 0})
    if not student:
        return {"error": "Student not found"}

    pair_sessions = await db.pair_sessions.count_documents({
        "$or": [{"learner_id": student_id}, {"teacher_id": student_id}],
        "status": "completed",
    })
    group_sessions = await db.group_sessions.count_documents({
        "members.student_id": student_id,
        "status": "completed",
    })

    # Topics they can teach
    strengths = student.get("mastery_profile", {}).get("strengths", [])
    can_teach = [s["topic"] for s in strengths if s.get("can_teach_others")]

    # Mastered topics with scores
    mastered_topics = []
    for topic_id in student.get("mastered_topics", []):
        verified = await db.verified_pools.find_one(
            {"student_id": student_id, "topic_id": topic_id}, {"_id": 0}
        )
        mastered_topics.append({
            "topic_id": topic_id,
            "topic_name": verified.get("topic_name") if verified else topic_id,
            "mastery_score": verified.get("final_mastery_score") if verified else None,
            "verification_date": verified.get("verification_date") if verified else None,
        })

    # Estimate total time (from session timestamps)
    first_session = await db.pair_sessions.find_one(
        {"$or": [{"learner_id": student_id}, {"teacher_id": student_id}]},
        sort=[("created_at", 1)],
    )
    total_seconds = None
    if first_session:
        total_seconds = int((datetime.utcnow() - first_session["created_at"]).total_seconds())

    return {
        "student_id": student_id,
        "initial_overall_mastery": student.get("initial_mastery_score", 0),
        "final_overall_mastery": student.get("mastery_profile", {}).get("overall_mastery_score", 0),
        "topics_mastered": mastered_topics,
        "pair_sessions_completed": pair_sessions,
        "group_sessions_completed": group_sessions,
        "topics_can_teach": can_teach,
        "total_time_seconds": total_seconds,
        "completion_date": datetime.utcnow(),
    }
