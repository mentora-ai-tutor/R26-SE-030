from datetime import datetime
from typing import List, Dict, Any
from loguru import logger
from app.core.database import get_db
from app.models.models import StudentImport, StudentDB, StudentStatus
from app.utils.helpers import sort_knowledge_gaps, mastery_level_to_score


async def import_students(students: List[StudentImport]) -> Dict[str, Any]:
    """
    Phase 1: Import students from JSON, initialize records.
    - Sort weaknesses: FUNDAMENTAL_GAP first
    - Set current_weak_topic
    - Initialize session_history, current_session_id
    """
    db = get_db()
    results = {"imported": 0, "updated": 0, "errors": [], "student_ids": []}

    for student_data in students:
        try:
            # Sort knowledge gaps: FUNDAMENTAL first, then by confidence desc
            gaps_raw = [g.model_dump() for g in student_data.mastery_profile.knowledge_gaps]
            sorted_gaps = sort_knowledge_gaps(gaps_raw)

            # Determine current_weak_topic (first gap after sorting)
            current_weak_topic = sorted_gaps[0]["topic_id"] if sorted_gaps else None

            # Build mastery profile with sorted gaps
            mastery_profile = student_data.mastery_profile.model_dump()
            mastery_profile["knowledge_gaps"] = sorted_gaps

            doc = {
                "student_id": student_data.student_id,
                "analysis_timestamp": student_data.analysis_timestamp or datetime.utcnow(),
                "data_sources": student_data.data_sources.model_dump() if student_data.data_sources else {},
                "mastery_profile": mastery_profile,
                "current_weak_topic": current_weak_topic,
                "current_session_id": None,
                "session_history": [],
                "improved_topics": [],
                "mastered_topics": [],
                "status": StudentStatus.ACTIVE,
                "initial_mastery_score": student_data.mastery_profile.overall_mastery_score,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
            }

            # Upsert
            existing = await db.students.find_one({"student_id": student_data.student_id})
            if existing:
                await db.students.update_one(
                    {"student_id": student_data.student_id},
                    {"$set": {**doc, "updated_at": datetime.utcnow()}},
                )
                results["updated"] += 1
            else:
                await db.students.insert_one(doc)
                results["imported"] += 1

            results["student_ids"].append(student_data.student_id)

        except Exception as e:
            logger.error(f"Error importing student {student_data.student_id}: {e}")
            results["errors"].append({"student_id": student_data.student_id, "error": str(e)})

    logger.info(f"Import complete: {results['imported']} new, {results['updated']} updated")
    return results


async def get_all_students() -> List[Dict]:
    db = get_db()
    cursor = db.students.find({}, {"_id": 0})
    return await cursor.to_list(length=None)


async def get_student(student_id: str) -> Dict | None:
    db = get_db()
    return await db.students.find_one({"student_id": student_id}, {"_id": 0})


async def get_student_weaknesses(student_id: str) -> List[Dict]:
    db = get_db()
    student = await db.students.find_one({"student_id": student_id}, {"_id": 0})
    if not student:
        return []
    return student.get("mastery_profile", {}).get("knowledge_gaps", [])


async def get_student_history(student_id: str) -> Dict:
    db = get_db()
    student = await db.students.find_one({"student_id": student_id}, {"_id": 0})
    if not student:
        return {}

    session_ids = student.get("session_history", [])
    pair_sessions = await db.pair_sessions.find(
        {"session_id": {"$in": session_ids}}, {"_id": 0}
    ).to_list(length=None)

    group_session_ids = []
    group_sessions = await db.group_sessions.find(
        {"members.student_id": student_id}, {"_id": 0}
    ).to_list(length=None)

    return {
        "student_id": student_id,
        "pair_sessions": pair_sessions,
        "group_sessions": group_sessions,
        "improved_topics": student.get("improved_topics", []),
        "mastered_topics": student.get("mastered_topics", []),
        "current_weak_topic": student.get("current_weak_topic"),
        "status": student.get("status"),
    }
