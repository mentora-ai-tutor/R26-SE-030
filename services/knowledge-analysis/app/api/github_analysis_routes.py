"""
FastAPI routes for GitHub behavioral analysis.
Ready-to-use route handlers integrated with Ollama LLM.
"""

from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import logging

from app.core.github_analysis_config import OLLAMA_MODEL, OLLAMA_URL
from app.services import BehaviorAnalysisService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/github-analysis", tags=["github-analysis"])

# Initialize service (can inject into dependency or create once)
analysis_service = BehaviorAnalysisService(
    ollama_url=OLLAMA_URL,
    model=OLLAMA_MODEL,
)


# ============================================================================
# PYDANTIC MODELS
# ============================================================================


class CommitRequest(BaseModel):
    """Single commit data."""
    repo: str = Field(..., description="Repository name/identifier")
    message: str = Field(..., description="Commit message")
    timestamp: str = Field(..., description="Timestamp (ISO format or Unix)")
    additions: int = Field(..., ge=0, description="Lines added")
    deletions: int = Field(..., ge=0, description="Lines deleted")

    class Config:
        json_schema_extra = {
            "example": {
                "repo": "learning-project",
                "message": "Fix authentication bug",
                "timestamp": "2024-01-15T10:30:00Z",
                "additions": 45,
                "deletions": 12,
            }
        }


class AnalysisMetrics(BaseModel):
    """Behavioral metrics."""
    commit_count: int
    avg_time_gap_seconds: float
    message_quality: float
    big_bang_detected: bool
    total_additions: int
    total_deletions: int
    avg_commit_size: float
    repos_count: int


class AIAnalysis(BaseModel):
    """AI-based behavioral analysis."""
    weaknesses: List[str]
    ai_dependency: str
    reasoning: str
    recommendations: List[str]


class AnalysisResponse(BaseModel):
    """Complete analysis response."""
    status: str
    metrics: AnalysisMetrics
    ai_analysis: AIAnalysis


class ErrorResponse(BaseModel):
    """Error response."""
    status: str = "error"
    error: str
    type: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    ollama_available: bool


# ============================================================================
# ROUTES
# ============================================================================


@router.post(
    "/analyze",
    response_model=AnalysisResponse,
    responses={400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def analyze_student_commits(
    commits: List[CommitRequest] = Body(..., description="List of commits to analyze"),
) -> Dict[str, Any]:
    """
    Analyze student GitHub commits and generate behavioral assessment.

    This endpoint:
    1. Extracts behavioral metrics from commit history
    2. Generates analysis prompt for the AI model
    3. Gets assessment from Ollama LLM
    4. Returns structured analysis with weaknesses and recommendations

    **Request Example:**
    ```json
    [
        {
            "repo": "my-first-project",
            "message": "Fix user authentication bug in login endpoint",
            "timestamp": "2024-01-15T10:30:00Z",
            "additions": 45,
            "deletions": 12
        },
        {
            "repo": "api-project",
            "message": "Add request validation",
            "timestamp": "2024-01-20T14:00:00Z",
            "additions": 78,
            "deletions": 23
        }
    ]
    ```

    **Response Example:**
    ```json
    {
        "status": "success",
        "metrics": {
            "commit_count": 5,
            "avg_time_gap_seconds": 432000.0,
            "message_quality": 0.75,
            "big_bang_detected": false,
            "total_additions": 350,
            "total_deletions": 120,
            "avg_commit_size": 94.0,
            "repos_count": 2
        },
        "ai_analysis": {
            "weaknesses": [
                "Inconsistent commit frequency may indicate time management issues",
                "Some commits don't follow clear naming conventions"
            ],
            "ai_dependency": "Low",
            "reasoning": "Student shows good incremental development patterns...",
            "recommendations": [
                "Try to commit more frequently (daily if possible)",
                "Use conventional commit messages (feat:, fix:, refactor:)"
            ]
        }
    }
    ```
    """
    try:
        # Convert Pydantic models to dicts for service
        commits_data = [c.dict() for c in commits]

        # Run analysis
        result = await analysis_service.analyze_student_behavior(commits_data)

        # Handle errors from service
        if result["status"] == "error":
            logger.warning(f"Analysis validation error: {result.get('error')}")
            raise HTTPException(status_code=400, detail=result.get("error"))

        # Extract metrics and analysis for response
        metrics = AnalysisMetrics(**result["metrics"])
        ai_analysis = AIAnalysis(**result["ai_analysis"])

        return {
            "status": "success",
            "metrics": metrics,
            "ai_analysis": ai_analysis,
        }

    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"Validation error in analyze endpoint: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in analyze endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal analysis error")


@router.get("/health", response_model=HealthResponse)
async def health_check() -> Dict[str, Any]:
    """
    Check if GitHub analysis service and Ollama are available.

    **Response Example:**
    ```json
    {
        "status": "ok",
        "ollama_available": true
    }
    ```
    """
    try:
        is_available = await analysis_service.check_ollama_available()
        return {
            "status": "ok" if is_available else "degraded",
            "ollama_available": is_available,
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {"status": "error", "ollama_available": False}


@router.post(
    "/metrics-only",
    response_model=Dict[str, Any],
    responses={400: {"model": ErrorResponse}},
)
async def get_metrics_only(
    commits: List[CommitRequest] = Body(
        ..., description="List of commits to analyze for metrics"
    ),
) -> Dict[str, Any]:
    """
    Extract behavioral metrics without LLM analysis.
    Faster than full analysis when AI assessment is not needed.

    Returns only the behavioral metrics:
    - commit_count
    - avg_time_gap_seconds
    - message_quality
    - big_bang_detected
    - total_additions / total_deletions
    - avg_commit_size
    - repos_count
    """
    try:
        from app.services import GitHubAnalyzer

        commits_data = [c.dict() for c in commits]
        analyzer = GitHubAnalyzer()

        summary = analyzer.analyze_commits(commits_data)
        metrics = analyzer.to_dict(summary)

        return {"status": "success", "metrics": metrics}

    except ValueError as e:
        logger.warning(f"Metrics extraction error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error in metrics-only endpoint: {e}")
        raise HTTPException(status_code=500, detail="Metrics extraction failed")
