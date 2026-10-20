import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Query

from app.agents.student_agent import generate_peer_coding_tasks
from app.api.student_routes import verify_jwt_student
from app.models.schemas import PeerMatchResponse
from app.services.mongodb import get_collection, save_peer_match, upsert_collab_room

logger = logging.getLogger("peer_routes")

router = APIRouter(prefix="/api/peer", tags=["Peer Matching"])


# ==========================================
# 1. Helper functions
# ==========================================

def _normalize_text(value) -> str:
    return str(value or "").strip().lower()


def _safe_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _iter_student_documents():
    """Read both saved student documents and imported mastery analyses."""
    students = []
    for collection_name in ["students", "student_analyses"]:
        try:
            collection = get_collection(collection_name)
            students.extend(list(collection.find({})))
        except Exception:
            pass
    return students


def _study_profile_from_document(student: dict):
    profile = student.get("mastery_profile") or {}
    if not isinstance(profile, dict):
        profile = {}
    return profile


def _extract_topic_entries(student: dict, section_name: str):
    """Support both the raw student save format and the imported mastery-analysis format."""
    entries = []

    direct = student.get(section_name)
    if direct is not None:
        entries.extend(_safe_list(direct))

    profile = _study_profile_from_document(student)
    if isinstance(profile, dict):
        entries.extend(_safe_list(profile.get(section_name)))

    request_data = student.get("request") or {}
    if isinstance(request_data, dict):
        request_profile = request_data.get("mastery_profile") or {}
        entries.extend(_safe_list(request_profile.get(section_name)))

    return entries


def _topic_from_entry(entry: dict) -> str:
    if not isinstance(entry, dict):
        return ""
    for key in ["topic", "name", "subject", "title"]:
        if entry.get(key):
            return str(entry.get(key))
    return ""


def _topic_score(entry: dict) -> float:
    if not isinstance(entry, dict):
        return 0.0
    for key in ["mastery_score", "score", "confidence", "strength_score", "gap_score"]:
        if key in entry:
            try:
                return float(entry.get(key))
            except (TypeError, ValueError):
                pass
    return 0.0


def _is_available(student: dict) -> bool:
    if "available_for_peer" in student:
        return bool(student.get("available_for_peer"))
    if "is_active" in student:
        return bool(student.get("is_active"))
    return True


def _is_student_in_active_session(student_id: str) -> bool:
    """Check if a student is currently in an active collaboration session."""
    try:
        active = get_collection("collab_rooms").find_one({
            "$or": [
                {"learner_student_id": student_id, "status": "in_progress"},
                {"peer_student_id": student_id, "status": "in_progress"},
            ]
        })
        return active is not None
    except Exception:
        return False


def _has_teacher_taught_topic(student_id: str, topic: str) -> bool:
    """Check if a student has already served as a teacher/helper for this topic."""
    try:
        target = _normalize_text(topic)
        record = get_collection("peer_teaching_history").find_one({
            "student_id": student_id,
            "topic": target,
        })
        return record is not None
    except Exception:
        return False


def _record_teaching_session(teacher_student_id: str, learner_student_id: str, topic: str, room_id: str):
    """Record that a teacher taught a specific topic to prevent re-teaching."""
    try:
        target = _normalize_text(topic)
        existing = get_collection("peer_teaching_history").find_one({
            "student_id": teacher_student_id,
            "topic": target,
        })
        if not existing:
            get_collection("peer_teaching_history").insert_one({
                "student_id": teacher_student_id,
                "learner_student_id": learner_student_id,
                "topic": target,
                "room_id": room_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })
    except Exception as e:
        logger.warning(f"Failed to record teaching session: {e}")


def _student_has_topic(student: dict, topic: str, section_name: str) -> bool:
    target = _normalize_text(topic)
    if not target:
        return False

    for entry in _extract_topic_entries(student, section_name):
        current = _normalize_text(_topic_from_entry(entry))
        if not current:
            continue
        if current == target or target in current or current in target:
            return True
    return False


def _resolve_topic_from_student(student: dict, fallback_topic: str | None = None) -> str:
    """Use the student's current learning gap if no topic is supplied."""
    for section in ["knowledge_gaps", "weak_subskills"]:
        entries = _extract_topic_entries(student, section)
        if entries:
            for entry in entries:
                topic_name = _topic_from_entry(entry)
                if topic_name:
                    return str(topic_name)

    recommendations = (student.get("recommendations") or {})
    if isinstance(recommendations, dict):
        priority_order = recommendations.get("priority_order") or []
        if isinstance(priority_order, list) and priority_order:
            first_topic = priority_order[0]
            if first_topic:
                return str(first_topic)

    if fallback_topic:
        return str(fallback_topic)

    return ""


def _best_helper_for_topic(students: list, topic: str, exclude_student_id: str):
    matches = []
    target = _normalize_text(topic)

    for student in students:
        if str(student.get("student_id")) == str(exclude_student_id):
            continue
        if not _is_available(student):
            continue

        student_id = str(student.get("student_id"))

        # Skip if student is currently in an active session
        if _is_student_in_active_session(student_id):
            continue

        # Skip if student has already taught this topic
        if _has_teacher_taught_topic(student_id, target):
            continue

        for entry in _extract_topic_entries(student, "strengths"):
            current_topic = _normalize_text(_topic_from_entry(entry))
            if not current_topic:
                continue
            if current_topic == target or target in current_topic or current_topic in target:
                score = _topic_score(entry)
                if score <= 0:
                    score = 85.0
                matches.append({
                    "student_id": student_id,
                    "name": str(student.get("name") or "Student"),
                    "topic": _topic_from_entry(entry),
                    "strength_score": score,
                    "match_score": round(min(max(score / 100, 0.5), 0.99), 2),
                })

    if not matches:
        return None
    matches.sort(key=lambda item: item["strength_score"], reverse=True)
    return matches[0]


def _best_learner_for_topic(students: list, topic: str, exclude_student_id: str):
    matches = []
    target = _normalize_text(topic)

    for student in students:
        if str(student.get("student_id")) == str(exclude_student_id):
            continue
        if not _is_available(student):
            continue

        student_id = str(student.get("student_id"))
        if _is_student_in_active_session(student_id):
            continue

        for entry in _extract_topic_entries(student, "knowledge_gaps"):
            current_topic = _normalize_text(_topic_from_entry(entry))
            if not current_topic:
                continue
            if current_topic == target or target in current_topic or current_topic in target:
                score = _topic_score(entry)
                if score <= 0:
                    score = 65.0
                matches.append({
                    "student_id": str(student.get("student_id")),
                    "name": str(student.get("name") or "Student"),
                    "topic": _topic_from_entry(entry),
                    "gap_score": score,
                    "match_score": round(min(max((100 - score) / 100, 0.4), 0.95), 2),
                })

    if not matches:
        return None
    matches.sort(key=lambda item: item["gap_score"], reverse=True)
    return matches[0]


def _create_match_notification(
    recipient_student_id: str,
    sender_student_id: str,
    sender_name: str,
    room_id: str,
    topic: str,
    recipient_role: str,
    match_score: float,
) -> str:
    """Create a peer-match notification and return the notification ID."""
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "student_id": recipient_student_id,
        "type": "peer_match",
        "matched_student_id": sender_student_id,
        "matched_student_name": sender_name,
        "room_id": room_id,
        "topic": topic,
        "role": recipient_role,
        "match_score": match_score,
        "status": "unread",
        "created_at": now,
    }
    result = get_collection("peer_notifications").insert_one(doc)
    return str(result.inserted_id)


def _extract_learner_gap_details(student: dict, topic: str) -> dict:
    """Extract the learner's knowledge gap, weak subskill, mastery score, and
    misconception for the matched topic — used to generate a coding task."""
    mastery_score = 0
    subskill = ""
    misconception = ""

    profile = student.get("mastery_profile") or {}
    if isinstance(profile, dict):
        mastery_score = profile.get("overall_mastery_score", 0)

    for gap in _extract_topic_entries(student, "knowledge_gaps"):
        gap_topic = _normalize_text(_topic_from_entry(gap))
        if not gap_topic:
            continue
        if gap_topic == _normalize_text(topic) or _normalize_text(topic) in gap_topic or gap_topic in _normalize_text(topic):
            mastery_score = gap.get("mastery_score", mastery_score)
            misconceptions = gap.get("misconceptions") or []
            if misconceptions and isinstance(misconceptions, list):
                misconception = misconceptions[0]
            weak_subskills = gap.get("weak_subskills") or []
            if weak_subskills and isinstance(weak_subskills, list):
                first_weak = weak_subskills[0]
                if isinstance(first_weak, dict):
                    subskill = first_weak.get("subskill", "")
                else:
                    subskill = str(first_weak)
            if subskill:
                break

    if not subskill:
        for entry in _extract_topic_entries(student, "knowledge_gaps"):
            topic_name = _topic_from_entry(entry)
            if topic_name:
                subskill = topic_name
                break

    return {
        "topic": topic,
        "subskill": subskill or topic,
        "mastery_score": mastery_score,
        "misconception": misconception or None,
    }


# ==========================================
# 2. Peer Match Endpoint
# ==========================================

@router.post("/match", response_model=PeerMatchResponse)
def match_peer(
    token_student_id: str = Depends(verify_jwt_student),
):
    """
    Finds a complementary peer pair using a strength-vs-gap model.
    When a match is found, BOTH students receive a notification with
    the room_id so they can join the live collaboration room.
    """
    student_id = token_student_id
    request_topic = None
    target_role = "peer_learner"

    try:
        if _is_student_in_active_session(student_id):
            response = PeerMatchResponse(
                status="no_match",
                matched_peer_id=None,
                match_score=0.0,
                message="You are already in an active collaboration session. Complete or leave it before starting a new match."
            )
            return response

        students = _iter_student_documents()

        target_student = next(
            (student for student in students if str(student.get("student_id")) == str(student_id)),
            None,
        )

        if target_student is None:
            response = PeerMatchResponse(
                status="no_match",
                matched_peer_id=None,
                match_score=0.0,
                message="No available peer match found for this student right now."
            )
            save_peer_match({
                "student_id": student_id,
                "topic": request_topic,
                "target_role": target_role,
                "matched_peer_id": None,
                "match_score": 0.0,
                "result": response.model_dump(),
            })
            return response

        if not request_topic:
            request_topic = _resolve_topic_from_student(target_student)

        if not request_topic:
            response = PeerMatchResponse(
                status="no_match",
                matched_peer_id=None,
                match_score=0.0,
                message="No learning gap was found for this student, so no peer tutor match can be suggested."
            )
            save_peer_match({
                "student_id": student_id,
                "topic": request_topic,
                "target_role": target_role,
                "matched_peer_id": None,
                "match_score": 0.0,
                "result": response.model_dump(),
            })
            return response

        target_has_gap = _student_has_topic(target_student, request_topic, "knowledge_gaps")
        target_has_strength = _student_has_topic(target_student, request_topic, "strengths")

        best_match = None
        match_role = "peer"

        if target_has_gap:
            best_match = _best_helper_for_topic(students, request_topic, student_id)
            match_role = "helper"
        elif target_has_strength:
            best_match = _best_learner_for_topic(students, request_topic, student_id)
            match_role = "learner"

        if best_match is None:
            response = PeerMatchResponse(
                status="no_match",
                matched_peer_id=None,
                match_score=0.0,
                message=(
                    f"No available peer match found for '{request_topic}'. "
                    f"A helper/learner pairing is not available right now."
                )
            )
            save_peer_match({
                "student_id": student_id,
                "topic": request_topic,
                "target_role": target_role,
                "matched_peer_id": None,
                "match_score": 0.0,
                "result": response.model_dump(),
            })
            return response

        room_id = f"PEER_{student_id}_{best_match['student_id']}_{uuid.uuid4().hex[:6].upper()}"

        gap_details = _extract_learner_gap_details(target_student, request_topic)

        coding_tasks = generate_peer_coding_tasks(
            topic=gap_details["topic"],
            subskill=gap_details["subskill"],
            mastery_score=gap_details["mastery_score"],
            misconception=gap_details["misconception"],
        )

        first_starter_code = (
            coding_tasks[0].get("starter_code", "")
            if coding_tasks
            else "// Start coding Java here..."
        )
        requester_name = str(target_student.get("name") or "Student")
        helper_name = best_match["name"]

        upsert_collab_room(
            room_id=room_id,
            code=first_starter_code,
            active_users=0,
        )

        get_collection("collab_rooms").update_one(
            {"room_id": room_id},
            {"$set": {
                "coding_tasks": coding_tasks,
                "current_task_index": 0,
                "current_task": 1,
                "status": "in_progress",
                "attempts": 0,
                "passed": False,
                "task_progress": [
                    {
                        "task_number": index + 1,
                        "task_type": task.get("task_type", ""),
                        "status": "available" if index == 0 else "locked",
                        "attempts": 0,
                        "passed": False,
                    }
                    for index, task in enumerate(coding_tasks)
                ],
                "learner_student_id": student_id,
                "peer_student_id": best_match["student_id"],
                "learner_name": requester_name,
                "peer_name": helper_name,
                "topic": request_topic,
                "target_subskill": gap_details["subskill"],
            }},
        )

        notif_for_requester = _create_match_notification(
            recipient_student_id=student_id,
            sender_student_id=best_match["student_id"],
            sender_name=helper_name,
            room_id=room_id,
            topic=request_topic,
            recipient_role="learner",
            match_score=best_match["match_score"],
        )

        notif_for_peer = _create_match_notification(
            recipient_student_id=best_match["student_id"],
            sender_student_id=student_id,
            sender_name=requester_name,
            room_id=room_id,
            topic=request_topic,
            recipient_role=match_role,
            match_score=best_match["match_score"],
        )

        response = PeerMatchResponse(
            status="success",
            matched_peer_id=best_match["student_id"],
            match_score=best_match["match_score"],
            message=(
                f"Matched with {helper_name} ({best_match['student_id']}) for '{request_topic}' as a "
                f"{match_role} partner. Both students have been notified. "
                f"Join room '{room_id}' to start collaborating."
            ),
            room_id=room_id,
            notification_id=notif_for_requester,
        )

        save_peer_match({
            "student_id": student_id,
            "topic": request_topic,
            "target_role": target_role,
            "matched_peer_id": best_match["student_id"],
            "match_score": best_match["match_score"],
            "result": response.model_dump(),
            "match_role": match_role,
            "room_id": room_id,
            "notification_ids": [notif_for_requester, notif_for_peer],
        })

        _record_teaching_session(
            teacher_student_id=best_match["student_id"],
            learner_student_id=student_id,
            topic=request_topic,
            room_id=room_id,
        )

        return response

    except Exception as e:
        logger.warning(f"Peer matching failed: {e}")
        response = PeerMatchResponse(
            status="no_match",
            matched_peer_id=None,
            match_score=0.0,
            message="No available peer match found for this student right now."
        )

        save_peer_match({
            "student_id": student_id,
            "topic": request_topic,
            "target_role": target_role,
            "matched_peer_id": None,
            "match_score": 0.0,
            "result": response.model_dump(),
            "error": str(e),
        })

        return response


# ==========================================
# 3. Notification Endpoints
# ==========================================

@router.get("/notifications")
def get_peer_notifications(
    status: str = Query(default="unread", pattern="^(unread|read|all)$"),
    since: Optional[str] = Query(default=None, description="ISO timestamp — only return notifications created after this time"),
    token_student_id: str = Depends(verify_jwt_student),
):
    """
    Returns notifications for the authenticated student.
    Use ?status=unread (default), ?status=read, or ?status=all.
    Optional ?since=<ISO timestamp> to poll efficiently — returns only new notifications.
    """
    try:
        query: dict = {"student_id": token_student_id}
        if status != "all":
            query["status"] = status
        if since:
            query["created_at"] = {"$gt": since}

        notifications = list(
            get_collection("peer_notifications").find(
                query,
                sort=[("created_at", -1)],
            )
        )
        for n in notifications:
            n["_id"] = str(n["_id"])

        unread_count = get_collection("peer_notifications").count_documents(
            {"student_id": token_student_id, "status": "unread"}
        )

        return {
            "status": "success",
            "total": len(notifications),
            "unread_count": unread_count,
            "notifications": notifications,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch notifications: {str(e)}",
        )


@router.post("/notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: str,
    token_student_id: str = Depends(verify_jwt_student),
):
    """Mark a single notification as read."""
    try:
        notif = get_collection("peer_notifications").find_one(
            {"_id": ObjectId(notification_id), "student_id": token_student_id}
        )
        if not notif:
            raise HTTPException(status_code=404, detail="Notification not found.")

        get_collection("peer_notifications").update_one(
            {"_id": ObjectId(notification_id)},
            {"$set": {"status": "read", "read_at": datetime.now(timezone.utc).isoformat()}},
        )

        return {"status": "success", "message": "Notification marked as read."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to mark notification as read: {str(e)}",
        )


@router.post("/notifications/read-all")
def mark_all_notifications_read(
    token_student_id: str = Depends(verify_jwt_student),
):
    """Mark all unread notifications as read for the authenticated student."""
    try:
        result = get_collection("peer_notifications").update_many(
            {"student_id": token_student_id, "status": "unread"},
            {"$set": {"status": "read", "read_at": datetime.now(timezone.utc).isoformat()}},
        )

        return {
            "status": "success",
            "message": f"Marked {result.modified_count} notification(s) as read.",
            "modified_count": result.modified_count,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to mark notifications as read: {str(e)}",
        )


@router.post("/notifications/{notification_id}/unread")
def mark_notification_unread(
    notification_id: str,
    token_student_id: str = Depends(verify_jwt_student),
):
    """Mark a single notification as unread."""
    try:
        notif = get_collection("peer_notifications").find_one(
            {"_id": ObjectId(notification_id), "student_id": token_student_id}
        )
        if not notif:
            raise HTTPException(status_code=404, detail="Notification not found.")

        get_collection("peer_notifications").update_one(
            {"_id": ObjectId(notification_id)},
            {"$set": {"status": "unread"}},
        )

        return {"status": "success", "message": "Notification marked as unread."}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to mark notification as unread: {str(e)}",
        )
