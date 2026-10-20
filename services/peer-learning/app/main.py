from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import socketio
import json

# Import API routes with correct aliases
from app.services.mongodb import close_db, init_db
from app.api.assessment_routes import router as assessment_router
from app.api.chat_routes import router as chat_router
from app.api.collab_routes import router as collab_router
from app.api.individual_quiz_routes import router as individual_quiz_router
from app.api.peer_routes import router as peer_router
from app.api.rag_routes import recommend_learning_materials, router as rag_router
from app.api.student_routes import router as student_router
from app.api.question_generator_routes import router as question_generator_router  # 👈 1. මෙතැන Import කළා
from app.models.schemas import RecommendationRequest, RecommendationResponse

# ---------------------------------------------------------------------------
# 1. SOCKET.IO SERVER INITIALIZATION & REAL-TIME EVENTS
# ---------------------------------------------------------------------------
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins='*'
)

@sio.event
async def connect(sid, environ):
    print(f"[Socket.IO] Client connected: {sid}")

@sio.event
async def join_room(sid, data):
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:
            data = {"room_id": data}

    room_id = data.get('room_id') if isinstance(data, dict) else None
    username = data.get('username', 'Anonymous') if isinstance(data, dict) else 'Anonymous'
    
    if room_id:
        await sio.enter_room(sid, room_id)
        print(f"[Socket.IO] {username} ({sid}) joined room: {room_id}")

# ✏️ Real-time Pencil Drawing Broadcast Event
@sio.event
async def draw_line(sid, data):
    room_id = data.get('room_id') if isinstance(data, dict) else None
    if room_id:
        await sio.emit('receive_line', data, room=room_id, skip_sid=sid)
        print(f"[Socket.IO] Broadcasted draw_line to room: {room_id}")

# 🧹 Clear Canvas Sync Event
@sio.event
async def clear_canvas(sid, data):
    room_id = data.get('room_id') if isinstance(data, dict) else None
    if room_id:
        await sio.emit('canvas_cleared', data, room=room_id, skip_sid=sid)
        print(f"[Socket.IO] Broadcasted clear_canvas to room: {room_id}")

@sio.event
async def disconnect(sid):
    print(f"[Socket.IO] Client disconnected: {sid}")


# ---------------------------------------------------------------------------
# 2. FASTAPI LIFESPAN & ROUTER SETUP
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: MongoDB Connection
    init_db()
    yield
    # Shutdown: Close DB
    close_db()

fastapi_app = FastAPI(
    title="Java Multi-Agent Pedagogy Platform API",
    description="Backend platform for Java collaborative learning using specialized AI Agents.",
    version="1.2.0",
    lifespan=lifespan,
)

# CORS Middlewares
fastapi_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register All Routers
fastapi_app.include_router(student_router)         # Agent 1: Diagnostic & Learning Agent
fastapi_app.include_router(assessment_router)      # Agent 2: Assessment Agent
fastapi_app.include_router(rag_router)             # Agent 3: RAG Route (/api/rag-content/recommend)
fastapi_app.include_router(peer_router)            # Agent 4: Peer Matching Agent
fastapi_app.include_router(chat_router)            # Agent 5: Chat Moderator Agent
fastapi_app.include_router(collab_router)          # Live Code Editor Router
fastapi_app.include_router(individual_quiz_router) # Individual Quiz Router (/api/individual-quiz)
fastapi_app.include_router(question_generator_router) # 👈 2. මෙතැන Router එක Register කළා


# ---------------------------------------------------------------------------
# 3. LEGACY ENDPOINTS & HEALTH CHECK
# ---------------------------------------------------------------------------
@fastapi_app.post("/api/content/recommend", response_model=RecommendationResponse, tags=["Content Recommendation (Legacy Mapping)"])
def legacy_recommend_content(request: RecommendationRequest):
    return recommend_learning_materials(request)


@fastapi_app.get("/", tags=["Health Check"])
def root_status():
    """System Health Check Endpoint"""
    return {
        "status": "online",
        "system_status": "online",
        "platform": "Java Multi-Agent Pedagogy Platform",
        "message": "All AI Pedagogy Agents, Individual Quiz system, Question Generator, and RAG services are operational.",
    }


# ---------------------------------------------------------------------------
# 4. WRAP FASTAPI WITH SOCKET.IO ASGI APP
# ---------------------------------------------------------------------------
app = socketio.ASGIApp(sio, fastapi_app, socketio_path='/socket.io')