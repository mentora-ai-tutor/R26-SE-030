from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from jose import JWTError, jwt
from loguru import logger
from app.core.websocket_manager import manager
from app.core.database import get_db
from app.core.config import settings

router = APIRouter(tags=["WebSocket"])


def decode_ws_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.jwt_secret_key, algorithms=["HS256"])
    except JWTError:
        return None


@router.websocket("/ws/session/{session_id}")
async def session_websocket(
    websocket: WebSocket,
    session_id: str,
    student_id: str = Query(...),
    role: str = Query("learner"),
    token: str = Query(None),
):
    if token:
        payload = decode_ws_token(token)
        if not payload:
            await websocket.close(code=4001, reason="Invalid token")
            return
    await manager.connect(websocket, room_id=session_id, student_id=student_id, role=role)
    db = get_db()

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "chat")

            if msg_type == "chat":
                # Broadcast chat to all in session room
                payload = {
                    "type": "chat",
                    "from": student_id,
                    "role": role,
                    "message": data.get("message", ""),
                    "timestamp": datetime.utcnow().isoformat(),
                }
                # Save to DB
                await db.pair_sessions.update_one(
                    {"session_id": session_id},
                    {"$push": {"chat_log": payload}},
                )
                await manager.broadcast(session_id, payload)

            elif msg_type == "sandbox_update":
                # Sync code editor state
                payload = {
                    "type": "sandbox_update",
                    "from": student_id,
                    "code": data.get("code", ""),
                    "language": data.get("language", "python"),
                    "cursor_position": data.get("cursor_position"),
                    "timestamp": datetime.utcnow().isoformat(),
                }
                await db.pair_sessions.update_one(
                    {"session_id": session_id},
                    {"$set": {"sandbox_code": data.get("code", "")}},
                )
                await manager.broadcast(session_id, payload, exclude=websocket)

            elif msg_type == "voice_signal":
                # WebRTC signaling: forward offer/answer/ICE to specific peer
                target_student = data.get("target_student_id")
                payload = {
                    "type": "voice_signal",
                    "from": student_id,
                    "signal_type": data.get("signal_type"),  # offer/answer/ice_candidate
                    "signal_data": data.get("signal_data"),
                    "timestamp": datetime.utcnow().isoformat(),
                }
                if target_student:
                    await manager.send_to_student(session_id, target_student, payload)
                else:
                    await manager.broadcast(session_id, payload, exclude=websocket)

            elif msg_type == "typing":
                await manager.broadcast(
                    session_id,
                    {"type": "typing", "from": student_id, "is_typing": data.get("is_typing", False)},
                    exclude=websocket,
                )

            elif msg_type == "hint_request":
                await manager.broadcast(
                    session_id,
                    {
                        "type": "hint_request",
                        "from": student_id,
                        "question_id": data.get("question_id"),
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                )

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        await manager.broadcast(
            session_id,
            {
                "type": "user_left",
                "student_id": student_id,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
    except Exception as e:
        logger.error(f"WebSocket error in session {session_id}: {e}")
        manager.disconnect(websocket)


@router.websocket("/ws/group/{session_id}")
async def group_session_websocket(
    websocket: WebSocket,
    session_id: str,
    student_id: str = Query(...),
    role: str = Query("member"),
    token: str = Query(None),
):
    if token:
        payload = decode_ws_token(token)
        if not payload:
            await websocket.close(code=4001, reason="Invalid token")
            return
    await manager.connect(websocket, room_id=f"group_{session_id}", student_id=student_id, role=role)
    db = get_db()
    room_id = f"group_{session_id}"

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
                await db.group_sessions.update_one(
                    {"session_id": session_id},
                    {"$push": {"chat_log": payload}},
                )
                await manager.broadcast(room_id, payload)

            elif msg_type == "sandbox_update":
                payload = {
                    "type": "sandbox_update",
                    "from": student_id,
                    "role": role,
                    "code": data.get("code", ""),
                    "language": data.get("language", "python"),
                    "timestamp": datetime.utcnow().isoformat(),
                }
                await db.group_sessions.update_one(
                    {"session_id": session_id},
                    {"$set": {"sandbox_code": data.get("code", "")}},
                )
                await manager.broadcast(room_id, payload, exclude=websocket)

            elif msg_type == "voice_signal":
                target_student = data.get("target_student_id")
                payload = {
                    "type": "voice_signal",
                    "from": student_id,
                    "signal_type": data.get("signal_type"),
                    "signal_data": data.get("signal_data"),
                }
                if target_student:
                    await manager.send_to_student(room_id, target_student, payload)
                else:
                    await manager.broadcast(room_id, payload, exclude=websocket)

            elif msg_type == "role_action":
                # Role-specific actions: explainer explaining, solver submitting code, reviewer checklist
                await manager.broadcast(
                    room_id,
                    {
                        "type": "role_action",
                        "from": student_id,
                        "role": role,
                        "action": data.get("action"),
                        "content": data.get("content"),
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                )

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        manager.disconnect(websocket)
        await manager.broadcast(
            room_id,
            {
                "type": "user_left",
                "student_id": student_id,
                "role": role,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
    except Exception as e:
        logger.error(f"WebSocket error in group {session_id}: {e}")
        manager.disconnect(websocket)


@router.websocket("/ws/notifications/{student_id}")
async def notification_websocket(
    websocket: WebSocket,
    student_id: str,
    token: str = Query(None),
):
    if token:
        payload = decode_ws_token(token)
        if not payload:
            await websocket.close(code=4001, reason="Invalid token")
            return
    await manager.connect(
        websocket,
        room_id=f"notif_{student_id}",
        student_id=student_id,
        role="self",
    )
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"Notification WS error for {student_id}: {e}")
        manager.disconnect(websocket)
