import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as api_router
from app.api.github_analysis_routes import router as github_analysis_router
from app.api.github_fetch_analyze_routes import router as github_fetch_analyze_router
from app.api.github_review_routes import router as github_review_router
from app.api.knowledge_profile_routes import (
    ensure_knowledge_profile_indexes,
    router as knowledge_profile_router,
)
from app.api.career_routes import router as career_router
from app.api.mastery_profile_routes import router as mastery_profile_router
from app.api.quiz_routes import router as quiz_router
from app.api.sandbox_routes import router as sandbox_router
from app.core.config import APP_NAME, APP_VERSION, CORS_ORIGINS
from app.services.career.store import ensure_career_indexes
from app.services.mastery_profile_store import ensure_mastery_profile_indexes
from app.services.quiz_store import ensure_quiz_indexes
from app.services.sandbox_challenge_generator import ensure_sandbox_challenge_indexes

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create Mongo indexes once at startup instead of on every request.
    # Tolerate Mongo being unreachable at boot so the service still starts.
    try:
        await ensure_mastery_profile_indexes()
        await ensure_knowledge_profile_indexes()
        await ensure_quiz_indexes()
        await ensure_sandbox_challenge_indexes()
        await ensure_career_indexes()
    except Exception as exc:  # pragma: no cover - startup best effort
        logger.warning("Index creation skipped at startup: %s", exc)
    yield


app = FastAPI(title=APP_NAME, version=APP_VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS if CORS_ORIGINS else ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
app.include_router(github_analysis_router)
app.include_router(github_fetch_analyze_router)
app.include_router(github_review_router)
app.include_router(knowledge_profile_router)
app.include_router(mastery_profile_router)
app.include_router(quiz_router)
app.include_router(sandbox_router)
app.include_router(career_router)
