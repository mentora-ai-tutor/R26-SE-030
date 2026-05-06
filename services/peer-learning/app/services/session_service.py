from datetime import datetime
from typing import Dict, Any, Optional, List
from loguru import logger
from app.core.database import get_db
from app.models.models import SessionStatus
from app.services.question_service import (
    generate_and_save_question,
    evaluate_answer,
    record_question_outcome,
    get_hint,
)
from app.utils.helpers import (
    get_next_bloom_level,
    is_mastery_achieved,
    calculate_learner_score,
    calculate_teacher_score,
    calculate_updated_mastery_score,
)


async def get_active_session_for_learner(learner_id: str) -> Optional[Dict]:
    """Return the active pair session where this student is the learner."""
    db = get_db()
    return await db.pair_sessions.find_one(
        {"learner_id": learner_id, "status": SessionStatus.ACTIVE.value},
        {"_id": 0},
    )


async def get_session(session_id: str) -> Optional[Dict]:
    db = get_db()
    return await db.pair_sessions.find_one({"session_id": session_id}, {"_id": 0})


async def get_all_active_sessions() -> List[Dict]:
    db = get_db()
    return await db.pair_sessions.find(
        {"status": SessionStatus.ACTIVE.value}, {"_id": 0}
    ).to_list(length=None)


async def start_session_question(session_id: str) -> Optional[Dict]:
    """Generate the first or next question for a session."""
    db = get_db()
    session = await db.pair_sessions.find_one({"session_id": session_id})
    if not session or session["status"] != SessionStatus.ACTIVE.value:
        return None

    # Find the learner's gap details for misconception info
    learner = await db.students.find_one({"student_id": session["learner_id"]}, {"_id": 0})
    gap = None
    if learner:
        for g in learner.get("mastery_profile", {}).get("knowledge_gaps", []):
            if g.get("topic_id") == session["topic_id"]:
                gap = g
                break

    misconception = gap.get("gap_type", "general gap") if gap else "general gap"
    current_mastery = gap.get("mastery_score", 0.0) if gap else 0.0

    # Find the last asked question's text to avoid repeating it
    previous_question_text = None
    question_log = session.get("question_log", [])
    if question_log:
        last_entry = question_log[-1]
        last_qid = last_entry.get("question_id")
        if last_qid:
            db2 = get_db()
            last_q = await db2.questions_bank.find_one({"question_id": last_qid}, {"_id": 0})
            if last_q:
                previous_question_text = last_q.get("question_text")

    question = await generate_and_save_question(
        topic_id=session["topic_id"],
        topic_name=session["topic_name"],
        bloom_level=session["current_bloom_level"],
        current_mastery=current_mastery,
        misconception=misconception,
        session_id=session_id,
        session_type="pair",
        previous_question_text=previous_question_text,
    )

    if not question:
        return None

    await db.pair_sessions.update_one(
        {"session_id": session_id},
        {
            "$set": {
                "current_question_id": question["question_id"],
                "updated_at": datetime.utcnow(),
            },
            "$inc": {"questions_asked": 1},
        },
    )

    return question


async def submit_answer(session_id: str, answer: str, time_taken: Optional[int]) -> Dict[str, Any]:
    """
    Process a learner's submitted answer.
    Returns result with next action.
    """
    db = get_db()
    session = await db.pair_sessions.find_one({"session_id": session_id})
    if not session:
        return {"error": "Session not found"}

    question_id = session.get("current_question_id")
    if not question_id:
        return {"error": "No active question"}

    # Evaluate answer
    evaluation = await evaluate_answer(question_id, answer)
    is_correct = evaluation.get("is_correct", False)

    # Record outcome
    hints_used = 0  # Track per-question hint usage separately if needed
    await record_question_outcome(question_id, is_correct, hints_used, time_taken)

    # Update bloom level progression
    consecutive_correct = session["consecutive_correct"]
    consecutive_incorrect = session["consecutive_incorrect"]

    if is_correct:
        consecutive_correct += 1
        consecutive_incorrect = 0
    else:
        consecutive_incorrect += 1
        consecutive_correct = 0

    current_level = session["current_bloom_level"]
    new_level = get_next_bloom_level(current_level, consecutive_correct, consecutive_incorrect)

    # Calculate and update mastery score immediately
    learner = await db.students.find_one({"student_id": session["learner_id"]}, {"_id": 0})
    previous_score = 0.0
    if learner:
        for g in learner.get("mastery_profile", {}).get("knowledge_gaps", []):
            if g.get("topic_id") == session["topic_id"]:
                previous_score = g.get("mastery_score", 0.0)
                break

    new_score = calculate_updated_mastery_score(
        previous_score=previous_score,
        is_correct=is_correct,
        bloom_level=current_level,
        consecutive_correct=consecutive_correct,
        consecutive_incorrect=consecutive_incorrect,
        time_taken_seconds=time_taken
    )

    await db.students.update_one(
        {"student_id": session["learner_id"], "mastery_profile.knowledge_gaps.topic_id": session["topic_id"]},
        {"$set": {"mastery_profile.knowledge_gaps.$.mastery_score": round(new_score, 2)}}
    )

    mastery_achieved = is_mastery_achieved(new_level, new_score)

    log_entry = {
        "question_id": question_id,
        "bloom_level": current_level,
        "correct": is_correct,
        "hints_used": 0,
        "time_taken_seconds": time_taken,
        "asked_teacher": False,
        "timestamp": datetime.utcnow(),
    }

    update = {
        "$set": {
            "current_bloom_level": new_level,
            "consecutive_correct": consecutive_correct,
            "consecutive_incorrect": consecutive_incorrect,
            "current_question_id": None,
            "updated_at": datetime.utcnow(),
        },
        "$push": {"question_log": log_entry},
    }
    if is_correct:
        update["$inc"] = {"correct_answers": 1}

    await db.pair_sessions.update_one({"session_id": session_id}, update)

    questions_asked = session.get("questions_asked", 1)
    session_completed_flag = mastery_achieved or questions_asked >= 5

    response = {
        "session_id": session_id,
        "is_correct": is_correct,
        "feedback": evaluation.get("feedback", ""),
        "bloom_level_before": current_level,
        "bloom_level_after": new_level,
        "consecutive_correct": consecutive_correct,
        "mastery_achieved": mastery_achieved,
        "current_mastery_score": round(new_score, 2),
        "questions_asked": questions_asked,
    }

    if session_completed_flag:
        # Trigger session completion
        result = await complete_session(session_id, final_mastery=new_score)
        response["session_completed"] = True
        response["performance"] = result
    else:
        response["next_action"] = "next_question"

    return response


async def request_hint(session_id: str, question_id: str) -> Dict[str, Any]:
    """Provide a hint for the current question."""
    db = get_db()
    session = await db.pair_sessions.find_one({"session_id": session_id})
    if not session:
        return {"error": "Session not found"}

    hints_used = session.get("hints_used_by_learner", 0)
    hint_index = hints_used  # 0, 1, 2

    if hint_index >= 3:
        return {"message": "Maximum hints reached", "hint": None}

    hint = await get_hint(question_id, hint_index)
    await db.pair_sessions.update_one(
        {"session_id": session_id},
        {"$inc": {"hints_used_by_learner": 1}},
    )

    return {"hint_index": hint_index + 1, "hint": hint, "hints_remaining": 2 - hint_index}





async def complete_session(session_id: str, final_mastery: Optional[float] = None) -> Dict[str, Any]:
    """
    Phase 4: Complete a session and calculate performance scores.
    Triggers Phase 5 (pool) and Phase 8 (teacher gaps) as needed.
    """
    db = get_db()
    session = await db.pair_sessions.find_one({"session_id": session_id})
    if not session:
        return {"error": "Session not found"}

    # Determine learner's final mastery for teacher score calculation
    if final_mastery is None:
        learner = await db.students.find_one({"student_id": session["learner_id"]}, {"_id": 0})
        final_mastery = 0.0
        if learner:
            for g in learner.get("mastery_profile", {}).get("knowledge_gaps", []):
                if g.get("topic_id") == session["topic_id"]:
                    final_mastery = g.get("mastery_score", 0.0)
                    break

    learner_score = final_mastery

    teacher_score = calculate_teacher_score(
        initial_mastery=session.get("learner_initial_mastery", 0.0),
        final_mastery=final_mastery,
    )

    # Determine outcome
    if learner_score >= 85:
        learner_outcome = "MASTERED"
    elif learner_score >= 50:
        learner_outcome = "CONTINUE"
    else:
        learner_outcome = "REGROUP"

    teacher_outcome = "NEEDS_IMPROVEMENT" if teacher_score < 50 else "OK"

    # Update session
    await db.pair_sessions.update_one(
        {"session_id": session_id},
        {
            "$set": {
                "status": SessionStatus.COMPLETED.value,
                "completed_at": datetime.utcnow(),
                "performance_score": learner_score,
                "teacher_score": teacher_score,
                "learner_outcome": learner_outcome,
                "teacher_outcome": teacher_outcome,
            }
        },
    )

    # Immediately release both students back to "active" status
    await _release_student(session["learner_id"])
    await _release_student(session["teacher_id"])

    # Set can_teach_others = False for the teacher's topic
    await db.students.update_one(
        {
            "student_id": session["teacher_id"],
            "mastery_profile.strengths.topic_id": session["topic_id"]
        },
        {
            "$set": {
                "mastery_profile.strengths.$.can_teach_others": False,
                "updated_at": datetime.utcnow()
            }
        }
    )

    # Mark the learner's knowledge gap as completed
    await db.students.update_one(
        {
            "student_id": session["learner_id"],
            "mastery_profile.knowledge_gaps.topic_id": session["topic_id"]
        },
        {
            "$set": {
                "mastery_profile.knowledge_gaps.$.completed": True,
                "updated_at": datetime.utcnow()
            }
        }
    )

    # Notify gap completed
    from app.services.notification_service import send_knowledge_gap_completed_notification
    await send_knowledge_gap_completed_notification(session["learner_id"], session["topic_name"], session_id)

    initial_mastery = session.get("learner_initial_mastery", 0.0)
    score_improvement = learner_score - initial_mastery

    result = {
        "session_id": session_id,
        "previous_mastery_score": round(initial_mastery, 2),
        "current_mastery_score": round(learner_score, 2),
        "score_improvement": round(score_improvement, 2),
        "bloom_level_before": session.get("initial_bloom_level", 1) if "initial_bloom_level" in session else 1,
        "bloom_level_after": session.get("current_bloom_level", 1),
        "learner_score": round(learner_score, 2),
        "teacher_score": round(teacher_score, 2),
        "learner_outcome": learner_outcome,
        "teacher_outcome": teacher_outcome,
    }

    # Phase 5: If mastered, add to improved pool and transition to verified pool
    if learner_outcome == "MASTERED":
        from app.services.pool_service import add_to_improved_pool, add_to_verified_pool
        await add_to_improved_pool(
            student_id=session["learner_id"],
            topic_id=session["topic_id"],
            topic_name=session["topic_name"],
            mastery_score=learner_score,
        )
        await add_to_verified_pool(
            student_id=session["learner_id"],
            topic_id=session["topic_id"],
            topic_name=session["topic_name"],
            final_mastery_score=learner_score,
        )
        result["next_action"] = "added_to_verified_pool"

    # Phase 8: Handle teacher gaps
    if teacher_outcome == "NEEDS_IMPROVEMENT":
        await _handle_teacher_needs_improvement(session["teacher_id"], session["topic_id"])
        result["teacher_action"] = "teacher_marked_for_improvement"
    else:
        await _handle_teacher_gaps_after_session(session["teacher_id"])

    return result


async def _release_student(student_id: str):
    db = get_db()
    await db.students.update_one(
        {"student_id": student_id},
        {
            "$set": {
                "current_session_id": None,
                "status": "active",
                "updated_at": datetime.utcnow(),
            }
        },
    )


async def _handle_teacher_needs_improvement(teacher_id: str, topic_id: str):
    """Mark teacher as needing improvement for a topic."""
    db = get_db()
    await db.students.update_one(
        {"student_id": teacher_id},
        {
            "$push": {
                "mastery_profile.knowledge_gaps": {
                    "topic": topic_id,
                    "topic_id": topic_id,
                    "gap_type": "PARTIAL_GAP",
                    "confidence": 0.7,
                    "mastery_score": 40.0,
                    "reason": "needs_improvement_as_teacher",
                }
            },
            # Disable teaching ability for this topic
            "$set": {"updated_at": datetime.utcnow()},
        },
    )
    # Remove can_teach_others for this topic
    student = await db.students.find_one({"student_id": teacher_id})
    if student:
        strengths = student.get("mastery_profile", {}).get("strengths", [])
        updated = []
        for s in strengths:
            if s.get("topic_id") == topic_id:
                s["can_teach_others"] = False
            updated.append(s)
        await db.students.update_one(
            {"student_id": teacher_id},
            {"$set": {"mastery_profile.strengths": updated}},
        )


async def _handle_teacher_gaps_after_session(teacher_id: str):
    """Phase 8: After teaching, check if teacher has their own gaps."""
    db = get_db()
    teacher = await db.students.find_one({"student_id": teacher_id}, {"_id": 0})
    if not teacher:
        return

    gaps = teacher.get("mastery_profile", {}).get("knowledge_gaps", [])
    if gaps and teacher.get("current_session_id") is None:
        logger.info(f"Teacher {teacher_id} has {len(gaps)} gaps, can now seek help")
        # Teacher will naturally be picked up by the pairing algorithm
        # as a learner for their own gaps in the next batch run
