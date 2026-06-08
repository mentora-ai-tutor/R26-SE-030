from fastapi import APIRouter, HTTPException, status
from starlette.concurrency import run_in_threadpool

from app.models.schemas import LearnerInput
from app.services.pipeline import run_full_pipeline
from app.services.diagnostic_report import build_diagnostic_report
from app.services.mastery_profile_store import save_mastery_profile
from app.services.quiz_engine import generate_quiz

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
