import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, status
from starlette.concurrency import run_in_threadpool

from app.db.database import get_database
from app.models.schemas import LearnerInput, QuizPerformance, SandboxSession
from app.services.diagnostic_report import build_diagnostic_report
from app.services.github_review_service import verify_student_from_authorization
from app.services.mastery_profile_store import save_mastery_profile
from app.services.pipeline import run_full_pipeline
from app.services.quiz_engine import generate_quiz

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/analyze")
async def analyze(data: LearnerInput) -> dict:
    result = await run_in_threadpool(run_full_pipeline, data)
    diagnostic_report = build_diagnostic_report(data, result["final_output"])
    try:
        saved_profile = await save_mastery_profile(
            result["final_output"],
            raw_analysis_payload=result.get("pipeline", {}),
            diagnostic_report=diagnostic_report,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Mastery profile could not be saved: {exc}",
        ) from exc

    result["diagnostic_report"] = diagnostic_report
    result["persistence"] = {
        "saved": True,
        "profile_id": saved_profile.get("profile_id"),
        "latest_profile_url": f"/api/v1/mastery-profiles/{data.student_id}/latest",
    }
    return result


@router.post("/analyze/auto")
async def analyze_auto(
    authorization: Optional[str] = Header(default=None),
) -> dict:
    """Auto-analyze using stored data: reads completed quiz_sessions and sandbox_attempts
    from MongoDB for the authenticated student, then runs the full pipeline and saves a
    mastery profile. Triggered automatically after quiz completion."""
    student = await verify_student_from_authorization(authorization)
    db = get_database()

    # ── 1. Quiz performance from completed sessions ──────────────────────────
    quiz_docs = await db.quiz_sessions.find(
        {"student_id": student.id, "status": "completed"}
    ).sort("completed_at", -1).limit(10).to_list(length=10)

    quiz_by_topic: dict = {}
    for doc in quiz_docs:
        for ans in doc.get("answers", []):
            topic = ans.get("topic", "Unknown")
            b = quiz_by_topic.setdefault(topic, {"correct": 0, "total": 0, "time": 0.0})
            b["total"] += 1
            if ans.get("correct"):
                b["correct"] += 1
            b["time"] += float(ans.get("time_seconds", 0) or 0)

    quiz_sessions_input = [
        QuizPerformance(
            topic=t,
            correct=s["correct"],
            total=s["total"],
            avg_time_seconds=round(s["time"] / s["total"], 1) if s["total"] else 0.0,
            retry_count=0,
        )
        for t, s in quiz_by_topic.items()
    ]

    # ── 2. Sandbox performance aggregated from attempts ──────────────────────
    attempt_docs = await db.sandbox_attempts.find(
        {"student_id": student.id}
    ).sort("created_at", -1).limit(50).to_list(length=50)

    sandbox_by_topic: dict = {}
    for att in attempt_docs:
        topic = att.get("topic", "Unknown")
        b = sandbox_by_topic.setdefault(topic, {
            "compile_attempts": 0,
            "runtime_errors": 0,
            "syntax_errors": 0,
            "logical_errors": 0,
            "success_ms": [],
            "fail_ms": [],
            "latest_code": "",
        })
        b["compile_attempts"] += 1
        err = (att.get("error") or "").lower()
        passed = att.get("passed", False)
        success = att.get("success", False)
        ms = float(att.get("runtime_ms") or 0)
        if not success:
            if any(k in err for k in ("compileerror", "syntax", "cannot find symbol", "error:")):
                b["syntax_errors"] += 1
            else:
                b["runtime_errors"] += 1
            b["fail_ms"].append(ms)
        elif not passed:
            b["logical_errors"] += 1
            b["fail_ms"].append(ms)
        else:
            b["success_ms"].append(ms)
        if att.get("code"):
            b["latest_code"] = att["code"]

    sandbox_sessions_input = []
    for topic, b in sandbox_by_topic.items():
        time_to_success = (
            sum(b["success_ms"]) / 1000.0 if b["success_ms"]
            else sum(b["fail_ms"]) / 1000.0 if b["fail_ms"]
            else 60.0
        )
        ecl = (
            sum(b["fail_ms"]) / len(b["fail_ms"]) / 1000.0 if b["fail_ms"] else 10.0
        )
        lines = max(len(b["latest_code"].split("\n")) if b["latest_code"] else 30, 10)
        sandbox_sessions_input.append(
            SandboxSession(
                topic=topic,
                compile_attempts=b["compile_attempts"],
                runtime_errors=b["runtime_errors"],
                syntax_errors=b["syntax_errors"],
                logical_errors=b["logical_errors"],
                time_to_success_seconds=round(time_to_success, 1),
                error_correction_latency=round(ecl, 1),
                keystroke_burst_score=0.5,
                lines_of_code=lines,
            )
        )

    if not quiz_sessions_input and not sandbox_sessions_input:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No completed quizzes or sandbox attempts found yet. Finish at least one quiz or run some sandbox code first.",
        )

    # ── 3. Run pipeline and persist ──────────────────────────────────────────
    data = LearnerInput(
        student_id=student.student_id,
        github_enabled=False,
        quiz_sessions=quiz_sessions_input,
        sandbox_sessions=sandbox_sessions_input,
    )
    result = await run_in_threadpool(run_full_pipeline, data)
    diagnostic_report = build_diagnostic_report(data, result["final_output"])
    try:
        saved_profile = await save_mastery_profile(
            result["final_output"],
            raw_analysis_payload=result.get("pipeline", {}),
            diagnostic_report=diagnostic_report,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Mastery profile could not be saved: {exc}",
        ) from exc

    result["diagnostic_report"] = diagnostic_report
    result["persistence"] = {
        "saved": True,
        "profile_id": saved_profile.get("profile_id"),
        "latest_profile_url": f"/api/v1/mastery-profiles/{student.student_id}/latest",
        "quiz_topics": [q.topic for q in quiz_sessions_input],
        "sandbox_topics": [s.topic for s in sandbox_sessions_input],
    }
    logger.info(
        "Auto-analyze complete for %s: mastery=%s profile=%s",
        student.student_id,
        result["final_output"].get("overall_mastery_score"),
        saved_profile.get("profile_id"),
    )
    return result


@router.post("/quiz/generate")
def quiz_generate(topic: str, mastery_score: float = 0.5) -> dict:
    return generate_quiz(topic=topic, mastery_score=mastery_score)


@router.get("/health")
def health() -> dict:
    return {"status": "online", "agent": "KAA v1.0", "steps": 10}


@router.get("/demo")
def demo() -> dict:
    return {
        "sample_payload": {
            "student_id": "IT22201232",
            "github_enabled": True,
            "quiz_sessions": [
                {"topic": "Loops", "correct": 3, "total": 10, "avg_time_seconds": 18, "retry_count": 4},
                {"topic": "Recursion", "correct": 2, "total": 10, "avg_time_seconds": 35, "retry_count": 6},
                {"topic": "OOP", "correct": 7, "total": 10, "avg_time_seconds": 20, "retry_count": 1},
                {"topic": "Arrays", "correct": 8, "total": 10, "avg_time_seconds": 12, "retry_count": 0},
                {"topic": "Algorithms", "correct": 4, "total": 10, "avg_time_seconds": 45, "retry_count": 5},
            ],
            "sandbox_sessions": [
                {
                    "topic": "Loops",
                    "compile_attempts": 12,
                    "runtime_errors": 5,
                    "syntax_errors": 8,
                    "logical_errors": 4,
                    "time_to_success_seconds": 320,
                    "error_correction_latency": 2.1,
                    "keystroke_burst_score": 0.82,
                    "lines_of_code": 45,
                },
                {
                    "topic": "Recursion",
                    "compile_attempts": 18,
                    "runtime_errors": 9,
                    "syntax_errors": 3,
                    "logical_errors": 8,
                    "time_to_success_seconds": 540,
                    "error_correction_latency": 1.8,
                    "keystroke_burst_score": 0.9,
                    "lines_of_code": 35,
                },
                {
                    "topic": "OOP",
                    "compile_attempts": 5,
                    "runtime_errors": 1,
                    "syntax_errors": 2,
                    "logical_errors": 1,
                    "time_to_success_seconds": 180,
                    "error_correction_latency": 14.0,
                    "keystroke_burst_score": 0.25,
                    "lines_of_code": 90,
                },
                {
                    "topic": "Arrays",
                    "compile_attempts": 4,
                    "runtime_errors": 0,
                    "syntax_errors": 1,
                    "logical_errors": 0,
                    "time_to_success_seconds": 120,
                    "error_correction_latency": 20.0,
                    "keystroke_burst_score": 0.15,
                    "lines_of_code": 60,
                },
                {
                    "topic": "Algorithms",
                    "compile_attempts": 14,
                    "runtime_errors": 6,
                    "syntax_errors": 5,
                    "logical_errors": 7,
                    "time_to_success_seconds": 680,
                    "error_correction_latency": 2.5,
                    "keystroke_burst_score": 0.78,
                    "lines_of_code": 80,
                },
            ],
            "github_commits": [
                {
                    "timestamp": "2026-03-01T10:00:00",
                    "lines_added": 250,
                    "lines_removed": 5,
                    "is_big_bang": True,
                    "refactor_frequency": 0.2,
                    "diff_granularity": 0.15,
                },
                {
                    "timestamp": "2026-03-05T14:30:00",
                    "lines_added": 20,
                    "lines_removed": 8,
                    "is_big_bang": False,
                    "refactor_frequency": 0.8,
                    "diff_granularity": 0.75,
                },
                {
                    "timestamp": "2026-03-10T09:15:00",
                    "lines_added": 180,
                    "lines_removed": 2,
                    "is_big_bang": True,
                    "refactor_frequency": 0.3,
                    "diff_granularity": 0.2,
                },
                {
                    "timestamp": "2026-03-15T16:00:00",
                    "lines_added": 30,
                    "lines_removed": 15,
                    "is_big_bang": False,
                    "refactor_frequency": 0.9,
                    "diff_granularity": 0.85,
                },
            ],
        }
    }
