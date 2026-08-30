import os
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, Depends, HTTPException
from pydantic import BaseModel
from openai import OpenAI

from app.api.student_routes import decode_student_token, verify_jwt_student
from app.services.mongodb import get_collection, save_chat_session
from app.agents.support_agent import support_agent

logger = logging.getLogger("chat_routes")

router = APIRouter(prefix="/api/chat", tags=["Discussion Moderator & Support Agent"])


# --- WebSockets Connection Manager ---
class ConnectionManager:
    def __init__(self):
        # Stores active websocket connections per room
        self.active_connections: Dict[str, List[WebSocket]] = {}
        self.chat_history: Dict[str, List[str]] = {}

    async def connect(self, websocket: WebSocket, room_id: str):
        await websocket.accept()
        if room_id not in self.active_connections:
            self.active_connections[room_id] = []
        self.active_connections[room_id].append(websocket)

        # Restore the room chat from persistent storage on every connection.
        try:
            stored_messages = get_collection("collab_chat_messages").find(
                {"room_id": room_id}
            ).sort("timestamp", 1)
            self.chat_history[room_id] = [
                message.get("raw_message")
                or json.dumps({
                    "sender": message.get("sender_name") or message.get("sender_id", message.get("student_id", "Unknown")),
                    "content": message.get("message", ""),
                })
                for message in stored_messages
            ]
        except Exception as error:
            logger.warning(f"Unable to restore chat history for room {room_id}: {error}")

        history_messages = []
        for message in self.chat_history.get(room_id, []):
            try:
                history_messages.append(json.loads(message))
            except json.JSONDecodeError:
                history_messages.append({"sender": "Unknown", "content": message})

        await websocket.send_text(json.dumps({
            "type": "CHAT_HISTORY",
            "room_id": room_id,
            "messages": history_messages,
        }))

    def disconnect(self, websocket: WebSocket, room_id: str):
        if room_id in self.active_connections:
            self.active_connections[room_id].remove(websocket)
            if not self.active_connections[room_id]:
                del self.active_connections[room_id]

    async def broadcast(self, message: str, room_id: str):
        if room_id in self.active_connections:
            for connection in self.active_connections[room_id]:
                await connection.send_text(message)

    def add_message(self, room_id: str, message: str):
        self.chat_history.setdefault(room_id, []).append(message)

    def save_message(self, room_id: str, student_id: str, message: str):
        """Persist a raw chat event without changing the client message format."""
        try:
            get_collection("collab_chat_messages").insert_one({
                "room_id": room_id,
                "student_id": student_id,
                "sender_id": student_id,
                "message": message,
                "raw_message": message,
                "timestamp": datetime.utcnow().isoformat(),
            })
        except Exception as error:
            logger.warning(f"Unable to persist chat message for room {room_id}: {error}")


manager = ConnectionManager()


# --- AI Discussion Moderator Agent Logic ---
class DiscussionModeratorAgent:
    """Agent responsible for monitoring chat, summarizing discussion,
    and keeping peer discussions focused on Java pedagogy."""

    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            self.client = OpenAI(api_key=api_key)
            self.model_name = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        else:
            self.client = None

    def analyze_message(self, student_id: str, message: str) -> dict:
        # Check for Java/Programming context keywords
        java_keywords = [
            "java",
            "class",
            "object",
            "recursion",
            "loop",
            "method",
            "code",
            "bug",
            "error",
            "array",
            "exception",
            "interface",
            "override",
        ]
        is_relevant = any(kw in message.lower() for kw in java_keywords)

        if is_relevant:
            moderator_note = (
                f"💡 [AI Moderator]: Good technical discussion point regarding Java concepts by {student_id}."
            )
        else:
            moderator_note = (
                f"⚠️ [AI Moderator]: Reminder - Please keep the peer discussion focused on Java pedagogy and problem-solving."
            )

        return {
            "type": "moderator_insight",
            "student_id": student_id,
            "is_relevant": is_relevant,
            "moderator_note": moderator_note,
        }

    def generate_session_summary(self, chat_history: List[str]) -> dict:
        """Generates a dynamic AI summary with structured key_learning_points array."""
        if not chat_history:
            return {
                "status": "warning",
                "total_messages": 0,
                "summary": "No messages were recorded in this peer discussion session to summarize.",
                "key_learning_points": []
            }

        if not self.client:
            return {
                "status": "success",
                "total_messages": len(chat_history),
                "summary": f"Peer session completed with {len(chat_history)} messages.",
                "key_learning_points": ["Collaborative Java discussion completed."]
            }

        try:
            prompt = f"""
            Analyze the following peer learning chat session between matched students studying Java:
            Chat Transcript History: {chat_history}

            Respond strictly in valid JSON format with two keys:
            1. "summary": A concise overview string explaining what students discussed and resolved.
            2. "key_learning_points": A list of 2-4 strings representing specific Java concepts, takeaways, or bug fixes mastered.
            """

            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": "You analyze student peer-learning interactions. Always respond in valid JSON format."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.5,
                max_tokens=400
            )

            parsed_data = json.loads(response.choices[0].message.content.strip())

            return {
                "status": "success",
                "total_messages": len(chat_history),
                "summary": parsed_data.get("summary", "Discussion session completed."),
                "key_learning_points": parsed_data.get("key_learning_points", ["Peer collaboration finished"]),
                "generated_at": datetime.utcnow().isoformat()
            }

        except Exception as e:
            logger.error(f"Error generating AI peer session summary: {str(e)}")
            return {
                "status": "error",
                "total_messages": len(chat_history),
                "summary": "Failed to generate AI summary.",
                "key_learning_points": ["Session overview logged"],
                "error": str(e)
            }


moderator_agent = DiscussionModeratorAgent()


# --- Pydantic Models ---
class ChatMessageRequest(BaseModel):
    message: str


# --- HTTP Endpoint for AI Support Chatbot (OpenAI Powered) ---
@router.post("/support")
def chat_support(
    request: ChatMessageRequest,
    token_student_id: str = Depends(verify_jwt_student),
):
    """
    Endpoint for individual student support assistant and Java pedagogy queries.
    Uses OpenAI API configured inside SupportAgent.
    student_id is auto-fetched from the JWT token.
    """
    try:
        response = support_agent.get_response(
            user_message=request.message,
            student_id=token_student_id
        )
        return response
    except Exception as e:
        logger.error(f"Error in /api/chat/support endpoint: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Chat support endpoint error: {str(e)}")


# --- WebSocket Endpoint for Real-time Peer Discussion & Moderation ---
@router.websocket("/ws/{room_id}/{student_id}")
async def websocket_chat_moderator(
    websocket: WebSocket,
    room_id: str,
    student_id: str,
    token: str = Query(...),
):
    try:
        authenticated_student_id = decode_student_token(token)
        if authenticated_student_id != student_id:
            await websocket.close(code=1008)
            return
    except Exception:
        await websocket.close(code=1008)
        return

    await manager.connect(websocket, room_id)

    # Announce student joined
    join_message = json.dumps(
        {
            "sender": "System",
            "content": f"Student {student_id} joined discussion room {room_id}.",
        }
    )
    await manager.broadcast(join_message, room_id)

    try:
        while True:
            # Receive real-time chat message from student
            data = await websocket.receive_text()
            manager.add_message(room_id, data)
            manager.save_message(room_id, student_id, data)

            # Broadcast student's original message to all peers in the room
            user_msg = json.dumps({"sender": student_id, "content": data})
            await manager.broadcast(user_msg, room_id)

            # Pass message through Discussion Moderator Agent
            moderation_result = moderator_agent.analyze_message(student_id, data)

            # Broadcast AI Moderator's insight/feedback
            moderator_msg = json.dumps(
                {
                    "sender": "AI Moderator Agent",
                    "content": moderation_result["moderator_note"],
                }
            )
            manager.add_message(room_id, moderator_msg)
            manager.save_message(room_id, "AI Moderator Agent", moderator_msg)
            await manager.broadcast(moderator_msg, room_id)

    except WebSocketDisconnect:
        manager.disconnect(websocket, room_id)
        leave_message = json.dumps(
            {
                "sender": "System",
                "content": f"Student {student_id} left room {room_id}.",
            }
        )
        await manager.broadcast(leave_message, room_id)


# --- HTTP Endpoint to Summarize Discussion Session ---
@router.post("/summarize-session")
def summarize_discussion(
    room_id: str = Query(...),
    token_student_id: str = Depends(verify_jwt_student),
):
    """Endpoint triggered when a peer coding/chat session ends to produce a summary."""
    chat_history = manager.chat_history.get(room_id, [])
    if not chat_history:
        try:
            stored_messages = get_collection("collab_chat_messages").find(
                {"room_id": room_id}
            ).sort("timestamp", 1)
            chat_history = [
                message.get("raw_message")
                or json.dumps({
                    "sender": message.get("sender_name") or message.get("sender_id", message.get("student_id", "Unknown")),
                    "content": message.get("message", ""),
                })
                for message in stored_messages
            ]
        except Exception as error:
            logger.warning(f"Unable to load persisted chat for room {room_id}: {error}")

    summary_data = moderator_agent.generate_session_summary(chat_history)

    # Save the discussion session summary to MongoDB
    save_chat_session({
        "room_id": room_id,
        "student_id": token_student_id,
        "chat_history": chat_history,
        "summary": summary_data,
        "ended_at": datetime.utcnow().isoformat(),
    })

    return summary_data