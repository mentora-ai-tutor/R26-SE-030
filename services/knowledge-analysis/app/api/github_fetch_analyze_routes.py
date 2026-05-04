"""
GitHub fetch and analyze routes.
Fetches commits from GitHub and analyzes behavioral patterns.
"""

from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel, Field
from typing import Optional
import logging

from app.services import GitHubFetcher, BehaviorAnalysisService
from app.core.github_analysis_config import (
    GITHUB_PAT,
    GITHUB_API_URL,
    GITHUB_API_TIMEOUT,
    GITHUB_FETCH_DAYS,
    GITHUB_FETCH_PER_PAGE,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/github-fetch-analyze", tags=["github-fetch-analyze"]
)


# ============================================================================
# PYDANTIC MODELS
# ============================================================================


class FetchAndAnalyzeRequest(BaseModel):
    """Request to fetch and analyze GitHub repository."""
    repo: str = Field(
        ..., description="Repository in format 'owner/repo' or GitHub URL"
    )
    days: int = Field(
        default=GITHUB_FETCH_DAYS,
        ge=1,
        le=365,
        description="Days to look back (1-365)",
    )
    author: Optional[str] = Field(
        default=None, description="Filter by author username (optional)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "repo": "owner/repo",
                "days": 30,
                "author": None,
            }
        }


class FetchOnlyRequest(BaseModel):
    """Request to fetch commits only."""
    repo: str = Field(..., description="Repository in format 'owner/repo'")
    days: int = Field(default=GITHUB_FETCH_DAYS, ge=1, le=365)
    author: Optional[str] = Field(default=None)


class FetchOnlyResponse(BaseModel):
    """Response with fetched commits."""
    status: str
    count: int
    commits: list


# ============================================================================
# ROUTES
# ============================================================================


@router.post("/fetch-and-analyze")
async def fetch_and_analyze(
    request: FetchAndAnalyzeRequest = Body(...),
) -> dict:
    """
    Fetch commits from GitHub and analyze behavioral patterns.

    This endpoint:
    1. Fetches commits from GitHub API using PAT
    2. Analyzes commit patterns
    3. Generates AI assessment

    **Request:**
    ```json
    {
        "repo": "owner/repo",
        "days": 30,
        "author": null
    }
    ```

    **Response:**
    ```json
    {
        "status": "success",
        "fetch_info": {
            "repository": "owner/repo",
            "commits_fetched": 15,
            "days_analyzed": 30
        },
        "metrics": {...},
        "ai_analysis": {...}
    }
    ```
    """
    if not GITHUB_PAT:
        logger.error("GitHub PAT not configured")
        raise HTTPException(
            status_code=503, detail="GitHub API not configured (missing GITHUB_PAT)"
        )

    try:
        # Initialize fetcher
        fetcher = GitHubFetcher(
            token=GITHUB_PAT,
            base_url=GITHUB_API_URL,
            timeout=GITHUB_API_TIMEOUT,
        )

        logger.info(f"Fetching commits from {request.repo}")

        # Fetch commits from GitHub
        commits = await fetcher.get_commits(
            repo=request.repo,
            days=request.days,
            per_page=GITHUB_FETCH_PER_PAGE,
            author=request.author,
        )

        if not commits:
            return {
                "status": "no_commits",
                "message": f"No commits found in {request.repo} for the last {request.days} days",
            }

        logger.info(f"Fetched {len(commits)} commits, starting analysis")

        # Analyze commits
        analyzer_service = BehaviorAnalysisService()
        analysis_result = await analyzer_service.analyze_student_behavior(commits)

        if analysis_result["status"] != "success":
            logger.error(f"Analysis failed: {analysis_result.get('error')}")
            raise HTTPException(
                status_code=400, detail=analysis_result.get("error")
            )

        # Combine fetch and analysis results
        return {
            "status": "success",
            "fetch_info": {
                "repository": request.repo,
                "commits_fetched": len(commits),
                "days_analyzed": request.days,
                "author_filter": request.author,
            },
            "metrics": analysis_result["metrics"],
            "ai_analysis": analysis_result["ai_analysis"],
        }

    except Exception as e:
        logger.error(f"Fetch and analyze failed: {e}", exc_info=True)
        error_msg = str(e)

        if "authentication" in error_msg.lower():
            raise HTTPException(status_code=401, detail="GitHub authentication failed")
        elif "rate limit" in error_msg.lower():
            raise HTTPException(status_code=429, detail="GitHub rate limit exceeded")
        elif "not found" in error_msg.lower():
            raise HTTPException(status_code=404, detail=error_msg)
        else:
            raise HTTPException(status_code=500, detail=error_msg)


@router.post("/fetch-only", response_model=FetchOnlyResponse)
async def fetch_commits_only(
    request: FetchOnlyRequest = Body(...),
) -> dict:
    """
    Fetch commits from GitHub only (no analysis).

    Useful for getting raw commit data to analyze separately.

    **Response:**
    ```json
    {
        "status": "success",
        "count": 15,
        "commits": [
            {
                "repo": "owner/repo",
                "message": "Add feature",
                "timestamp": "2024-01-15T10:30:00Z",
                "additions": 50,
                "deletions": 10,
                "author": "username",
                "sha": "abc123..."
            }
        ]
    }
    ```
    """
    if not GITHUB_PAT:
        logger.error("GitHub PAT not configured")
        raise HTTPException(
            status_code=503, detail="GitHub API not configured (missing GITHUB_PAT)"
        )

    try:
        fetcher = GitHubFetcher(
            token=GITHUB_PAT,
            base_url=GITHUB_API_URL,
            timeout=GITHUB_API_TIMEOUT,
        )

        logger.info(f"Fetching commits from {request.repo}")

        commits = await fetcher.get_commits(
            repo=request.repo,
            days=request.days,
            per_page=GITHUB_FETCH_PER_PAGE,
            author=request.author,
        )

        return {
            "status": "success",
            "count": len(commits),
            "commits": commits,
        }

    except Exception as e:
        logger.error(f"Fetch failed: {e}")
        error_msg = str(e)

        if "authentication" in error_msg.lower():
            raise HTTPException(status_code=401, detail="GitHub authentication failed")
        elif "rate limit" in error_msg.lower():
            raise HTTPException(status_code=429, detail="GitHub rate limit exceeded")
        elif "not found" in error_msg.lower():
            raise HTTPException(status_code=404, detail=error_msg)
        else:
            raise HTTPException(status_code=500, detail=error_msg)


@router.get("/check-github-auth")
async def check_github_auth() -> dict:
    """
    Check if GitHub authentication is working.

    Returns status of GitHub API connection.
    """
    if not GITHUB_PAT:
        return {"status": "error", "message": "GitHub PAT not configured"}

    try:
        fetcher = GitHubFetcher(
            token=GITHUB_PAT,
            base_url=GITHUB_API_URL,
            timeout=GITHUB_API_TIMEOUT,
        )

        is_auth = await fetcher.check_auth()

        if is_auth:
            # Get rate limit info
            rate_limit = await fetcher.get_rate_limit()
            remaining = (
                rate_limit.get("rate", {}).get("remaining", "unknown")
                if rate_limit
                else "unknown"
            )

            return {
                "status": "authenticated",
                "rate_limit_remaining": remaining,
            }
        else:
            return {
                "status": "error",
                "message": "Authentication failed",
            }

    except Exception as e:
        logger.error(f"Auth check failed: {e}")
        return {
            "status": "error",
            "message": str(e),
        }
