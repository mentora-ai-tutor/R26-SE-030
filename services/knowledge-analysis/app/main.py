from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router as api_router
from app.api.github_analysis_routes import router as github_analysis_router
from app.api.github_fetch_analyze_routes import router as github_fetch_analyze_router
from app.api.github_review_routes import router as github_review_router
from app.api.knowledge_profile_routes import router as knowledge_profile_router
from app.core.config import APP_NAME, APP_VERSION, CORS_ORIGINS

app = FastAPI(title=APP_NAME, version=APP_VERSION)

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
