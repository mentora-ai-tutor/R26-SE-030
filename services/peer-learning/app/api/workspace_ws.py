import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.student_routes import decode_student_token
from app.api.workspace_routes import persist_chat_message
from app.services.mongodb import get_collection

logger = logging.getLogger("workspace_ws")

router = APIRouter(prefix="/api/workspaces", tags=["Project Workspace"])

COLOR_PALETTE = [
    "#2563eb", "#dc2626", "#059669", "#d97706",
    "#7c3aed", "#db2777", "#0891b2", "#65a30d",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _color_for(student_id: str) -> str:
    return COLOR_PALETTE[sum(ord(c) for c in student_id) % len(COLOR_PALETTE)]


def _student_name(student_id: str) -> str:
    for collection_name in ("students", "student_analyses"):
        try:
            doc = get_collection(collection_name).find_one({"student_id": student_id})
        except Exception:
            doc = None
        if doc and doc.get("name"):
            return str(doc["name"])
    return str(student_id)


class WorkspaceManager:
    """Relays Yjs CRDT updates and presence for project workspace rooms.

    The server is a stateless fan-out relay: Yjs documents live in the browser.
    The latest update per file is cached in memory so late joiners can sync.
    """

    def __init__(self):
        self.active_rooms: Dict[str, List[WebSocket]] = {}
        self.socket_members: Dict[WebSocket, dict] = {}
        self.doc_state: Dict[str, Dict[str, str]] = {}
        self.cursors: Dict[str, Dict[str, dict]] = {}

    def presence(self, workspace_id: str) -> List[dict]:
        return [
            self.socket_members[socket]
            for socket in self.active_rooms.get(workspace_id, [])
            if socket in self.socket_members
        ]

    async def connect(self, websocket: WebSocket, workspace_id: str, member: dict):
        await websocket.accept()
        self.active_rooms.setdefault(workspace_id, []).append(websocket)
        self.socket_members[websocket] = member
        logger.info(
            "Client %s connected to workspace %s (%d online)",
            member.get("student_id"), workspace_id, len(self.active_rooms[workspace_id]),
        )

        await websocket.send_text(json.dumps({
            "type": "INIT_STATE",
            "workspace_id": workspace_id,
            "self": member,
            "presence": self.presence(workspace_id),
            "document_files": list(self.doc_state.get(workspace_id, {}).keys()),
            "cursors": list(self.cursors.get(workspace_id, {}).values()),
            "timestamp": _now_iso(),
        }))

        await self.broadcast(workspace_id, {
            "type": "PRESENCE_JOINED",
            "participant": member,
            "presence": self.presence(workspace_id),
        }, sender=websocket)

    def disconnect(self, websocket: WebSocket, workspace_id: str) -> Optional[dict]:
        member = self.socket_members.pop(websocket, None)
        room = self.active_rooms.get(workspace_id)
        if room and websocket in room:
            room.remove(websocket)
        if member:
            self.cursors.get(workspace_id, {}).pop(str(member.get("student_id")), None)
        if room is not None and not room:
            self.active_rooms.pop(workspace_id, None)
        return member

    async def broadcast(self, workspace_id: str, payload: Any, sender: Optional[WebSocket] = None):
        text = payload if isinstance(payload, str) else json.dumps(payload)
        dead = []
        for connection in list(self.active_rooms.get(workspace_id, [])):
            if connection is sender:
                continue
            try:
                await connection.send_text(text)
            except Exception as e:
                logger.warning("Workspace send failed: %s", e)
                dead.append(connection)
        for socket in dead:
            self.disconnect(socket, workspace_id)

    async def broadcast_bytes(self, workspace_id: str, data: bytes, sender: Optional[WebSocket] = None):
        dead = []
        for connection in list(self.active_rooms.get(workspace_id, [])):
            if connection is sender:
                continue
            try:
                await connection.send_bytes(data)
            except Exception as e:
                logger.warning("Workspace binary send failed: %s", e)
                dead.append(connection)
        for socket in dead:
            self.disconnect(socket, workspace_id)


workspace_manager = WorkspaceManager()


@router.websocket("/ws/{workspace_id}")
async def workspace_socket_endpoint(websocket: WebSocket, workspace_id: str):
    """Real-time Yjs relay, presence, awareness, and binary frame fan-out."""
    token = websocket.query_params.get("token")
    try:
        student_id = str(decode_student_token(token or ""))
    except Exception:
        await websocket.close(code=1008)
        return

    workspace = get_collection("workspaces").find_one({"workspace_id": workspace_id})
    if not workspace:
        await websocket.close(code=1008)
        return

    member_doc = get_collection("workspace_members").find_one({
        "workspace_id": workspace_id,
        "student_id": student_id,
        "status": "active",
    })
    if not member_doc:
        await websocket.close(code=1008)
        return

    member = {
        "student_id": student_id,
        "name": _student_name(student_id),
        "role": member_doc.get("role", "viewer"),
        "color": _color_for(student_id),
    }

    try:
        get_collection("workspace_members").update_one(
            {"workspace_id": workspace_id, "student_id": student_id},
            {"$set": {"last_seen_at": _now_iso()}},
        )
    except Exception:
        pass

    await workspace_manager.connect(websocket, workspace_id, member)

    try:
        while True:
            message = await websocket.receive()

            if message.get("type") == "websocket.disconnect":
                break

            if message.get("bytes") is not None:
                await workspace_manager.broadcast_bytes(workspace_id, message["bytes"], sender=websocket)
                continue

            text = message.get("text")
            if text is None:
                continue

            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                await workspace_manager.broadcast(workspace_id, text, sender=websocket)
                continue

            msg_type = payload.get("type")

            if msg_type == "YJS_UPDATE":
                file_id = payload.get("file_id")
                update = payload.get("update")
                if not file_id or update is None:
                    await websocket.send_text(json.dumps({
                        "type": "ERROR",
                        "message": "YJS_UPDATE requires 'file_id' and 'update'.",
                    }))
                    continue
                workspace_manager.doc_state.setdefault(workspace_id, {})[file_id] = update
                await workspace_manager.broadcast(workspace_id, {
                    "type": "YJS_UPDATE",
                    "file_id": file_id,
                    "update": update,
                    "sender_student_id": student_id,
                    "timestamp": _now_iso(),
                }, sender=websocket)

            elif msg_type == "SYNC_REQUEST":
                file_id = payload.get("file_id")
                state = workspace_manager.doc_state.get(workspace_id, {}).get(file_id)
                await websocket.send_text(json.dumps({
                    "type": "YJS_UPDATE" if state is not None else "SYNC_STATE",
                    "file_id": file_id,
                    "update": state,
                    "sender_student_id": "server",
                    "timestamp": _now_iso(),
                }))

            elif msg_type == "AWARENESS":
                cursor = {
                    "student_id": student_id,
                    "name": member["name"],
                    "role": member["role"],
                    "color": member["color"],
                    "file_id": payload.get("file_id"),
                    "selection": payload.get("selection"),
                    "cursor": payload.get("cursor"),
                    "timestamp": _now_iso(),
                }
                workspace_manager.cursors.setdefault(workspace_id, {})[student_id] = cursor
                await workspace_manager.broadcast(workspace_id, {
                    "type": "AWARENESS",
                    "awareness": cursor,
                }, sender=websocket)

            elif msg_type == "CHAT_MESSAGE":
                text = (payload.get("message") or "").strip()
                if not text:
                    await websocket.send_text(json.dumps({
                        "type": "ERROR",
                        "message": "CHAT_MESSAGE requires a non-empty 'message'.",
                    }))
                    continue
                doc = persist_chat_message(
                    workspace_id,
                    student_id,
                    member["name"],
                    member["role"],
                    text,
                    payload.get("message_type", "text"),
                    payload.get("reply_to"),
                )
                await workspace_manager.broadcast(workspace_id, {
                    "type": "CHAT_MESSAGE",
                    "message": doc,
                    "timestamp": _now_iso(),
                })

            elif msg_type == "PING":
                await websocket.send_text(json.dumps({"type": "PONG", "timestamp": _now_iso()}))

            else:
                await workspace_manager.broadcast(workspace_id, payload, sender=websocket)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("Workspace socket error in %s: %s", workspace_id, e)
    finally:
        left = workspace_manager.disconnect(websocket, workspace_id)
        if left:
            await workspace_manager.broadcast(workspace_id, {
                "type": "PRESENCE_LEFT",
                "participant": left,
                "presence": workspace_manager.presence(workspace_id),
            })
