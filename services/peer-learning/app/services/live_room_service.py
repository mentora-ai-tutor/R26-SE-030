from datetime import datetime
from typing import Dict, Any, Optional, List
from loguru import logger
from app.core.database import get_db
from app.models.models import RoomParticipant, WhiteboardAction


class LiveRoomService:
    """
    Manages live room state for paired session collaboration.
    Rooms are created from active pair sessions and enable real-time
    collaborative features: shared code editor, whiteboard, presence, etc.
    """

    def __init__(self):
        self.rooms: Dict[str, Dict[str, Any]] = {}

    async def create_room(self, session_id: str) -> Optional[Dict[str, Any]]:
        db = get_db()
        session = await db.pair_sessions.find_one(
            {"session_id": session_id}, {"_id": 0}
        )
        if not session:
            logger.warning(f"Cannot create live room: session {session_id} not found")
            return None

        status = session.get("status")
        if status not in ("active", "scheduled"):
            logger.warning(f"Cannot create live room: session {session_id} status is {status}")
            return None

        from app.services.session_service import activate_session_if_scheduled
        if status == "scheduled":
            await activate_session_if_scheduled(session_id)
            session = await db.pair_sessions.find_one(
                {"session_id": session_id}, {"_id": 0}
            )
            if not session or session.get("status") != "active":
                logger.warning(f"Cannot create live room: session {session_id} not yet active")
                return None

        room_id = f"live_{session_id}"

        if room_id in self.rooms:
            return self.rooms[room_id]

        teacher = await db.students.find_one(
            {"student_id": session["teacher_id"]}, {"_id": 0}
        )
        learner = await db.students.find_one(
            {"student_id": session["learner_id"]}, {"_id": 0}
        )

        participants = [
            RoomParticipant(
                student_id=session["teacher_id"],
                role="teacher",
                is_online=False,
            ),
            RoomParticipant(
                student_id=session["learner_id"],
                role="learner",
                is_online=False,
            ),
        ]

        self.rooms[room_id] = {
            "room_id": room_id,
            "session_id": session_id,
            "participants": [p.model_dump() for p in participants],
            "shared_code": session.get("sandbox_code", ""),
            "shared_language": "python",
            "whiteboard_actions": [],
            "status": "active",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "topic_id": session["topic_id"],
            "topic_name": session["topic_name"],
            "pairing_type": session.get("pairing_type", "ONE_WAY"),
            "teacher_name": teacher.get("name", "Teacher") if teacher else "Teacher",
            "learner_name": learner.get("name", "Learner") if learner else "Learner",
        }

        logger.info(f"Live room {room_id} created for session {session_id}")
        return self.rooms[room_id]

    async def get_room(self, session_id: str) -> Optional[Dict[str, Any]]:
        room_id = f"live_{session_id}"
        room = self.rooms.get(room_id)
        if room:
            return room

        db = get_db()
        session = await db.pair_sessions.find_one(
            {"session_id": session_id}, {"_id": 0}
        )
        if not session:
            return None

        return await self.create_room(session_id)

    async def join_room(self, session_id: str, student_id: str) -> Optional[Dict[str, Any]]:
        room = await self.get_room(session_id)
        if not room:
            return None

        room_id = f"live_{session_id}"
        for p in room["participants"]:
            if p["student_id"] == student_id:
                p["is_online"] = True
                p["joined_at"] = datetime.utcnow()
                break
        else:
            role = await self.resolve_role(session_id, student_id)
            if not role:
                return None
            room["participants"].append(
                RoomParticipant(
                    student_id=student_id,
                    role=role,
                    is_online=True,
                ).model_dump()
            )

        room["updated_at"] = datetime.utcnow()
        self.rooms[room_id] = room
        participant_role = next((p["role"] for p in room["participants"] if p["student_id"] == student_id), "member")
        logger.info(f"Student {student_id} joined live room {room_id} as {participant_role}")
        return room

    async def leave_room(self, session_id: str, student_id: str) -> bool:
        room_id = f"live_{session_id}"
        room = self.rooms.get(room_id)
        if not room:
            return False

        for p in room["participants"]:
            if p["student_id"] == student_id:
                p["is_online"] = False
                break

        room["updated_at"] = datetime.utcnow()
        logger.info(f"Student {student_id} left live room {room_id}")

        online_count = sum(1 for p in room["participants"] if p["is_online"])
        if online_count == 0:
            logger.info(f"Live room {room_id} has no participants, keeping for rejoin")
        return True

    async def close_room(self, session_id: str) -> bool:
        room_id = f"live_{session_id}"
        if room_id not in self.rooms:
            return False

        self.rooms[room_id]["status"] = "closed"
        self.rooms[room_id]["updated_at"] = datetime.utcnow()
        logger.info(f"Live room {room_id} closed")
        return True

    async def update_shared_code(
        self, session_id: str, code: str, language: str = "python"
    ) -> bool:
        room_id = f"live_{session_id}"
        room = self.rooms.get(room_id)
        if not room:
            return False

        room["shared_code"] = code
        room["shared_language"] = language
        room["updated_at"] = datetime.utcnow()

        db = get_db()
        await db.pair_sessions.update_one(
            {"session_id": session_id},
            {"$set": {"sandbox_code": code, "updated_at": datetime.utcnow()}},
        )
        return True

    async def add_whiteboard_action(
        self, session_id: str, action_type: str, data: Dict[str, Any]
    ) -> bool:
        room_id = f"live_{session_id}"
        room = self.rooms.get(room_id)
        if not room:
            return False

        action = WhiteboardAction(action_type=action_type, data=data).model_dump()
        room["whiteboard_actions"].append(action)
        room["updated_at"] = datetime.utcnow()
        return True

    async def clear_whiteboard(self, session_id: str) -> bool:
        room_id = f"live_{session_id}"
        room = self.rooms.get(room_id)
        if not room:
            return False

        room["whiteboard_actions"] = []
        room["updated_at"] = datetime.utcnow()
        return True

    async def set_screen_share(
        self, session_id: str, student_id: str, is_sharing: bool
    ) -> bool:
        room_id = f"live_{session_id}"
        room = self.rooms.get(room_id)
        if not room:
            return False

        room["screen_share"] = {
            "sharer_id": student_id if is_sharing else None,
            "is_sharing": is_sharing,
        }
        room["updated_at"] = datetime.utcnow()
        return True

    def get_screen_share_state(self, session_id: str) -> Dict[str, Any]:
        room_id = f"live_{session_id}"
        room = self.rooms.get(room_id)
        if not room or "screen_share" not in room:
            return {"is_sharing": False, "sharer_id": None}
        return room["screen_share"]

    def get_room_members(self, session_id: str) -> List[Dict[str, Any]]:
        room_id = f"live_{session_id}"
        room = self.rooms.get(room_id)
        if not room:
            return []
        return room.get("participants", [])

    async def resolve_role(self, session_id: str, student_id: str) -> Optional[str]:
        db = get_db()
        session = await db.pair_sessions.find_one({"session_id": session_id}, {"_id": 0})
        if not session:
            return None
        if session.get("teacher_id") == student_id:
            return "teacher"
        if session.get("learner_id") == student_id:
            return "learner"
        return None


live_room_service = LiveRoomService()
