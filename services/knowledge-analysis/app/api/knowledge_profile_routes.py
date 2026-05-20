from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from bson import ObjectId
from fastapi import APIRouter, Header
from pydantic import BaseModel, Field

from app.db.database import get_database
from app.services.github_review_service import (
    serialize_job,
    verify_student_from_authorization,
)

router = APIRouter(prefix="/api/v1/knowledge-profile", tags=["knowledge-profile"])


class SandboxAttemptRequest(BaseModel):
    challenge_id: str = Field(..., min_length=1, max_length=80)
    title: str = Field(..., min_length=1, max_length=140)
    topic: str = Field(..., min_length=1, max_length=80)
    difficulty: Optional[str] = Field(default=None, max_length=80)
    code: str = Field(..., min_length=1, max_length=30_000)
    stdin: Optional[str] = Field(default=None, max_length=5_000)
    expected_output: str = Field(..., max_length=5_000)
    output: Optional[str] = Field(default=None, max_length=20_000)
    error: Optional[str] = Field(default=None, max_length=20_000)
    success: bool
    passed: bool
    attempt_number: int = Field(..., ge=1)
    runtime_ms: Optional[int] = Field(default=None, ge=0)
    review_job_id: Optional[str] = Field(default=None, max_length=80)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _json_safe(value: Any) -> Any:
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    return value


def _serialize_attempt(doc: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not doc:
        return None
    out = _json_safe(doc)
    if "_id" in out:
        out["attempt_id"] = out.pop("_id")
    return out


async def _ensure_profile_indexes() -> None:
    db = get_database()
    await db.sandbox_attempts.create_index([("student_id", 1), ("created_at", -1)])
    await db.sandbox_attempts.create_index([("student_id", 1), ("challenge_id", 1)])
    await db.repo_review_jobs.create_index([("student_id", 1), ("created_at", -1)])


def _repo_review_stats(jobs: list[dict[str, Any]]) -> dict[str, Any]:
    total_repos = 0
    reviewed = 0
    failed = 0
    findings = 0
    high_risk = 0
    latest_java_level = None
    latest_evidence = None

    for job in jobs:
        if not latest_java_level and job.get("java_level_inferred"):
            latest_java_level = job.get("java_level_inferred")
            latest_evidence = job.get("signals_evidence")

        for repo in job.get("repos", []):
            total_repos += 1
            if repo.get("status") == "done":
                reviewed += 1
            if repo.get("status") == "error":
                failed += 1
            errors = ((repo.get("review") or {}).get("errors") or [])
            findings += len(errors)
            high_risk += sum(1 for item in errors if item.get("severity") == "high")

    return {
        "jobs": len(jobs),
        "total_repos": total_repos,
        "reviewed": reviewed,
        "failed": failed,
        "findings": findings,
        "high_risk": high_risk,
        "latest_java_level": latest_java_level,
        "latest_evidence": latest_evidence,
    }


def _sandbox_stats(attempts: list[dict[str, Any]], total_attempts: int) -> dict[str, Any]:
    passed = sum(1 for attempt in attempts if attempt.get("passed"))
    latest_by_topic: dict[str, dict[str, Any]] = {}

    for attempt in attempts:
        topic = attempt.get("topic") or attempt.get("title") or "Unknown"
        current = latest_by_topic.get(topic)
        if not current:
            latest_by_topic[topic] = {
                "topic": topic,
                "challenge_id": attempt.get("challenge_id"),
                "title": attempt.get("title"),
                "attempts": 1,
                "passed": 1 if attempt.get("passed") else 0,
                "latest_code": attempt.get("code"),
                "latest_output": attempt.get("output"),
                "latest_error": attempt.get("error"),
                "latest_at": attempt.get("created_at"),
            }
            continue

        current["attempts"] += 1
        current["passed"] += 1 if attempt.get("passed") else 0

    return {
        "total_attempts": total_attempts,
        "recent_attempts": len(attempts),
        "recent_passed": passed,
        "recent_pass_rate": round(passed / len(attempts), 3) if attempts else 0,
        "topics": list(latest_by_topic.values()),
    }


def _timeline(
    review_jobs: list[dict[str, Any]],
    sandbox_attempts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []

    for job in review_jobs:
        events.append(
            {
                "type": "github_review",
                "id": str(job.get("_id")),
                "label": f"GitHub review {job.get('status')}",
                "time": job.get("updated_at") or job.get("created_at"),
                "status": job.get("status"),
                "repo_count": len(job.get("repos", [])),
            }
        )

    for attempt in sandbox_attempts:
        events.append(
            {
                "type": "sandbox_attempt",
                "id": str(attempt.get("_id")),
                "label": f"Sandbox: {attempt.get('title')}",
                "time": attempt.get("created_at"),
                "status": "passed" if attempt.get("passed") else "needs_fix",
                "attempt_number": attempt.get("attempt_number"),
            }
        )

    return sorted(
        (_json_safe(event) for event in events),
        key=lambda event: event.get("time") or "",
        reverse=True,
    )[:20]


@router.post("/sandbox-attempts")
async def save_sandbox_attempt(
    payload: SandboxAttemptRequest,
    authorization: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    student = await verify_student_from_authorization(authorization)
    await _ensure_profile_indexes()

    now = _utcnow()
    doc = payload.model_dump()
    doc.update(
        {
            "student_id": student.id,
            "public_student_id": student.student_id,
            "source": "sandbox",
            "created_at": now,
            "updated_at": now,
        }
    )

    db = get_database()
    insert = await db.sandbox_attempts.insert_one(doc)
    created = await db.sandbox_attempts.find_one({"_id": insert.inserted_id})
    return {"status": "success", "data": _serialize_attempt(created)}


@router.get("/me")
async def get_my_knowledge_profile(
    authorization: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    student = await verify_student_from_authorization(authorization)
    await _ensure_profile_indexes()

    db = get_database()
    review_jobs = await db.repo_review_jobs.find(
        {"student_id": student.id}
    ).sort("created_at", -1).limit(8).to_list(length=8)
    sandbox_attempts = await db.sandbox_attempts.find(
        {"student_id": student.id}
    ).sort("created_at", -1).limit(20).to_list(length=20)
    total_attempts = await db.sandbox_attempts.count_documents({"student_id": student.id})

    data = {
        "student_id": student.id,
        "public_student_id": student.student_id,
        "generated_at": _utcnow().isoformat(),
        "review_summary": _repo_review_stats(review_jobs),
        "sandbox_summary": _sandbox_stats(sandbox_attempts, total_attempts),
        "latest_reviews": [serialize_job(job) for job in review_jobs],
        "latest_sandbox_attempts": [_serialize_attempt(attempt) for attempt in sandbox_attempts],
        "timeline": _timeline(review_jobs, sandbox_attempts),
    }
    return {"status": "success", "data": data}
