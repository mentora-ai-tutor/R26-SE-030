import json
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect, HTTPException, status

from app.api.student_routes import decode_student_token, verify_jwt_student
from app.services.mongodb import get_collection, upsert_collab_room
from app.agents.student_agent import generate_peer_coding_tasks
from app.agents.support_agent import support_agent

logger = logging.getLogger("collab_logger")

router = APIRouter(prefix="/api/collab", tags=["Real-Time Collaboration Engine"])


# ==========================================
# 1. Connection Manager for WebSockets
# ==========================================

class CollaborationManager:
    """Real-time collaborative room connection manager."""

    def __init__(self):
        self.active_rooms: Dict[str, List[WebSocket]] = {}
        self.room_code_state: Dict[str, str] = {}
        self.room_task_index: Dict[str, int] = {}
        self.room_cursors: Dict[str, Dict[str, dict]] = {}
        self.socket_students: Dict[WebSocket, str] = {}

    async def connect(self, websocket: WebSocket, room_id: str, student_id: str):
        await websocket.accept()
        if room_id not in self.active_rooms:
            self.active_rooms[room_id] = []
            self.room_cursors[room_id] = {}
            self.room_code_state[room_id] = "// Start coding Java here...\npublic class Main {\n    public static void main(String[] args) {\n        \n    }\n}"

        self.active_rooms[room_id].append(websocket)
        self.socket_students[websocket] = str(student_id)
        logger.info(f"New client connected to room: {room_id}. Total clients: {len(self.active_rooms[room_id])}")

        coding_tasks = None
        current_task_index = 0
        room_doc = get_collection("collab_rooms").find_one({"room_id": room_id})
        if room_doc:
            if room_doc.get("code") is not None:
                self.room_code_state[room_id] = room_doc["code"]
            if "coding_tasks" in room_doc:
                coding_tasks = room_doc["coding_tasks"]
            current_task_index = room_doc.get("current_task_index", 0)

        if room_id not in self.room_task_index:
            self.room_task_index[room_id] = current_task_index

        task_progress = room_doc.get("task_progress", []) if room_doc else []
        current_task = room_doc.get("current_task", current_task_index + 1) if room_doc else current_task_index + 1
        sequence_status = room_doc.get("status", "in_progress") if room_doc else "in_progress"
        participant = self.participant_for_room(room_doc or {}, student_id)
        whiteboard = room_doc.get("whiteboard", []) if room_doc else []

        # Load chat history from MongoDB
        chat_messages = []
        try:
            chat_cursor = get_collection("collab_chat_messages").find(
                {"room_id": room_id}
            ).sort("timestamp", 1)
            chat_messages = list(chat_cursor)
            for msg in chat_messages:
                if "_id" in msg:
                    msg["_id"] = str(msg["_id"])
                if "role" not in msg:
                    msg["role"] = "Participant"
        except Exception:
            pass

        current_progress = next(
            (item for item in task_progress if item.get("task_number") == current_task),
            {"attempts": 0, "passed": False},
        )
        initial_payload = {
            "type": "INIT_STATE",
            "code": self.room_code_state[room_id],
            "mode": (room_doc or {}).get("mode", "peer"),
            "active_users_count": len(self.active_rooms[room_id]),
            "timestamp": datetime.utcnow().isoformat(),
            "current_task_index": self.room_task_index.get(room_id, 0),
            "current_task": current_task,
            "status": sequence_status,
            "attempts": current_progress.get("attempts", 0),
            "passed": current_progress.get("passed", False),
            "task_progress": task_progress,
            "total_tasks": len(coding_tasks or []),
            "sequence_complete": sequence_status == "completed",
            "participant": participant,
            "cursors": list(self.room_cursors.get(room_id, {}).values()),
            "whiteboard": whiteboard,
            "chat_messages": chat_messages,
        }
        if coding_tasks:
            # Do not expose locked task content before it is unlocked.
            initial_payload["coding_tasks"] = coding_tasks[:current_task]
            initial_payload["task"] = coding_tasks[current_task - 1]

        await websocket.send_text(json.dumps(initial_payload))

        upsert_collab_room(
            room_id=room_id,
            code=self.room_code_state[room_id],
            active_users=len(self.active_rooms[room_id]),
        )

        await self.broadcast_to_room(json.dumps({
            "type": "PRESENCE_JOINED",
            "participant": participant,
        }), room_id, sender=websocket)

    @staticmethod
    def participant_for_room(room_doc: dict, student_id: str) -> dict:
        learner_id = str(room_doc.get("learner_student_id", ""))
        is_learner = str(student_id) == learner_id
        return {
            "student_id": str(student_id),
            "name": str(room_doc.get("learner_name" if is_learner else "peer_name", "Participant")),
            "role": "Learner" if is_learner else "Peer Teacher",
            "color": "#2563eb" if is_learner else "#dc2626",
        }

    def disconnect(self, websocket: WebSocket, room_id: str):
        """ශිෂ්‍යයෙකු room එකෙන් ඉවත් වූ විට Connection එක ඉවත් කිරීම."""
        student_id = self.socket_students.pop(websocket, None)
        if room_id in self.active_rooms:
            if websocket in self.active_rooms[room_id]:
                self.active_rooms[room_id].remove(websocket)
                logger.info(f"Client removed from room: {room_id}. Remaining: {len(self.active_rooms[room_id])}")

            # Room එකේ කිසිවෙක් නැත්නම් Memory වලින් ඉවත් කිරීම
            if len(self.active_rooms[room_id]) == 0:
                del self.active_rooms[room_id]
                del self.room_code_state[room_id]
                self.room_cursors.pop(room_id, None)
            elif student_id:
                self.room_cursors.get(room_id, {}).pop(student_id, None)
        return student_id

    async def broadcast_to_room(self, message: str, room_id: str, sender: WebSocket):
        """සන්දේශයක් යැවූ ශිෂ්‍යයා හැර room එකේ සිටින අනිත් සෑම ශිෂ්‍යයෙකුටම Data Broadcast කිරීම."""
        if room_id in self.active_rooms:
            disconnected_sockets = []
            for connection in self.active_rooms[room_id]:
                if connection != sender:
                    try:
                        await connection.send_text(message)
                    except Exception as e:
                        logger.error(f"Failed to send message: {str(e)}")
                        disconnected_sockets.append(connection)

            # Clean up broken sockets
            for dead_socket in disconnected_sockets:
                self.disconnect(dead_socket, room_id)

    async def broadcast_all(self, message: str, room_id: str):
        """Send a state update to every learner and Peer Teacher connection."""
        if room_id not in self.active_rooms:
            return

        disconnected_sockets = []
        for connection in self.active_rooms[room_id]:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.error(f"Failed to send state update: {str(e)}")
                disconnected_sockets.append(connection)

        for dead_socket in disconnected_sockets:
            self.disconnect(dead_socket, room_id)

    def update_code_state(self, room_id: str, new_code: str):
        """Room එකේ අලුත්ම Code එක Memory එකේ Save කරගැනීම."""
        self.room_code_state[room_id] = new_code


# Connection Manager Instance එක
collab_manager = CollaborationManager()


# ==========================================
# 2. REST Endpoints for Collaboration Rooms
# ==========================================

@router.get("/rooms")
def list_active_rooms(token_student_id: str = Depends(verify_jwt_student)):
    """දැනට සක්‍රීයව පවතින Collaborative Rooms සහ ඒවායේ සිසුන් ගණන ලබාදෙයි."""
    active_summary = {
        room_id: len(sockets) 
        for room_id, sockets in collab_manager.active_rooms.items()
    }
    return {
        "status": "success",
        "active_rooms_count": len(collab_manager.active_rooms),
        "rooms": active_summary
    }

@router.get("/rooms/{room_id}/state")
def get_room_code_state(
    room_id: str,
    token_student_id: str = Depends(verify_jwt_student),
):
    """Room එකක වත්මන් Java Code state එක ලබාගැනීම."""
    if room_id not in collab_manager.room_code_state:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Room not found or inactive."
        )
    return {
        "room_id": room_id,
        "code": collab_manager.room_code_state[room_id]
    }


@router.post("/initialize-session")
def initialize_session(
    room_id: str = Query(...),
    topic_id: str = Query(default="JAVA_GENERAL"),
    token_student_id: str = Depends(verify_jwt_student),
):
    """Create a collaboration room without requiring a JSON request body."""
    if room_id not in collab_manager.room_code_state:
        collab_manager.room_code_state[room_id] = (
            "// Start coding Java here...\n"
            "public class Main {\n"
            "    public static void main(String[] args) {\n"
            "    }\n"
            "}"
        )
        collab_manager.active_rooms.setdefault(room_id, [])
    upsert_collab_room(room_id, collab_manager.room_code_state[room_id], 0)
    return {
        "status": "active",
        "room_id": room_id,
        "student_id": token_student_id,
        "topic_id": topic_id,
    }


@router.post("/setup-ai-session")
def setup_ai_session(
    room_id: str = Query(...),
    topic: str = Query(default="Java Programming"),
    token_student_id: str = Depends(verify_jwt_student),
):
    """Create a collaboration room for an AI teacher session.

    Generates 7 coding tasks based on the student's knowledge gaps,
    exactly like a peer session. The AI teacher also chats to guide the student.
    """
    from app.api.student_routes import get_latest_student_analysis

    try:
        analysis = get_latest_student_analysis(token_student_id)
    except HTTPException:
        analysis = None

    knowledge_gaps = []
    gap_topic = topic
    gap_subskill = "General Java Concepts"
    gap_mastery = 0
    gap_misconception = None

    if analysis:
        knowledge_gaps = analysis.get("mastery_profile", {}).get("knowledge_gaps", [])
        if knowledge_gaps:
            first_gap = knowledge_gaps[0]
            gap_topic = first_gap.get("topic", topic)
            weak_subskills = first_gap.get("weak_subskills", [])
            if weak_subskills:
                gap_subskill = weak_subskills[0].get("subskill", gap_subskill)
            gap_mastery = first_gap.get("mastery_score", 0)
            misconceptions = first_gap.get("misconceptions", [])
            if misconceptions:
                gap_misconception = misconceptions[0]

    coding_tasks = generate_peer_coding_tasks(
        topic=gap_topic,
        subskill=gap_subskill,
        mastery_score=gap_mastery,
        misconception=gap_misconception,
    )

    first_starter_code = (
        coding_tasks[0].get("starter_code", "")
        if coding_tasks
        else "// Start coding Java here...\npublic class Main {\n    public static void main(String[] args) {\n    }\n}"
    )

    upsert_collab_room(
        room_id=room_id,
        code=first_starter_code,
        active_users=0,
    )

    get_collection("collab_rooms").update_one(
        {"room_id": room_id},
        {"$set": {
            "mode": "ai_teacher",
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
            "learner_student_id": token_student_id,
            "peer_student_id": "AI_TEACHER",
            "learner_name": token_student_id,
            "peer_name": "AI Assistant Teacher",
            "topic": gap_topic,
            "target_subskill": gap_subskill,
            "knowledge_gaps": knowledge_gaps,
            "mastery_score": gap_mastery,
        }},
    )

    return {
        "status": "success",
        "room_id": room_id,
        "student_id": token_student_id,
        "mode": "ai_teacher",
        "topic": gap_topic,
        "subskill": gap_subskill,
        "total_tasks": len(coding_tasks),
        "message": "AI teacher session started with tasks based on your knowledge gaps.",
    }


# ==========================================
# 3. Real-Time WebSocket Endpoint
# ==========================================

@router.websocket("/ws/collab/{room_id}")
async def collaborative_editor_endpoint(websocket: WebSocket, room_id: str):
    """
    Monaco Code Editor sync සහ real-time chat කළමනාකරණය කරන WebSocket Endpoint එක.
    `WebSocketDisconnect` නිවැරදිව Handle කර ඇත.
    """
    token = websocket.query_params.get("token")
    try:
        student_id = decode_student_token(token or "")
    except Exception:
        await websocket.close(code=1008)
        return

    room_doc = get_collection("collab_rooms").find_one({"room_id": room_id}) or {}
    room_members = {
        str(room_doc.get("learner_student_id", "")),
        str(room_doc.get("peer_student_id", "")),
    } - {""}
    if room_members and str(student_id) not in room_members:
        await websocket.close(code=1008)
        return

    await collab_manager.connect(websocket, room_id, student_id)

    try:
        while True:
            # Client වෙතින් පැමිණෙන Messages සවන්දීම (JSON string formatted)
            data_text = await websocket.receive_text()

            try:
                data = json.loads(data_text)
                msg_type = data.get("type")

                # A. Code Editing Sync Event
                if msg_type == "CODE_CHANGE":
                    new_code = data.get("code", "")
                    collab_manager.update_code_state(room_id, new_code)
                    upsert_collab_room(
                        room_id=room_id,
                        code=new_code,
                        active_users=len(
                            collab_manager.active_rooms.get(room_id, [])
                        ),
                    )
                    await collab_manager.broadcast_to_room(data_text, room_id, sender=websocket)

                # B. Cursor Position Sync Event
                elif msg_type == "CURSOR_MOVE":
                    room_doc = get_collection("collab_rooms").find_one({"room_id": room_id}) or {}
                    participant = collab_manager.participant_for_room(room_doc, student_id)
                    cursor = {
                        "type": "CURSOR_MOVE",
                        "student_id": student_id,
                        "name": participant["name"],
                        "role": participant["role"],
                        "color": participant["color"],
                        "position": data.get("position", {}),
                    }
                    collab_manager.room_cursors.setdefault(room_id, {})[student_id] = cursor
                    await collab_manager.broadcast_to_room(json.dumps(cursor), room_id, sender=websocket)

                # C. Real-time Chat Event
                elif msg_type == "CHAT_MESSAGE":
                    room_doc = get_collection("collab_rooms").find_one({"room_id": room_id}) or {}
                    participant = collab_manager.participant_for_room(room_doc, student_id)
                    message_text = data.get("message", "")
                    timestamp = datetime.utcnow().isoformat()

                    # Prevent duplicate messages (same room, student, message within 2 seconds)
                    two_sec_ago = datetime.utcnow().timestamp() - 2
                    existing = get_collection("collab_chat_messages").find_one({
                        "room_id": room_id,
                        "student_id": student_id,
                        "message": message_text,
                    }, sort=[("timestamp", -1)])
                    if existing:
                        try:
                            existing_ts = datetime.fromisoformat(existing["timestamp"].replace("Z", "+00:00")).timestamp()
                            if existing_ts > two_sec_ago:
                                continue
                        except Exception:
                            pass

                    chat_doc = {
                        "room_id": room_id,
                        "student_id": student_id,
                        "sender_name": participant["name"],
                        "role": participant["role"],
                        "message": message_text,
                        "timestamp": timestamp,
                    }
                    get_collection("collab_chat_messages").insert_one(chat_doc)

                    broadcast_payload = json.dumps({
                        "type": "CHAT_MESSAGE",
                        "room_id": room_id,
                        "student_id": student_id,
                        "sender_name": participant["name"],
                        "role": participant["role"],
                        "message": message_text,
                        "timestamp": timestamp,
                    })
                    await collab_manager.broadcast_to_room(broadcast_payload, room_id, sender=websocket)

                    # AI teacher auto-reply: route student message to support_agent
                    if room_doc.get("mode") == "ai_teacher":
                        # Build knowledge gap context for focused AI responses
                        kg_context = None
                        knowledge_gaps = room_doc.get("knowledge_gaps", [])
                        target_sub = room_doc.get("target_subskill", "")
                        if knowledge_gaps:
                            gap_lines = []
                            for g in knowledge_gaps[:3]:
                                topics = g.get("topic", "")
                                weak = [ws.get("subskill", "") for ws in g.get("weak_subskills", [])]
                                mis = g.get("misconceptions", [])
                                score = g.get("mastery_score", "?")
                                gap_lines.append(
                                    f"- Topic: {topics} | Mastery: {score}/100 | "
                                    f"Weak subskills: {', '.join(weak)} | "
                                    f"Misconceptions: {', '.join(mis) if mis else 'none observed'}"
                                )
                            kg_context = (
                                f"Target subskill for this session: {target_sub}\n"
                                f"Student knowledge gaps:\n" + "\n".join(gap_lines)
                            )

                        ai_reply = support_agent.get_response(message_text, student_id, knowledge_gap_context=kg_context)
                        reply_text = ai_reply.get("reply", "Sorry, I couldn't process that.")
                        reply_ts = datetime.utcnow().isoformat()

                        get_collection("collab_chat_messages").insert_one({
                            "room_id": room_id,
                            "student_id": "AI_TEACHER",
                            "sender_name": "AI Assistant Teacher",
                            "role": "ai",
                            "message": reply_text,
                            "timestamp": reply_ts,
                        })

                        ai_payload = json.dumps({
                            "type": "CHAT_MESSAGE",
                            "room_id": room_id,
                            "student_id": "AI_TEACHER",
                            "sender_name": "AI Assistant Teacher",
                            "role": "ai",
                            "message": reply_text,
                            "timestamp": reply_ts,
                        })
                        await collab_manager.broadcast_to_room(ai_payload, room_id)

                # Whiteboard operations use the same room and survive reconnects.
                elif msg_type == "WHITEBOARD_DRAW":
                    operation = data.get("operation")
                    if not isinstance(operation, dict):
                        await websocket.send_text(json.dumps({
                            "type": "WHITEBOARD_ERROR",
                            "message": "A drawing operation object is required.",
                        }))
                        continue
                    operation = dict(operation)
                    operation["student_id"] = student_id
                    operation["color"] = data.get("color", "#111827")
                    get_collection("collab_rooms").update_one(
                        {"room_id": room_id},
                        {"$push": {"whiteboard": operation}},
                    )
                    await collab_manager.broadcast_to_room(json.dumps({
                        "type": "WHITEBOARD_DRAW",
                        "operation": operation,
                    }), room_id, sender=websocket)

                elif msg_type == "WHITEBOARD_ERASE":
                    operation_id = data.get("operation_id")
                    if operation_id:
                        get_collection("collab_rooms").update_one(
                            {"room_id": room_id},
                            {"$pull": {"whiteboard": {"id": operation_id}}},
                        )
                    await collab_manager.broadcast_to_room(data_text, room_id, sender=websocket)

                elif msg_type == "WHITEBOARD_CLEAR":
                    get_collection("collab_rooms").update_one(
                        {"room_id": room_id},
                        {"$set": {"whiteboard": []}},
                    )
                    await collab_manager.broadcast_to_room(data_text, room_id, sender=websocket)

                # D. Task Progression — Move to next task
                elif msg_type == "NEXT_TASK":
                    await websocket.send_text(json.dumps({
                        "type": "TASK_LOCKED",
                        "message": "Submit the current task successfully before continuing.",
                    }))

                # E. Task Progression — Move to previous task
                elif msg_type == "PREV_TASK":
                    await websocket.send_text(json.dumps({
                        "type": "TASK_LOCKED",
                        "message": "Tasks must be completed in order.",
                    }))

                # F. Generic Fallback Broadcast
                else:
                    await collab_manager.broadcast_to_room(data_text, room_id, sender=websocket)

            except json.JSONDecodeError:
                # Direct string data එකක් ආවොත් (Raw Code Sync)
                collab_manager.update_code_state(room_id, data_text)
                await collab_manager.broadcast_to_room(data_text, room_id, sender=websocket)

    except WebSocketDisconnect:
        # Client disconnect වූ විට ලස්සනට Handle කිරීම (RuntimeError වැලැක්වීම)
        disconnected_student_id = collab_manager.disconnect(websocket, room_id)
        
        # Room එකේ ඉතිරි සිසුන්ට User Disconnected notification එකක් යැවීම
        leave_notice = json.dumps({
            "type": "USER_DISCONNECTED",
            "message": "A peer has left the session.",
            "active_users_count": len(collab_manager.active_rooms.get(room_id, []))
        })
        await collab_manager.broadcast_to_room(leave_notice, room_id, sender=websocket)
        if disconnected_student_id:
            await collab_manager.broadcast_all(json.dumps({
                "type": "PRESENCE_LEFT",
                "student_id": disconnected_student_id,
            }), room_id)

    except Exception as e:
        logger.error(f"Unexpected WebSocket error in room {room_id}: {str(e)}")
        collab_manager.disconnect(websocket, room_id)