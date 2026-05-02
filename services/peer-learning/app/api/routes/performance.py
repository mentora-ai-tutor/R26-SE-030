from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from app.services.performance_service import (
    get_student_performance,
    get_student_topic_performance,
    generate_completion_report,
)
from app.services.question_service import (
    generate_and_save_question,
    evaluate_answer,
    get_question_bank,
)

router = APIRouter(tags=["Performance & Questions"])


# ─── Performance Endpoints ────────────────────────────────────────────────────

@router.get("/api/performance/{student_id}", summary="Get student overall performance")
async def performance(student_id: str) -> Dict[str, Any]:
    result = await get_student_performance(student_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get(
    "/api/performance/{student_id}/topic/{topic_id}",
    summary="Get student performance for a specific topic",
)
async def topic_performance(student_id: str, topic_id: str) -> Dict[str, Any]:
    return await get_student_topic_performance(student_id, topic_id)


@router.get(
    "/api/performance/{student_id}/completion",
    summary="Get completion report for a fully mastered student",
)
async def completion_report(student_id: str) -> Dict[str, Any]:
    return await generate_completion_report(student_id)


# ─── Questions Endpoints ──────────────────────────────────────────────────────

class GenerateQuestionBody(BaseModel):
    topic_id: str
    topic_name: str
    bloom_level: int = 1
    current_mastery: float = 0.0
    misconception: str = "general gap"
    session_id: str
    session_type: str = "pair"


class EvaluateAnswerBody(BaseModel):
    question_id: str
    student_answer: str


@router.post("/api/questions/generate", summary="Generate a new question via LLM")
async def generate_question(body: GenerateQuestionBody) -> Dict[str, Any]:
    question = await generate_and_save_question(
        topic_id=body.topic_id,
        topic_name=body.topic_name,
        bloom_level=body.bloom_level,
        current_mastery=body.current_mastery,
        misconception=body.misconception,
        session_id=body.session_id,
        session_type=body.session_type,
    )
    if not question:
        raise HTTPException(status_code=500, detail="Question generation failed")
    return question


@router.post("/api/questions/evaluate", summary="Evaluate a student answer via LLM")
async def evaluate(body: EvaluateAnswerBody) -> Dict[str, Any]:
    return await evaluate_answer(body.question_id, body.student_answer)


@router.get("/api/questions/bank/{topic_id}", summary="Get question bank for a topic")
async def question_bank(topic_id: str) -> List[Dict]:
    return await get_question_bank(topic_id)
