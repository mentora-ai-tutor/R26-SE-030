# backend/services/import_service.py
from database import get_db
from datetime import datetime

async def import_student_profile(json_data: dict):
    """
    Takes the raw JSON from the Knowledge Analysis Agent
    and stores it in MongoDB students collection.
    """
    db = get_db()
    
    # Sort weaknesses: FUNDAMENTAL_GAP comes first (highest priority)
    weaknesses = json_data["mastery_profile"]["knowledge_gaps"]
    weaknesses.sort(key=lambda x: 0 if x["gap_type"] == "FUNDAMENTAL_GAP" else 1)
    
    student_doc = {
        "student_id": json_data["student_id"],
        "analysis_timestamp": json_data["analysis_timestamp"],
        "overall_mastery_score": json_data["mastery_profile"]["overall_mastery_score"],
        "weaknesses": weaknesses,
        "strengths": json_data["mastery_profile"]["strengths"],
        "recommendations": json_data["recommendations"],
        
        # System tracking fields (not in original JSON)
        "current_weak_topic": weaknesses[0]["topic_id"] if weaknesses else None,
        "verified_topics": [],
        "current_role": "learner",
        "current_session_id": None,
        "imported_at": datetime.utcnow()
    }
    
    # upsert = update if exists, insert if not
    await db.students.update_one(
        {"student_id": json_data["student_id"]},
        {"$set": student_doc},
        upsert=True
    )
    
    return student_doc