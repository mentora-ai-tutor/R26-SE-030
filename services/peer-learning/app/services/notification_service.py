import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from loguru import logger
from app.core.database import get_db
from app.core.config import settings
from app.utils.helpers import (
    generate_notification_id,
    generate_queue_id,
    calculate_priority_score,
    calculate_compatibility_score,
)

# Background task reference
_background_task: Optional[asyncio.Task] = None


async def add_to_waiting_queue(
    student_id: str,
    topic_id: str,
    topic_name: str,
    gap_type: str,
    attempts: int = 0,
) -> Dict[str, Any]:
    """Phase 6: Add student to waiting queue when no teacher is available."""
    db = get_db()

    # Check if already waiting
    existing = await db.waiting_queue.find_one(
        {"student_id": student_id, "topic_id": topic_id, "status": "waiting"}
    )

    now = datetime.utcnow()
    priority = calculate_priority_score(gap_type, now, attempts)

    if existing:
        await db.waiting_queue.update_one(
            {"_id": existing["_id"]},
            {"$set": {"priority_score": priority, "attempts": attempts}},
        )
        return {"queued": True, "queue_id": existing["queue_id"], "priority": priority}

    queue_id = generate_queue_id()
    doc = {
        "queue_id": queue_id,
        "student_id": student_id,
        "topic_id": topic_id,
        "topic_name": topic_name,
        "gap_type": gap_type,
        "waiting_since": now,
        "priority_score": priority,
        "attempts": attempts,
        "status": "waiting",
    }
    await db.waiting_queue.insert_one(doc)
    logger.info(f"Student {student_id} added to waiting queue for topic {topic_id}, priority={priority:.1f}")
    return {"queued": True, "queue_id": queue_id, "priority": priority}


async def get_student_notifications(student_id: str) -> List[Dict]:
    db = get_db()
    now = datetime.utcnow()
    # Expire old notifications
    await db.notifications.update_many(
        {"student_id": student_id, "status": "pending", "expires_at": {"$lt": now}},
        {"$set": {"status": "expired"}},
    )
    return await db.notifications.find(
        {"student_id": student_id},
        {"_id": 0},
    ).sort("created_at", -1).limit(20).to_list(length=None)


async def accept_notification(notification_id: str) -> Dict[str, Any]:
    """Student accepts a teacher availability notification."""
    db = get_db()
    now = datetime.utcnow()
    notif = await db.notifications.find_one({"notification_id": notification_id})
    if not notif:
        return {"error": "Notification not found"}

    if notif["status"] != "pending":
        return {"error": f"Notification is {notif['status']}, not pending"}

    if notif["expires_at"] < now:
        await db.notifications.update_one(
            {"notification_id": notification_id},
            {"$set": {"status": "expired"}},
        )
        return {"error": "Notification has expired"}

    # Create session
    from app.services.pairing_service import _create_pair_session, _reserve_student
    from app.models.models import PairingType

    # Get learner info to get mastery
    student = await db.students.find_one({"student_id": notif["student_id"]}, {"_id": 0})
    gap = None
    if student:
        for g in student.get("mastery_profile", {}).get("knowledge_gaps", []):
            if g.get("topic_id") == notif["topic_id"]:
                gap = g
                break

    session = await _create_pair_session(
        teacher_id=notif["teacher_id"],
        learner_id=notif["student_id"],
        topic_id=notif["topic_id"],
        topic_name=notif["topic_name"],
        pairing_type=PairingType.ONE_WAY,
        learner_initial_mastery=gap.get("mastery_score", 0.0) if gap else 0.0,
    )
    await _reserve_student(notif["student_id"], session["session_id"])
    await _reserve_student(notif["teacher_id"], session["session_id"])

    # Update notification status
    await db.notifications.update_one(
        {"notification_id": notification_id},
        {"$set": {"status": "accepted", "session_id": session["session_id"]}},
    )

    # Remove from waiting queue
    await db.waiting_queue.update_one(
        {"student_id": notif["student_id"], "topic_id": notif["topic_id"]},
        {"$set": {"status": "matched"}},
    )

    return {
        "notification_id": notification_id,
        "session_id": session["session_id"],
        "status": "session_created",
    }


async def cancel_notification(notification_id: str) -> Dict[str, Any]:
    """Student cancels a notification and returns to queue with lower priority."""
    db = get_db()
    notif = await db.notifications.find_one({"notification_id": notification_id})
    if not notif:
        return {"error": "Notification not found"}

    await db.notifications.update_one(
        {"notification_id": notification_id},
        {"$set": {"status": "cancelled"}},
    )

    # Re-queue student with incremented attempts (lower priority bump rate)
    queue_entry = await db.waiting_queue.find_one(
        {"student_id": notif["student_id"], "topic_id": notif["topic_id"]}
    )
    attempts = (queue_entry.get("attempts", 0) + 1) if queue_entry else 1

    await add_to_waiting_queue(
        student_id=notif["student_id"],
        topic_id=notif["topic_id"],
        topic_name=notif["topic_name"],
        gap_type=queue_entry.get("gap_type", "PARTIAL_GAP") if queue_entry else "PARTIAL_GAP",
        attempts=attempts,
    )

    # Notify next best match
    await _notify_next_in_queue(notif["topic_id"], notif["teacher_id"])

    return {"notification_id": notification_id, "status": "cancelled", "re_queued": True}


async def _notify_next_in_queue(topic_id: str, teacher_id: str):
    """Find next best match from queue and send notification."""
    db = get_db()

    # Get teacher to check availability
    teacher = await db.students.find_one({"student_id": teacher_id}, {"_id": 0})
    if not teacher or teacher.get("current_session_id"):
        return

    # Get waiting students for topic, ordered by priority
    waiting = await db.waiting_queue.find(
        {"topic_id": topic_id, "status": "waiting"},
        {"_id": 0},
    ).sort("priority_score", -1).limit(10).to_list(length=None)

    if not waiting:
        return

    # Find best compatibility
    from app.services.pairing_service import _get_strength_for_topic, _get_gap_for_topic

    strength = _get_strength_for_topic(teacher, topic_id)
    if not strength:
        return

    best_student = None
    best_score = -1

    for entry in waiting:
        student = await db.students.find_one({"student_id": entry["student_id"]}, {"_id": 0})
        if not student or student.get("current_session_id"):
            continue
        gap = _get_gap_for_topic(student, topic_id)
        if not gap:
            continue

        score = calculate_compatibility_score(
            teacher_confidence=strength.get("confidence", 0.5),
            teacher_mastery_level=strength.get("mastery_level", "proficient"),
            gap_type=gap.get("gap_type", "PARTIAL_GAP"),
            learner_mastery_score=gap.get("mastery_score", 0.0),
            learner_confidence=gap.get("confidence", 0.5),
        )

        if score > settings.compatibility_threshold and score > best_score:
            best_score = score
            best_student = entry

    if best_student:
        await _send_notification(
            student_id=best_student["student_id"],
            teacher_id=teacher_id,
            topic_id=topic_id,
            topic_name=best_student.get("topic_name", topic_id),
        )


async def _send_notification(student_id: str, teacher_id: str, topic_id: str, topic_name: str):
    """Send a targeted notification to a specific student."""
    db = get_db()
    notification_id = generate_notification_id()
    expires_at = datetime.utcnow() + timedelta(seconds=settings.notification_ttl_seconds)

    doc = {
        "notification_id": notification_id,
        "student_id": student_id,
        "teacher_id": teacher_id,
        "topic_id": topic_id,
        "topic_name": topic_name,
        "message": f"A teacher is now available for {topic_name}! Click JOIN to start or CANCEL to wait longer.",
        "expires_at": expires_at,
        "status": "pending",
        "created_at": datetime.utcnow(),
    }
    await db.notifications.insert_one(doc)
    logger.info(f"Notification {notification_id} sent to student {student_id} for topic {topic_name}")
    return notification_id


async def background_matching_loop():
    """
    Phase 6: Background process that runs every N seconds.
    Checks for newly available teachers and matches waiting students.
    """
    db = get_db()
    logger.info("Background matching loop started")

    while True:
        try:
            await _run_matching_cycle(db)
        except Exception as e:
            logger.error(f"Background matching error: {e}")

        await asyncio.sleep(settings.waiting_queue_poll_interval)


async def _run_matching_cycle(db):
    """One cycle of the background matching process."""
    now = datetime.utcnow()

    # Expire old notifications
    expired = await db.notifications.update_many(
        {"status": "pending", "expires_at": {"$lt": now}},
        {"$set": {"status": "expired"}},
    )
    if expired.modified_count:
        logger.debug(f"Expired {expired.modified_count} notifications")

    # Get unique topic_ids with waiting students
    waiting_topics = await db.waiting_queue.distinct("topic_id", {"status": "waiting"})

    for topic_id in waiting_topics:
        # Find available teachers for this topic
        from app.services.pairing_service import get_available_teachers_for_topic
        teachers = await get_available_teachers_for_topic(topic_id)

        for teacher in teachers:
            # Check teacher doesn't already have a pending notification going out
            pending_notif = await db.notifications.find_one({
                "teacher_id": teacher["student_id"],
                "topic_id": topic_id,
                "status": "pending",
            })
            if pending_notif:
                continue

            await _notify_next_in_queue(topic_id, teacher["student_id"])


def start_background_matching():
    """Start the background matching task."""
    global _background_task
    loop = asyncio.get_event_loop()
    _background_task = loop.create_task(background_matching_loop())
    logger.info("Background matching task started")


def stop_background_matching():
    """Stop the background matching task."""
    global _background_task
    if _background_task:
        _background_task.cancel()
        logger.info("Background matching task stopped")
