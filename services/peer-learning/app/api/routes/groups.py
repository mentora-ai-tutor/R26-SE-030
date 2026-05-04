from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from app.core.auth import TokenPayload, get_current_user
from app.services.group_service import (
    form_group_session,
    get_group_session,
    submit_group_scores,
)

router = APIRouter(prefix="/api/groups", tags=["Group Sessions"])


class GroupScoreBody(BaseModel):
    student_id: str
    task_completion_score: float = Field(ge=0, le=100)
    collaboration_score: float = Field(ge=0, le=100)
    communication_score: float = Field(ge=0, le=100)


class FormGroupBody(BaseModel):
    topic_id: str


@router.post("/form", summary="Form group session from improved pool")
async def form_group(
    body: FormGroupBody,
    current_user: TokenPayload = Depends(get_current_user),
) -> Dict[str, Any]:
    result = await form_group_session(body.topic_id)
    if not result:
        raise HTTPException(status_code=400, detail="Could not form group session")
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/{session_id}", summary="Get group session details")
async def get_group(
    session_id: str,
    current_user: TokenPayload = Depends(get_current_user),
) -> Dict:
    session = await get_group_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Group session not found")
    return session


@router.post("/{session_id}/submit", summary="Submit role scores for group session")
async def submit_scores(
    session_id: str,
    body: GroupScoreBody,
    current_user: TokenPayload = Depends(get_current_user),
) -> Dict[str, Any]:
    session = await get_group_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Group session not found")
    return await submit_group_scores(
        session_id=session_id,
        student_id=body.student_id,
        task_completion=body.task_completion_score,
        collaboration=body.collaboration_score,
        communication=body.communication_score,
    )
