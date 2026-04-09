# backend/services/pairing_service.py
from database import get_db
from datetime import datetime
import uuid

async def find_teacher_for_topic(topic_id: str, exclude_student_id: str) -> dict | None:
    """
    MongoDB query: find a student who is strong in this topic,
    can teach others, and is not currently in an active session.
    """
    db = get_db()
    
    teacher = await db.students.find_one({
        # Must be strong in the topic and allowed to teach
        "strengths": {
            "$elemMatch": {
                "topic_id": topic_id,
                "can_teach_others": True
            }
        },
        # Must not be the learner themselves
        "student_id": {"$ne": exclude_student_id},
        # Must not be in an active session right now
        "current_session_id": None
    })
    
    return teacher

async def create_pair_session(learner_id: str, teacher_id: str, topic_id: str, topic_name: str) -> dict:
    """Creates a new pair session document in MongoDB."""
    db = get_db()
    
    session_id = f"PS-{uuid.uuid4().hex[:8].upper()}"
    
    session_doc = {
        "session_id": session_id,
        "teacher_id": teacher_id,
        "learner_id": learner_id,
        "topic_id": topic_id,
        "topic_name": topic_name,
        "status": "active",
        "created_at": datetime.utcnow(),
        "completed_at": None,
        "questions_asked": 0,
        "correct_answers": 0,
        "hints_used_by_learner": 0,
        "hints_used_by_teacher": 0,
        "help_requests": 0,
        "performance_score": None,
        "decision": None,
        "question_log": []
    }
    
    await db.pair_sessions.insert_one(session_doc)
    
    # Mark both students as busy
    await db.students.update_many(
        {"student_id": {"$in": [learner_id, teacher_id]}},
        {"$set": {"current_session_id": session_id}}
    )
    
    return session_doc

async def start_pairing_for_student(student_id: str) -> dict:
    """
    Main entry point: given a student, find their current weak topic,
    find a teacher for it, and create a session.
    """
    db = get_db()
    
    student = await db.students.find_one({"student_id": student_id})
    if not student:
        return {"error": "Student not found"}
    
    if student["current_session_id"]:
        return {"error": "Student already in a session"}
    
    topic_id = student["current_weak_topic"]
    if not topic_id:
        return {"message": "No weak topics remaining — student is complete!"}
    
    # Find the topic name from weaknesses list
    topic_name = next(
        (w["topic"] for w in student["weaknesses"] if w["topic_id"] == topic_id),
        topic_id
    )
    
    teacher = await find_teacher_for_topic(topic_id, student_id)
    if not teacher:
        return {"error": f"No available teacher for topic {topic_name} right now. Try again later."}
    
    session = await create_pair_session(
        learner_id=student_id,
        teacher_id=teacher["student_id"],
        topic_id=topic_id,
        topic_name=topic_name
    )
    
    return {
        "session_id": session["session_id"],
        "learner_id": student_id,
        "teacher_id": teacher["student_id"],
        "topic": topic_name
    }