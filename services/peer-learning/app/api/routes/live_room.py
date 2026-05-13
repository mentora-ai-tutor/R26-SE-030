from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Depends, HTTPException
from typing import Dict, Any, Optional
from loguru import logger
from app.core.auth import TokenPayload, get_current_user
from app.core.database import get_db
from app.models.models import SessionStatus
from app.services.live_room_service import live_room_service
from app.services.session_service import get_active_session_for_learner, get_session, activate_session_if_scheduled

router = APIRouter(prefix="/api/live-room", tags=["Live Room"])


async def _check_session_ready(session_id: str, role: str) -> Dict[str, Any]:
    """Check if a session is ready for joining. Returns the session with readiness info."""
    db = get_db()
    session = await db.pair_sessions.find_one({"session_id": session_id}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    status = session.get("status")
    scheduled_at = session.get("scheduled_at")

    if status == SessionStatus.COMPLETED.value:
        raise HTTPException(status_code=400, detail="Session already completed")

    if status == SessionStatus.SCHEDULED.value:
        now = datetime.utcnow()
        if scheduled_at and scheduled_at > now:
            remaining_seconds = int((scheduled_at - now).total_seconds())
            return {
                "ready": False,
                "status": "scheduled",
                "scheduled_at": scheduled_at.isoformat(),
                "remaining_seconds": remaining_seconds,
                "message": f"Session starts in {remaining_seconds} seconds",
                "session_id": session_id,
                "session": session,
            }
        await activate_session_if_scheduled(session_id)
        session = await db.pair_sessions.find_one({"session_id": session_id}, {"_id": 0})

    return {"ready": True, "status": "active", "session_id": session_id, "session": session}


@router.get("/{session_id}", summary="Get live room details")
async def get_live_room(
    session_id: str,
    current_user: TokenPayload = Depends(get_current_user),
) -> Dict[str, Any]:
    room = await live_room_service.get_room(session_id)
    if not room:
        session = await get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        room = await live_room_service.create_room(session_id)
        if not room:
            raise HTTPException(status_code=400, detail="Could not create live room")
    return room


@router.get("/{session_id}/ready", summary="Check if session is ready")
async def check_session_ready(
    session_id: str,
    current_user: TokenPayload = Depends(get_current_user),
) -> Dict[str, Any]:
    result = await _check_session_ready(session_id, current_user.role)
    return result


@router.post("/{session_id}/join", summary="Join a live room")
async def join_live_room(
    session_id: str,
    current_user: TokenPayload = Depends(get_current_user),
) -> Dict[str, Any]:
    readiness = await _check_session_ready(session_id, current_user.role)
    if not readiness["ready"]:
        return readiness

    room = await live_room_service.join_room(session_id, current_user.student_id)
    if not room:
        raise HTTPException(status_code=404, detail="Could not join live room")
    return room


@router.post("/{session_id}/leave", summary="Leave a live room")
async def leave_live_room(
    session_id: str,
    current_user: TokenPayload = Depends(get_current_user),
) -> Dict[str, Any]:
    success = await live_room_service.leave_room(session_id, current_user.student_id)
    if not success:
        raise HTTPException(status_code=404, detail="Live room not found")
    return {"status": "left", "session_id": session_id}


@router.post("/{session_id}/close", summary="Close a live room")
async def close_live_room(
    session_id: str,
    current_user: TokenPayload = Depends(get_current_user),
) -> Dict[str, Any]:
    success = await live_room_service.close_room(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Live room not found")
    return {"status": "closed", "session_id": session_id}


@router.get("/{session_id}/screen-share", summary="Get current screen sharing state")
async def get_screen_share_state(
    session_id: str,
    current_user: TokenPayload = Depends(get_current_user),
) -> Dict[str, Any]:
    room = await live_room_service.get_room(session_id)
    if not room:
        raise HTTPException(status_code=404, detail="Live room not found")
    state = live_room_service.get_screen_share_state(session_id)
    return {
        "session_id": session_id,
        "is_sharing": state.get("is_sharing", False),
        "sharer_id": state.get("sharer_id"),
        "sharer_role": next(
            (p["role"] for p in room.get("participants", []) if p["student_id"] == state.get("sharer_id")),
            None,
        ) if state.get("sharer_id") else None,
    }


@router.get("/{session_id}/members", summary="Get live room members")
async def get_live_room_members(
    session_id: str,
    current_user: TokenPayload = Depends(get_current_user),
) -> Dict[str, Any]:
    room = await live_room_service.get_room(session_id)
    if not room:
        raise HTTPException(status_code=404, detail="Live room not found")
    return {
        "session_id": session_id,
        "participants": room.get("participants", []),
    }


@router.post("/my/room", summary="Get or create live room for authenticated user's active session")
async def my_live_room(
    current_user: TokenPayload = Depends(get_current_user),
) -> Dict[str, Any]:
    session = await get_active_session_for_learner(current_user.student_id)
    if not session:
        session = await get_session_for_teacher(current_user.student_id)
    if not session:
        raise HTTPException(status_code=404, detail="No active session found")

    readiness = await _check_session_ready(session["session_id"], current_user.role)
    if not readiness["ready"]:
        return readiness

    room = await live_room_service.get_room(session["session_id"])
    if not room:
        room = await live_room_service.create_room(session["session_id"])
    if not room:
        raise HTTPException(status_code=400, detail="Could not create live room")

    await live_room_service.join_room(session["session_id"], current_user.student_id)
    return room


async def get_session_for_teacher(teacher_id: str) -> Optional[Dict]:
    db = get_db()
    return await db.pair_sessions.find_one(
        {"teacher_id": teacher_id, "status": {"$in": [SessionStatus.ACTIVE.value, SessionStatus.SCHEDULED.value]}},
        {"_id": 0}
    )


@router.websocket("/ws/{session_id}")
async def live_room_websocket(
    websocket: WebSocket,
    session_id: str,
    student_id: str = Query(...),
    token: str = Query(None),
):
    from app.core.websocket_manager import manager as ws_manager
    from app.core.database import get_db
    from jose import JWTError, jwt
    from app.core.config import settings

    if token:
        try:
            payload = jwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"])
            if not payload.get("student_id"):
                await websocket.close(code=4001, reason="Invalid token")
                return
        except JWTError:
            await websocket.close(code=4001, reason="Invalid token")
            return

    db_session = await get_db().pair_sessions.find_one({"session_id": session_id}, {"_id": 0})
    if not db_session:
        await websocket.close(code=4004, reason="Session not found")
        return

    status = db_session.get("status")
    scheduled_at = db_session.get("scheduled_at")

    if status == SessionStatus.COMPLETED.value:
        await websocket.close(code=4005, reason="Session already completed")
        return

    if status == SessionStatus.SCHEDULED.value and scheduled_at and scheduled_at > datetime.utcnow():
        remaining = int((scheduled_at - datetime.utcnow()).total_seconds())
        await websocket.close(code=4006, reason=f"Session not ready yet. Starts in {remaining}s")
        return

    await activate_session_if_scheduled(session_id)

    role = await live_room_service.resolve_role(session_id, student_id)
    if not role:
        await websocket.close(code=4003, reason="Not a participant of this session")
        return

    room = await live_room_service.get_room(session_id)
    if not room:
        await live_room_service.create_room(session_id)

    await live_room_service.join_room(session_id, student_id)
    await ws_manager.connect(websocket, room_id=f"live_{session_id}", student_id=student_id, role=role)

    db = get_db()
    room_id = f"live_{session_id}"

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "chat")

            if msg_type == "chat":
                payload = {
                    "type": "chat",
                    "from": student_id,
                    "role": role,
                    "message": data.get("message", ""),
                    "timestamp": datetime.utcnow().isoformat(),
                }
                await db.pair_sessions.update_one(
                    {"session_id": session_id},
                    {"$push": {"chat_log": payload}},
                )
                await ws_manager.broadcast(room_id, payload)

            elif msg_type == "sandbox_update":
                code = data.get("code", "")
                language = data.get("language", "python")
                await live_room_service.update_shared_code(session_id, code, language)
                payload = {
                    "type": "sandbox_update",
                    "from": student_id,
                    "role": role,
                    "code": code,
                    "language": language,
                    "cursor_position": data.get("cursor_position"),
                    "timestamp": datetime.utcnow().isoformat(),
                }
                await ws_manager.broadcast(room_id, payload, exclude=websocket)

            elif msg_type == "voice_signal":
                target_student = data.get("target_student_id")
                payload = {
                    "type": "voice_signal",
                    "from": student_id,
                    "signal_type": data.get("signal_type"),
                    "signal_data": data.get("signal_data"),
                    "timestamp": datetime.utcnow().isoformat(),
                }
                if target_student:
                    await ws_manager.send_to_student(room_id, target_student, payload)
                else:
                    await ws_manager.broadcast(room_id, payload, exclude=websocket)

            elif msg_type == "screen_share":
                signal_type = data.get("signal_type")
                target_student = data.get("target_student_id")

                if signal_type == "started":
                    await live_room_service.set_screen_share(session_id, student_id, True)
                    await ws_manager.broadcast(
                        room_id,
                        {
                            "type": "screen_share",
                            "from": student_id,
                            "signal_type": "started",
                            "role": role,
                            "timestamp": datetime.utcnow().isoformat(),
                        },
                    )
                elif signal_type == "stopped":
                    await live_room_service.set_screen_share(session_id, student_id, False)
                    await ws_manager.broadcast(
                        room_id,
                        {
                            "type": "screen_share",
                            "from": student_id,
                            "signal_type": "stopped",
                            "role": role,
                            "timestamp": datetime.utcnow().isoformat(),
                        },
                    )
                elif signal_type in ("offer", "answer", "ice_candidate"):
                    payload = {
                        "type": "screen_share",
                        "from": student_id,
                        "signal_type": signal_type,
                        "signal_data": data.get("signal_data"),
                        "timestamp": datetime.utcnow().isoformat(),
                    }
                    if target_student:
                        await ws_manager.send_to_student(room_id, target_student, payload)
                    else:
                        await ws_manager.broadcast(room_id, payload, exclude=websocket)

            elif msg_type == "typing":
                await ws_manager.broadcast(
                    room_id,
                    {
                        "type": "typing",
                        "from": student_id,
                        "role": role,
                        "is_typing": data.get("is_typing", False),
                    },
                    exclude=websocket,
                )

            elif msg_type == "whiteboard":
                action_type = data.get("action_type", "draw")
                action_data = data.get("data", {})
                await live_room_service.add_whiteboard_action(session_id, action_type, action_data)
                await ws_manager.broadcast(
                    room_id,
                    {
                        "type": "whiteboard",
                        "from": student_id,
                        "action_type": action_type,
                        "data": action_data,
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                    exclude=websocket,
                )

            elif msg_type == "whiteboard_clear":
                await live_room_service.clear_whiteboard(session_id)
                await ws_manager.broadcast(
                    room_id,
                    {
                        "type": "whiteboard_clear",
                        "from": student_id,
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                )

            elif msg_type == "question_update":
                await ws_manager.broadcast(
                    room_id,
                    {
                        "type": "question_update",
                        "from": student_id,
                        "question_id": data.get("question_id"),
                        "status": data.get("status"),
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                )

            elif msg_type == "session_action":
                await ws_manager.broadcast(
                    room_id,
                    {
                        "type": "session_action",
                        "from": student_id,
                        "action": data.get("action"),
                        "payload": data.get("payload"),
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                )

            elif msg_type == "presence":
                await ws_manager.broadcast(
                    room_id,
                    {
                        "type": "presence",
                        "from": student_id,
                        "status": data.get("status", "online"),
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                )

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        await live_room_service.leave_room(session_id, student_id)
        ws_manager.disconnect(websocket)
        await ws_manager.broadcast(
            room_id,
            {
                "type": "user_left",
                "student_id": student_id,
                "role": role,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
    except Exception as e:
        logger.error(f"Live room WS error: session={session_id} student={student_id} error={e}")
        await live_room_service.leave_room(session_id, student_id)
        ws_manager.disconnect(websocket)
