import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional
from loguru import logger
from app.core.database import get_db
from app.core.websocket_manager import manager
from app.utils.helpers import generate_notification_id

async def send_pairing_notification(
    student_id: str, 
    session_id: str, 
    topic_name: str, 
    role: str, 
    peer_id: str
) -> str:
    """
    Phase 4 & 5: Notify student that they have been paired for a session.
    Saves to DB and broadcasts via WebSocket.
    """
    db = get_db()
    notification_id = generate_notification_id()
    
    doc = {
        "notification_id": notification_id,
        "student_id": student_id,
        "type": "pairing_success",
        "message": f"Your peer learning session for {topic_name} is starting! You are paired as {role}.",
        "session_id": session_id,
        "topic_name": topic_name,
        "role": role,
        "peer_id": peer_id,
        "created_at": datetime.utcnow(),
        "status": "unread"
    }
    
    try:
        await db.notifications.insert_one(doc)
        logger.info(f"Pairing notification {notification_id} sent to {student_id}")
        
        # Broadcast via WebSocket
        await manager.broadcast(f"notif_{student_id}", {
            "type": "session_start",
            "notification_id": notification_id,
            "session_id": session_id,
            "topic_name": topic_name,
            "role": role,
            "peer_id": peer_id,
            "message": doc["message"]
        })
        return notification_id
    except Exception as e:
        logger.error(f"Failed to send pairing notification for {student_id}: {e}")
        return ""

async def send_queue_notification(
    student_id: str, 
    topic_name: str, 
    queue_id: str
) -> str:
    """
    Phase 6: Notify student that they have been added to the waiting queue.
    Saves to DB and broadcasts via WebSocket.
    """
    db = get_db()
    notification_id = generate_notification_id()
    
    doc = {
        "notification_id": notification_id,
        "student_id": student_id,
        "type": "queue_entry",
        "message": f"No immediate match found for {topic_name}. You've been added to the waiting queue.",
        "queue_id": queue_id,
        "topic_name": topic_name,
        "created_at": datetime.utcnow(),
        "status": "unread"
    }
    
    try:
        await db.notifications.insert_one(doc)
        logger.info(f"Queue notification {notification_id} sent to {student_id}")
        
        # Broadcast via WebSocket
        await manager.broadcast(f"notif_{student_id}", {
            "type": "queue_entry",
            "notification_id": notification_id,
            "queue_id": queue_id,
            "topic_name": topic_name,
            "message": doc["message"]
        })
        return notification_id
    except Exception as e:
        logger.error(f"Failed to send queue notification for {student_id}: {e}")
        return ""

async def get_student_notifications(student_id: str) -> List[Dict]:
    """Retrieve notifications for a student, sorted by newest first."""
    db = get_db()
    return await db.notifications.find(
        {"student_id": student_id},
        {"_id": 0}
    ).sort("created_at", -1).limit(50).to_list(length=None)
