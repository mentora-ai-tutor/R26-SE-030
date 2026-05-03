from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any
from pydantic import BaseModel
from app.core.auth import TokenPayload, get_current_user
from app.services.notification_service import (
    add_to_waiting_queue,
    get_student_notifications,
    accept_notification,
    cancel_notification,
)

router = APIRouter(prefix="/api", tags=["Notifications & Queue"])


class WaitingQueueBody(BaseModel):
    student_id: str
    topic_id: str
    topic_name: str
    gap_type: str = "PARTIAL_GAP"
    attempts: int = 0


@router.post("/waiting/add", summary="Add student to waiting queue")
async def add_to_queue(
    body: WaitingQueueBody,
    current_user: TokenPayload = Depends(get_current_user),
) -> Dict[str, Any]:
    return await add_to_waiting_queue(
        student_id=body.student_id,
        topic_id=body.topic_id,
        topic_name=body.topic_name,
        gap_type=body.gap_type,
        attempts=body.attempts,
    )


@router.get("/notifications/{student_id}", summary="Get notifications for a student")
async def get_notifications(
    student_id: str,
    current_user: TokenPayload = Depends(get_current_user),
) -> List[Dict]:
    return await get_student_notifications(student_id)


@router.post("/notifications/{notification_id}/accept", summary="Accept teacher notification")
async def accept(
    notification_id: str,
    current_user: TokenPayload = Depends(get_current_user),
) -> Dict[str, Any]:
    result = await accept_notification(notification_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/notifications/{notification_id}/cancel", summary="Cancel notification, return to queue")
async def cancel(
    notification_id: str,
    current_user: TokenPayload = Depends(get_current_user),
) -> Dict[str, Any]:
    result = await cancel_notification(notification_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result
