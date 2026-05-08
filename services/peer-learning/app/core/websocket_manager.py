import json
from datetime import datetime
from typing import Dict, Set, Any
from fastapi import WebSocket
from loguru import logger


class ConnectionManager:
    """
    Manages WebSocket connections for:
    - Pair session chat (session_id room)
    - Group session chat (group_id room)
    - Sandbox code sync (session_id room)
    - Voice signaling (WebRTC offer/answer/ICE)
    """

    def __init__(self):
        # room_id -> set of WebSocket connections
        self.rooms: Dict[str, Set[WebSocket]] = {}
        # websocket -> metadata (student_id, room_id, role)
        self.meta: Dict[WebSocket, Dict[str, Any]] = {}

    async def connect(self, websocket: WebSocket, room_id: str, student_id: str, role: str = "member"):
        await websocket.accept()
        if room_id not in self.rooms:
            self.rooms[room_id] = set()
        self.rooms[room_id].add(websocket)
        self.meta[websocket] = {"student_id": student_id, "room_id": room_id, "role": role}
        logger.info(f"WS connected: student={student_id} room={room_id}")

        # Notify others in the room
        await self.broadcast(
            room_id=room_id,
            message={
                "type": "user_joined",
                "student_id": student_id,
                "role": role,
                "timestamp": datetime.utcnow().isoformat(),
            },
            exclude=websocket,
        )

    def disconnect(self, websocket: WebSocket):
        meta = self.meta.get(websocket, {})
        room_id = meta.get("room_id")
        student_id = meta.get("student_id")

        if room_id and room_id in self.rooms:
            self.rooms[room_id].discard(websocket)
            if not self.rooms[room_id]:
                del self.rooms[room_id]

        if websocket in self.meta:
            del self.meta[websocket]

        logger.info(f"WS disconnected: student={student_id} room={room_id}")

    async def broadcast(self, room_id: str, message: Dict[str, Any], exclude: WebSocket = None):
        """Send message to all connections in a room."""
        if room_id not in self.rooms:
            return
        dead = set()
        for ws in self.rooms[room_id]:
            if ws is exclude:
                continue
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.disconnect(ws)

    async def send_personal(self, websocket: WebSocket, message: Dict[str, Any]):
        """Send message to a specific WebSocket."""
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.warning(f"Failed to send personal message: {e}")

    async def send_to_student(self, room_id: str, student_id: str, message: Dict[str, Any]):
        """Send message to a specific student in a room."""
        if room_id not in self.rooms:
            return
        for ws, meta in self.meta.items():
            if meta.get("room_id") == room_id and meta.get("student_id") == student_id:
                await self.send_personal(ws, message)
                return

    def get_room_members(self, room_id: str) -> list:
        if room_id not in self.rooms:
            return []
        return [self.meta[ws] for ws in self.rooms[room_id] if ws in self.meta]


manager = ConnectionManager()
