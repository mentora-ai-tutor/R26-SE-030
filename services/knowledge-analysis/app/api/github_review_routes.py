from __future__ import annotations

from typing import Any, Literal, Optional

from bson import ObjectId
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, status
from pydantic import BaseModel, Field

from app.db.database import get_database
from app.services.github_review_service import (
    LLM_CHOICES,
    MAX_REPOS,
    build_repo_selection,
    get_student_github_credential,
    ollama_available,
    process_review_job,
    run_single_repo_rereview,
    serialize_job,
    start_review_job,
    verify_student_from_authorization,
)

router = APIRouter(prefix="/api/v1/github-review", tags=["github-review"])

LlmChoice = Literal["gemini", "ollama"]


class ReviewTopFiveRequest(BaseModel):
    repos: Optional[list[str]] = Field(
        default=None,
        description="Optional selected repository full_names. If omitted, the deterministic top five are used.",
        max_length=MAX_REPOS,
    )
    llm: LlmChoice = Field(
        default="gemini",
        description="Which LLM engine to run the review with. 'ollama' pins to the local model.",
    )


class ReReviewRequest(BaseModel):
    repo: str = Field(..., min_length=1, max_length=260)
    llm: LlmChoice = Field(default="gemini")


async def _auth_context(authorization: Optional[str]):
    student = await verify_student_from_authorization(authorization)
    credential = await get_student_github_credential(student)
    return student, credential


@router.get("/llm-options")
async def llm_options() -> dict[str, Any]:
    """
    Report which LLM engines the review UI may offer.

    Gemini is always available (it is the managed default). Ollama is only
    offered when the configured local server actually answers a health check,
    so the frontend can disable it instead of letting a review error out.
    """
    return {
        "status": "success",
        "data": {
            "providers": list(LLM_CHOICES),
            "default": "gemini",
            "ollama_available": await ollama_available(),
        },
    }


@router.post("/select-repos")
async def select_repos(authorization: Optional[str] = Header(default=None)) -> dict[str, Any]:
    """
    Return eligible GitHub repositories and the deterministic five-repo selection.

    The browser sends only the Mentora JWT. This service retrieves the GitHub
    token internally from user-service after verifying that JWT.
    """
    student, credential = await _auth_context(authorization)
    return {
        "status": "success",
        "data": await build_repo_selection(student, credential),
    }


@router.post("/review-top-5")
async def review_top_five(
    background_tasks: BackgroundTasks,
    payload: Optional[ReviewTopFiveRequest] = None,
    authorization: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    """
    Start a review for up to five repositories and persist one RepoReviewJob
    document. The review continues in the background and can be recovered via
    /status/{job_id}.
    """
    student, credential = await _auth_context(authorization)
    llm_choice = payload.llm if payload else "gemini"
    job, selected = await start_review_job(
        student=student,
        credential=credential,
        selected_full_names=payload.repos if payload else None,
        llm_choice=llm_choice,
    )
    background_tasks.add_task(
        process_review_job,
        job_id=job["job_id"],
        credential=credential,
        selected_repos=selected,
        llm_choice=llm_choice,
    )
    return {"status": "success", "data": job}


@router.get("/status/{job_id}")
async def review_status(
    job_id: str,
    authorization: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    student = await verify_student_from_authorization(authorization)
    if not ObjectId.is_valid(job_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid job id")

    db = get_database()
    job = await db.repo_review_jobs.find_one(
        {"_id": ObjectId(job_id), "student_id": student.id}
    )
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review job not found")

    return {"status": "success", "data": serialize_job(job)}


@router.post("/re-review")
async def re_review(
    payload: ReReviewRequest,
    authorization: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    student, credential = await _auth_context(authorization)
    job = await run_single_repo_rereview(
        student=student,
        credential=credential,
        repo_full_name=payload.repo,
        llm_choice=payload.llm,
    )
    return {"status": "success", "data": job}
