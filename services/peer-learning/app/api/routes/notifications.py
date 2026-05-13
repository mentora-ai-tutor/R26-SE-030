
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any
from pydantic import BaseModel
from loguru import logger
from app.core.auth import TokenPayload, get_current_user
from app.core.database import get_db
from app.models.models import SessionStatus
from app.services.notification_service import (
    get_student_notifications,
    send_pairing_notification,
    send_queue_notification,
)


router = APIRouter(prefix="/api", tags=["Notifications & Queue"])


class WaitingQueueBody(BaseModel):
    student_id: str
    topic_id: str
    topic_name: str
    gap_type: str = "PARTIAL_GAP"
    attempts: int = 0


@router.get("/notifications", summary="Get notifications for the logged-in student")
async def get_my_notifications(
    current_user: TokenPayload = Depends(get_current_user),
) -> List[Dict]:
    """Retrieve all notifications for the authenticated student."""
    return await get_student_notifications(current_user.student_id)


@router.post("/notifications/{notification_id}/accept", summary="Accept a pairing notification (Join Session)")
async def accept_notification(
    notification_id: str,
    current_user: TokenPayload = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Mark a notification as accepted/read after the user clicks "Join Session".
    Activates the session immediately so the teacher can join right away.
    Returns the session_id so the frontend can redirect to the live room.
    """
    db = get_db()
    notif = await db.notifications.find_one(
        {"notification_id": notification_id, "student_id": current_user.student_id},
        {"_id": 0},
    )
    if not notif:
        raise HTTPException(status_code=404, detail="Notification not found")

    await db.notifications.update_one(
        {"notification_id": notification_id},
        {"$set": {"status": "read", "accepted_at": datetime.utcnow()}},
    )

    session_id = notif.get("session_id")
    role = notif.get("role")

    # When the teacher clicks "Start Session", activate the session immediately
    if session_id and role == "teacher":
        await db.pair_sessions.update_one(
            {"session_id": session_id, "status": SessionStatus.SCHEDULED.value},
            {
                "$set": {
                    "status": SessionStatus.ACTIVE.value,
                    "quiz_available": True,
                    "updated_at": datetime.utcnow(),
                }
            },
        )
        logger.info(f"Session {session_id} activated by teacher {current_user.student_id} via notification accept")

    logger.info(f"Notification {notification_id} accepted by {current_user.student_id}")

    return {
        "status": "accepted",
        "session_id": session_id,
        "role": role,
        "topic_name": notif.get("topic_name"),
        "session_ready": True,
    }


@router.post("/notifications/{notification_id}/read", summary="Mark notification as read")
async def mark_notification_read(
    notification_id: str,
    current_user: TokenPayload = Depends(get_current_user),
) -> Dict[str, Any]:
    """Mark a single notification as read."""
    db = get_db()
    result = await db.notifications.update_one(
        {"notification_id": notification_id, "student_id": current_user.student_id},
        {"$set": {"status": "read"}},
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Notification not found")
    return {"status": "read"}


@router.post("/notifications/read-all", summary="Mark all notifications as read")
async def mark_all_read(
    current_user: TokenPayload = Depends(get_current_user),
) -> Dict[str, Any]:
    """Mark all unread notifications for the student as read."""
    db = get_db()
    result = await db.notifications.update_many(
        {"student_id": current_user.student_id, "status": "unread"},
        {"$set": {"status": "read"}},
    )
    return {"status": "read", "modified_count": result.modified_count}
