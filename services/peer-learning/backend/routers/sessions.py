# backend/routers/sessions.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from database import get_db
from services.question_service import generate_question, evaluate_answer
from services.performance_service import complete_pair_session
import asyncio, json
from datetime import datetime

router = APIRouter()

# Tracks active WebSocket connections: {session_id: {student_id: websocket}}
active_connections: dict = {}

@router.websocket("/ws/pair/{session_id}/{student_id}")
async def pair_session_websocket(websocket: WebSocket, session_id: str, student_id: str):
    await websocket.accept()
    
    # Register this connection
    if session_id not in active_connections:
        active_connections[session_id] = {}
    active_connections[session_id][student_id] = websocket
    
    db = get_db()
    session = await db.pair_sessions.find_one({"session_id": session_id})
    is_learner = (student_id == session["learner_id"])
    
    try:
        if is_learner:
            await run_learner_flow(websocket, session_id, session, db)
        else:
            await run_teacher_standby(websocket, session_id, student_id)
    
    except WebSocketDisconnect:
        del active_connections[session_id][student_id]

async def run_learner_flow(websocket: WebSocket, session_id: str, session: dict, db):
    """Manages the question-answer loop for the learner."""
    
    # Get learner's misconceptions for better question generation
    learner = await db.students.find_one({"student_id": session["learner_id"]})
    weak_topic = next(
        (w for w in learner["weaknesses"] if w["topic_id"] == session["topic_id"]),
        {}
    )
    misconceptions = weak_topic.get("misconceptions", [])
    
    MAX_QUESTIONS = 10
    
    for q_num in range(1, MAX_QUESTIONS + 1):
        
        # Generate a fresh question
        question_data = await generate_question(
            topic=session["topic_name"],
            misconceptions=misconceptions,
            difficulty="beginner"
        )
        
        # Send question to learner
        await websocket.send_json({
            "type": "NEW_QUESTION",
            "question_number": q_num,
            "total_questions": MAX_QUESTIONS,
            "question": question_data["question"],
            "time_limit_seconds": 120
        })
        
        # Log this question in MongoDB
        await db.pair_sessions.update_one(
            {"session_id": session_id},
            {
                "$inc": {"questions_asked": 1},
                "$push": {
                    "question_log": {
                        "question_number": q_num,
                        "question_text": question_data["question"],
                        "started_at": datetime.utcnow().isoformat(),
                        "answered": False,
                        "correct": None,
                        "hints_used": 0,
                        "help_from_teacher": False
                    }
                }
            }
        )
        
        answered = False
        hint_level = 0
        
        # Wait for answer with 120 second timeout
        while not answered:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=120)
                data = json.loads(raw)
                
                if data["type"] == "SUBMIT_ANSWER":
                    result = await evaluate_answer(
                        question_data["question"],
                        data["answer"],
                        question_data["expected_answer"]
                    )
                    
                    if result["correct"]:
                        await db.pair_sessions.update_one(
                            {"session_id": session_id},
                            {"$inc": {"correct_answers": 1}}
                        )
                        await websocket.send_json({
                            "type": "ANSWER_CORRECT",
                            "feedback": result["feedback"],
                            "score": result["score"]
                        })
                        answered = True
                    else:
                        await websocket.send_json({
                            "type": "ANSWER_WRONG",
                            "feedback": result["feedback"]
                        })
                
                elif data["type"] == "REQUEST_HINT":
                    if hint_level < 3:
                        await websocket.send_json({
                            "type": "HINT",
                            "hint": question_data["hints"][hint_level],
                            "hint_level": hint_level + 1
                        })
                        hint_level += 1
                        await db.pair_sessions.update_one(
                            {"session_id": session_id},
                            {"$inc": {"hints_used_by_learner": 1}}
                        )
                    else:
                        await websocket.send_json({
                            "type": "NO_MORE_HINTS",
                            "message": "You've used all hints. Would you like to ask your teacher?"
                        })
                
                elif data["type"] == "ASK_TEACHER":
                    # Notify teacher's WebSocket
                    await notify_teacher(session_id, session["teacher_id"], question_data)
                    await db.pair_sessions.update_one(
                        {"session_id": session_id},
                        {"$inc": {"help_requests": 1}}
                    )
                    await websocket.send_json({
                        "type": "TEACHER_NOTIFIED",
                        "message": "Your teacher has been asked to explain. Please wait..."
                    })
                
                elif data["type"] == "TEACHER_EXPLAINED":
                    # Teacher finished explaining, give similar question
                    await websocket.send_json({
                        "type": "SIMILAR_QUESTION",
                        "question": question_data["similar_question"],
                        "message": "Now try this similar question to check your understanding."
                    })
                    answered = True  # move on after teacher explanation
            
            except asyncio.TimeoutError:
                await websocket.send_json({
                    "type": "TIME_EXPIRED",
                    "message": "Time's up! You can request a hint or ask your teacher.",
                    "options": ["REQUEST_HINT", "ASK_TEACHER"]
                })
    
    # All questions done — calculate final result
    updated_session = await db.pair_sessions.find_one({"session_id": session_id})
    result = await complete_pair_session(session_id)
    
    await websocket.send_json({
        "type": "SESSION_COMPLETE",
        "score": result["score"],
        "decision": result["decision"],
        "message": get_decision_message(result["decision"])
    })

async def notify_teacher(session_id: str, teacher_id: str, question_data: dict):
    """Send a message to the teacher's WebSocket to ask them to explain."""
    if session_id in active_connections and teacher_id in active_connections[session_id]:
        teacher_ws = active_connections[session_id][teacher_id]
        await teacher_ws.send_json({
            "type": "LEARNER_NEEDS_HELP",
            "question": question_data["question"],
            "expected_answer": question_data["expected_answer"],
            "message": "Your learner is stuck! Please explain this question."
        })

async def run_teacher_standby(websocket: WebSocket, session_id: str, teacher_id: str):
    """Teacher waits in standby mode, receiving help requests as they come."""
    await websocket.send_json({
        "type": "TEACHER_STANDBY",
        "message": "Session active. You'll be notified when your student needs help."
    })
    
    # Keep connection alive, handle teacher messages
    while True:
        try:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            
            if data["type"] == "TEACHER_DONE_EXPLAINING":
                # Notify learner that teacher is done
                db = get_db()
                session = await db.pair_sessions.find_one({"session_id": session_id})
                learner_id = session["learner_id"]
                if session_id in active_connections and learner_id in active_connections[session_id]:
                    learner_ws = active_connections[session_id][learner_id]
                    await learner_ws.send_json({"type": "TEACHER_EXPLAINED"})
        
        except WebSocketDisconnect:
            break

def get_decision_message(decision: str) -> str:
    messages = {
        "MASTERED": "Excellent! You've mastered this topic. You've been added to the topic pool!",
        "REGROUP": "Don't worry! We'll match you with a different teacher for another try.",
        "CONTINUE": "Good effort! More practice will help. Continuing with your current teacher."
    }
    return messages.get(decision, "Session ended.")