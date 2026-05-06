from datetime import datetime
from typing import Dict, Any, Optional, List
from loguru import logger
from app.core.database import get_db
from app.core.llm_client import llm_client
from app.utils.helpers import generate_question_id


async def generate_and_save_question(
    topic_id: str,
    topic_name: str,
    bloom_level: int,
    current_mastery: float,
    misconception: str,
    session_id: str,
    session_type: str = "pair",
    previous_question_text: Optional[str] = None,
) -> Optional[Dict]:
    """Generate a question via LLM and save to questions_bank."""
    db = get_db()

    raw = await llm_client.generate_question(
        topic=topic_name,
        bloom_level=bloom_level,
        current_mastery=current_mastery,
        misconception=misconception,
        topic_id=topic_id,
        previous_question_text=previous_question_text,
    )

    if not raw:
        return None

    question_id = generate_question_id()
    doc = {
        "question_id": question_id,
        "question_text": raw["question_text"],
        "bloom_level": bloom_level,
        "expected_answer": raw["expected_answer"],
        "hints": raw.get("hints", [])[:3],
        "time_limit_seconds": raw.get("time_limit_seconds", 120),
        "topic_id": topic_id,
        "topic_name": topic_name,
        "difficulty": bloom_level,
        "session_id": session_id,
        "session_type": session_type,
        "generated_by": "gemma4",
        "generated_at": datetime.utcnow(),
        "used_count": 1,
        "success_rate": 0.0,
        "average_hints_used": 0.0,
        "average_time_taken": 0.0,
        "flagged_for_review": False,
        "answer_records": [],
    }

    await db.questions_bank.insert_one(doc)
    doc.pop("_id", None)
    logger.info(f"Question {question_id} generated for topic={topic_name}, level={bloom_level}")
    return doc


async def get_question(question_id: str) -> Optional[Dict]:
    db = get_db()
    return await db.questions_bank.find_one({"question_id": question_id}, {"_id": 0})


async def get_hint(question_id: str, hint_index: int) -> Optional[str]:
    """Return a specific hint (0-indexed)."""
    doc = await get_question(question_id)
    if not doc:
        return None
    hints = doc.get("hints", [])
    if hint_index < len(hints):
        return hints[hint_index]
    return None


async def record_question_outcome(
    question_id: str, is_correct: bool, hints_used: int, time_taken: Optional[int]
):
    """Update question analytics after an answer."""
    db = get_db()
    doc = await db.questions_bank.find_one({"question_id": question_id})
    if not doc:
        return

    records = doc.get("answer_records", [])
    records.append({
        "is_correct": is_correct,
        "hints_used": hints_used,
        "time_taken": time_taken or 0,
        "recorded_at": datetime.utcnow(),
    })

    total = len(records)
    success_rate = sum(1 for r in records if r["is_correct"]) / total if total else 0
    avg_hints = sum(r["hints_used"] for r in records) / total if total else 0
    avg_time = sum(r["time_taken"] for r in records) / total if total else 0
    flagged = success_rate < 0.4 and total >= 5

    await db.questions_bank.update_one(
        {"question_id": question_id},
        {
            "$set": {
                "success_rate": round(success_rate, 3),
                "average_hints_used": round(avg_hints, 2),
                "average_time_taken": round(avg_time, 2),
                "flagged_for_review": flagged,
                "answer_records": records,
                "used_count": total,
            }
        },
    )


async def evaluate_answer(
    question_id: str, student_answer: str
) -> Dict[str, Any]:
    """Evaluate student answer using LLM."""
    doc = await get_question(question_id)
    if not doc:
        return {"is_correct": False, "feedback": "Question not found"}

    result = await llm_client.evaluate_answer(
        question_text=doc["question_text"],
        expected_answer=doc["expected_answer"],
        student_answer=student_answer,
        topic=doc["topic_name"],
    )
    return result


async def get_question_bank(topic_id: str) -> List[Dict]:
    db = get_db()
    cursor = db.questions_bank.find({"topic_id": topic_id}, {"_id": 0, "answer_records": 0})
    return await cursor.to_list(length=None)
