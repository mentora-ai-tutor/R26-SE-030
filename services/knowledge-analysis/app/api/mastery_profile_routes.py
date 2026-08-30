from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status

from app.services.mastery_profile_store import get_latest_mastery_profile

router = APIRouter(prefix="/api/v1/mastery-profiles", tags=["mastery-profiles"])


@router.get("/{student_id}/latest")
async def get_latest_profile(student_id: str) -> dict[str, Any]:
    profile = await get_latest_mastery_profile(student_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No mastery profile found for this student",
        )
    return {"status": "success", "data": profile}
