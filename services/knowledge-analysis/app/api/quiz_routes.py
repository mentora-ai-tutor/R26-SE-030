"""Adaptive Java quiz endpoints.

A student-facing skill check that runs *alongside* the GitHub repo review (or stand
alone in the sandbox). Difficulty ramps simple -> hard based on answers.

Auth mirrors the repo-review routes: the browser sends only the Mentora JWT, which we
verify via user-service. Responses use the shared ``{"status","data"}`` envelope so the
frontend ``unwrap`` helper works unchanged.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException, Query, status

from app.models.quiz import AnswerQuizRequest, StartQuizRequest
from app.services import quiz_store
from app.services.github_review_service import verify_student_from_authorization

router = APIRouter(prefix="/api/v1/quiz", tags=["quiz"])


@router.post("/session")
async def start_session(
    payload: Optional[StartQuizRequest] = None,
    authorization: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    """Start a skill-check session and return the first (easy) question."""
    student = await verify_student_from_authorization(authorization)
    data = await quiz_store.create_session(student, payload or StartQuizRequest())
    return {"status": "success", "data": data}


@router.post("/session/{session_id}/answer")
async def answer_question(
    session_id: str,
    payload: AnswerQuizRequest,
    authorization: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    """Grade the current answer, adapt difficulty, and return the next question (or results)."""
    student = await verify_student_from_authorization(authorization)
    data = await quiz_store.answer_question(student, session_id, payload)
    return {"status": "success", "data": data}


@router.get("/session/{session_id}")
async def get_session(
    session_id: str,
    authorization: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    """Recover session state (pending question + running results)."""
    student = await verify_student_from_authorization(authorization)
    data = await quiz_store.get_session_view(student, session_id)
    return {"status": "success", "data": data}


# ---- Cross-team result reads -------------------------------------------------
# Open reads by student id, mirroring the mastery-profile read endpoints, so other
# services/agents can consume MCQ outcomes. (Internal-key enforcement on KAA read
# endpoints is a known, tracked gap — see ARCHITECTURE.md §9.) The shape is
# ``models.quiz.QuizResultRecord``; ``topic_performance`` feeds POST /analyze directly.
@router.get("/results/{student_id}/latest")
async def latest_quiz_result(student_id: str) -> dict[str, Any]:
    """Latest completed quiz result for a student (public or internal student id)."""
    data = await quiz_store.get_latest_result(student_id)
    if data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No completed quiz results found for this student",
        )
    return {"status": "success", "data": data}


@router.get("/results/{student_id}")
async def list_quiz_results(
    student_id: str,
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    """Recent completed quiz results for a student, newest first.

    ``data`` is a (possibly empty) list of result records — a collection, so an empty
    list returns 200, whereas ``/latest`` returns 404 when the student has no results.
    """
    results = await quiz_store.list_results(student_id, limit=limit)
    return {"status": "success", "data": results}
