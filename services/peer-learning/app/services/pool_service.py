from datetime import datetime
from typing import Dict, Any, List, Optional
from loguru import logger
from app.core.database import get_db
from app.core.config import settings
from app.utils.helpers import sort_knowledge_gaps


async def add_to_improved_pool(
    student_id: str, topic_id: str, topic_name: str, mastery_score: float
) -> Dict[str, Any]:
    """Phase 5: Add student to improved pool after mastering in pair session."""
    db = get_db()

    # Check if already in pool
    existing = await db.improved_pools.find_one({"student_id": student_id, "topic_id": topic_id})
    if existing:
        # Update mastery score
        await db.improved_pools.update_one(
            {"student_id": student_id, "topic_id": topic_id},
            {"$set": {"mastery_score": mastery_score, "updated_at": datetime.utcnow()}},
        )
    else:
        doc = {
            "student_id": student_id,
            "topic_id": topic_id,
            "topic_name": topic_name,
            "mastery_score": mastery_score,
            "added_at": datetime.utcnow(),
            "teaching_ability": "not_yet",
            "consecutive_group_sessions_above_threshold": 0,
            "group_session_ids": [],
        }
        await db.improved_pools.insert_one(doc)

    # Update student record
    student = await db.students.find_one({"student_id": student_id})
    if student:
        gaps = student.get("mastery_profile", {}).get("knowledge_gaps", [])
        remaining_gaps = [g for g in gaps if g.get("topic_id") != topic_id]

        # Recalculate overall mastery
        strengths = student.get("mastery_profile", {}).get("strengths", [])
        total_topics = len(strengths) + len(remaining_gaps) + 1
        mastered_weight = mastery_score
        current_overall = (
            (student.get("mastery_profile", {}).get("overall_mastery_score", 50) * (total_topics - 1) + mastered_weight)
            / total_topics
        )

        await db.students.update_one(
            {"student_id": student_id},
            {
                "$set": {
                    "mastery_profile.knowledge_gaps": remaining_gaps,
                    "mastery_profile.overall_mastery_score": round(current_overall, 2),
                    "updated_at": datetime.utcnow(),
                },
                "$addToSet": {"improved_topics": topic_id},
            },
        )

        # Set next weak topic
        sorted_gaps = sort_knowledge_gaps(remaining_gaps)
        next_topic = sorted_gaps[0]["topic_id"] if sorted_gaps else None
        await db.students.update_one(
            {"student_id": student_id},
            {"$set": {"current_weak_topic": next_topic}},
        )

        if not remaining_gaps:
            logger.info(f"Student {student_id} has improved ALL topics!")

    # Check if pool size triggers group session
    pool_size = await db.improved_pools.count_documents(
        {"topic_id": topic_id, "teaching_ability": "not_yet"}
    )
    trigger_group = pool_size >= settings.improved_pool_group_trigger

    result = {
        "student_id": student_id,
        "topic_id": topic_id,
        "mastery_score": mastery_score,
        "pool_size": pool_size,
        "trigger_group_session": trigger_group,
    }

    if trigger_group:
        logger.info(f"Pool for {topic_id} has {pool_size} students - triggering group session")

    return result


async def create_topic_pool(topic_id: str) -> Dict:
    """Create (or verify) a topic pool collection entry."""
    db = get_db()
    count = await db.improved_pools.count_documents({"topic_id": topic_id})
    return {"topic_id": topic_id, "student_count": count, "message": "Pool exists or is empty"}


async def get_all_pools() -> List[Dict]:
    """Return aggregated pool info for all topics."""
    db = get_db()
    pipeline = [
        {
            "$group": {
                "_id": "$topic_id",
                "topic_name": {"$first": "$topic_name"},
                "student_count": {"$sum": 1},
                "avg_mastery": {"$avg": "$mastery_score"},
            }
        }
    ]
    result = await db.improved_pools.aggregate(pipeline).to_list(length=None)
    return [
        {
            "topic_id": r["_id"],
            "topic_name": r.get("topic_name"),
            "student_count": r["student_count"],
            "avg_mastery": round(r.get("avg_mastery", 0), 2),
        }
        for r in result
    ]


async def get_pool_students(topic_id: str) -> List[Dict]:
    db = get_db()
    return await db.improved_pools.find(
        {"topic_id": topic_id}, {"_id": 0}
    ).to_list(length=None)


async def add_to_verified_pool(
    student_id: str,
    topic_id: str,
    topic_name: str,
    final_mastery_score: float,
) -> Dict[str, Any]:
    """Phase 10: Add student to verified pool after meeting all criteria."""
    db = get_db()

    verified_doc = {
        "student_id": student_id,
        "topic_id": topic_id,
        "topic_name": topic_name,
        "verification_date": datetime.utcnow(),
        "final_mastery_score": final_mastery_score,
        "teaching_certified": True,
    }

    await db.verified_pools.update_one(
        {"student_id": student_id, "topic_id": topic_id},
        {"$set": verified_doc},
        upsert=True,
    )

    # Remove from improved pool
    await db.improved_pools.delete_one({"student_id": student_id, "topic_id": topic_id})

    # Update student record
    await db.students.update_one(
        {"student_id": student_id},
        {
            "$addToSet": {"mastered_topics": topic_id},
            "$set": {"updated_at": datetime.utcnow()},
        },
    )

    # Enable can_teach_others for this topic in strengths
    student = await db.students.find_one({"student_id": student_id})
    if student:
        strengths = student.get("mastery_profile", {}).get("strengths", [])
        # Check if already in strengths
        topic_in_strengths = any(s.get("topic_id") == topic_id for s in strengths)
        if not topic_in_strengths:
            strengths.append({
                "topic": topic_name,
                "topic_id": topic_id,
                "confidence": final_mastery_score / 100,
                "mastery_level": "advanced",
                "can_teach_others": True,
            })
        else:
            strengths = [
                {**s, "can_teach_others": True, "mastery_level": "advanced"}
                if s.get("topic_id") == topic_id else s
                for s in strengths
            ]
        await db.students.update_one(
            {"student_id": student_id},
            {"$set": {"mastery_profile.strengths": strengths}},
        )

    # Check if all topics mastered → Phase 11 completion
    student = await db.students.find_one({"student_id": student_id}, {"_id": 0})
    remaining_gaps = student.get("mastery_profile", {}).get("knowledge_gaps", [])

    if not remaining_gaps:
        from app.services.performance_service import generate_completion_report
        await db.students.update_one(
            {"student_id": student_id},
            {"$set": {"status": "complete"}},
        )
        report = await generate_completion_report(student_id)
        return {"verified": True, "student_complete": True, "completion_report": report}

    return {"verified": True, "student_complete": False, "topic_id": topic_id}
