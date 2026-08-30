"""Sandbox coding-challenge endpoints.

Serves fresh, Gemini-authored + runtime-verified Java challenges so the sandbox can
rotate questions over time (e.g. while a GitHub repo review runs). Auth + envelope
mirror the other KAA routes.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Header, Query

from app.services.github_review_service import verify_student_from_authorization
from app.services.sandbox_challenge_generator import build_challenge_batch

router = APIRouter(prefix="/api/v1/sandbox", tags=["sandbox"])


@router.get("/challenges")
async def get_challenges(
    count: int = Query(3, ge=1, le=6),
    topics: Optional[str] = Query(None, description="Comma-separated topic filter"),
    authorization: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    """Return a fresh batch of coding challenges (easy -> hard), verified via the ai-engine."""
    student = await verify_student_from_authorization(authorization)
    topic_list = [t.strip() for t in topics.split(",") if t.strip()] if topics else None
    data = await build_challenge_batch(student, count=count, topics=topic_list)
    return {"status": "success", "data": data}
