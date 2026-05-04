from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
import sys

from app.core.config import settings
from app.core.database import connect_db, disconnect_db
from app.api import api_router
# from app.services.notification_service import start_background_matching, stop_background_matching

# ─── Logging ──────────────────────────────────────────────────────────────────
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="DEBUG" if settings.app_debug else "INFO",
)
logger.add("logs/app.log", rotation="10 MB", retention="7 days", level="DEBUG")


# ─── Lifespan ─────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Peer Learning System...")
    await connect_db()
    # start_background_matching()
    logger.info(f"Server running on {settings.app_host}:{settings.app_port}")
    yield
    # Shutdown
    logger.info("Shutting down...")
    # stop_background_matching()
    await disconnect_db()


# ─── App ──────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Collaborative Peer Learning & Knowledge Exchange Agent",
    description="""
## System Overview

This system facilitates peer-to-peer learning by:
- Matching students (learners) with teachers using the **Hungarian Algorithm**
- Generating adaptive questions using **Bloom's Taxonomy** via **gemma4 (Ollama)**
- Tracking mastery through pair and group sessions
- Promoting students from Learner → Skilled Student → Teacher

## Phases
1. Data Ingestion — Import student profiles
2. Pair Formation — Hungarian algorithm matching
3. Interactive Sessions — LLM-powered questions with Bloom's progression
4. Performance Scoring — Learner & teacher evaluation
5. Improved Pool — Students who mastered a topic
6. Waiting Queue — Notification system for teacher availability
7. Group Sessions — 3-student collaborative learning
8. Teacher Gap Resolution — Teachers improve their own gaps
9. Question Bank — Persistent question storage & analytics
10. Verification — Certified mastery
11. Completion — Full mastery report
    """,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ─── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routes ───────────────────────────────────────────────────────────────────
app.include_router(api_router)


# ─── Health ───────────────────────────────────────────────────────────────────
@app.get("/health", tags=["Health"])
async def health_check():
    from app.core.database import db
    try:
        await db.command("ping")
        db_status = "connected"
    except Exception:
        db_status = "disconnected"

    return {
        "status": "ok",
        "database": db_status,
        "model": settings.ollama_model,
        "version": "1.0.0",
    }


@app.get("/", tags=["Root"])
async def root():
    return {
        "message": "Collaborative Peer Learning System",
        "docs": "/docs",
        "health": "/health",
    }
