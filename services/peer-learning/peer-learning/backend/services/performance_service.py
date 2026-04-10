# backend/services/performance_service.py
from database import get_db
from datetime import datetime
from services.group_service import trigger_group_session

async def calculate_session_score(session: dict) -> float:
    """
    Score formula:
      base = (correct_answers / questions_asked) * 100
      penalty = hints_used * 5 + help_requests * 10
      final = max(0, base - penalty)
    """
    if session["questions_asked"] == 0:
        return 0.0
    
    base = (session["correct_answers"] / session["questions_asked"]) * 100
    penalty = (session["hints_used_by_learner"] * 5) + (session["help_requests"] * 10)
    return max(0.0, round(base - penalty, 1))

async def decide_next_action(learner_id: str, topic_id: str, score: float) -> str:
    """
    Core decision logic:
      ≥90% → MASTERED (add to topic pool)
      <50% → REGROUP (find new teacher)
      else → CONTINUE (more practice with same teacher)
    """
    if score >= 90:
        return "MASTERED"
    elif score < 50:
        return "REGROUP"
    else:
        return "CONTINUE"

async def complete_pair_session(session_id: str) -> dict:
    """Called when a pair session ends. Updates MongoDB and triggers next step."""
    db = get_db()
    
    session = await db.pair_sessions.find_one({"session_id": session_id})
    score = await calculate_session_score(session)
    decision = await decide_next_action(session["learner_id"], session["topic_id"], score)
    
    # 1. Update the session document
    await db.pair_sessions.update_one(
        {"session_id": session_id},
        {"$set": {
            "status": "completed",
            "completed_at": datetime.utcnow(),
            "performance_score": score,
            "decision": decision
        }}
    )
    
    # 2. Free up both students
    await db.students.update_many(
        {"student_id": {"$in": [session["learner_id"], session["teacher_id"]]}},
        {"$set": {"current_session_id": None}}
    )
    
    # 3. Act on the decision
    if decision == "MASTERED":
        await add_to_topic_pool(session["learner_id"], session["topic_id"], session["topic_id"], score, session_id)
    
    elif decision == "REGROUP":
        # Clear current session, system will find new teacher
        await db.students.update_one(
            {"student_id": session["learner_id"]},
            {"$set": {"current_session_id": None}}
        )
        
        # If teacher used hints, mark them as no longer able to teach this topic directly safely (simulate performance drop)
        if session.get("hints_used_by_teacher", 0) > 0:
            await db.students.update_one(
                { "student_id": session["teacher_id"], "strengths.topic_id": session["topic_id"] },
                { "$set": { "strengths.$.can_teach_others": False } }
            )
    
    return {"session_id": session_id, "score": score, "decision": decision}

async def add_to_topic_pool(student_id: str, topic_id: str, topic_name: str, score: float, session_id: str):
    """Adds a student to the 'improved' topic pool after mastering in pair session."""
    db = get_db()
    
    # Add to topic pool
    await db.topic_pools.insert_one({
        "topic_id": topic_id,
        "topic_name": topic_name,
        "pool_type": "improved",
        "student_id": student_id,
        "added_at": datetime.utcnow(),
        "pair_session_id": session_id,
        "final_score": score
    })
    
    # Check if there are now 3+ students in the pool — trigger group session
    pool_count = await db.topic_pools.count_documents({
        "topic_id": topic_id,
        "pool_type": "improved"
    })
    
    if pool_count >= 3:
        await trigger_group_session(topic_id)

async def move_to_next_weak_topic(student_id: str):
    """After fully mastering a topic, find and assign the next weakest one."""
    db = get_db()
    
    student = await db.students.find_one({"student_id": student_id})
    verified = student.get("verified_topics", [])
    
    remaining = [
        w for w in student["weaknesses"]
        if w["topic_id"] not in verified
    ]
    # FUNDAMENTAL_GAP still first
    remaining.sort(key=lambda x: 0 if x["gap_type"] == "FUNDAMENTAL_GAP" else 1)
    
    if remaining:
        next_topic = remaining[0]["topic_id"]
        await db.students.update_one(
            {"student_id": student_id},
            {"$set": {"current_weak_topic": next_topic}}
        )
        return next_topic
    else:
        # All weak areas mastered!
        await db.students.update_one(
            {"student_id": student_id},
            {"$set": {"current_weak_topic": None, "status": "fully_mastered"}}
        )
        return None