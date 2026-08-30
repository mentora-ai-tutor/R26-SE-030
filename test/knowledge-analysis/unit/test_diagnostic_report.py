"""Pure diagnostic-report reshaping (10-step pipeline is LLM/DB-free)."""
from __future__ import annotations

from app.models.schemas import (
    GitHubCommit,
    LearnerInput,
    QuizPerformance,
    SandboxSession,
)
from app.services.diagnostic_report import (
    DIAGNOSTIC_REPORT_SCHEMA_VERSION,
    _classify_pattern,
    build_diagnostic_report,
)
from app.services.pipeline import run_full_pipeline


def _input(github_enabled: bool = True) -> LearnerInput:
    return LearnerInput(
        student_id="STU-2026-0411",
        github_enabled=github_enabled,
        quiz_sessions=[
            QuizPerformance(topic="Loops", correct=9, total=10, avg_time_seconds=14, retry_count=0),
            QuizPerformance(topic="Recursion", correct=2, total=10, avg_time_seconds=42, retry_count=6),
            QuizPerformance(topic="OOP", correct=8, total=10, avg_time_seconds=20, retry_count=1),
        ],
        sandbox_sessions=[
            SandboxSession(
                topic="Loops",
                compile_attempts=6,
                runtime_errors=0,
                syntax_errors=1,
                logical_errors=0,
                time_to_success_seconds=180,
                error_correction_latency=12.0,
                keystroke_burst_score=0.2,
                lines_of_code=40,
            ),
            SandboxSession(
                topic="Recursion",
                compile_attempts=5,
                runtime_errors=3,
                syntax_errors=0,
                logical_errors=2,
                time_to_success_seconds=700,
                error_correction_latency=1.2,
                keystroke_burst_score=0.95,
                lines_of_code=35,
            ),
        ],
        github_commits=(
            [
                GitHubCommit(
                    timestamp="2026-03-01T10:00:00",
                    lines_added=240,
                    lines_removed=2,
                    is_big_bang=True,
                    refactor_frequency=0.1,
                    diff_granularity=0.1,
                ),
                GitHubCommit(
                    timestamp="2026-03-03T10:00:00",
                    lines_added=40,
                    lines_removed=12,
                    is_big_bang=False,
                    refactor_frequency=0.7,
                    diff_granularity=0.8,
                ),
                GitHubCommit(
                    timestamp="2026-03-07T10:00:00",
                    lines_added=14,
                    lines_removed=3,
                    is_big_bang=True,
                    refactor_frequency=0.3,
                    diff_granularity=0.2,
                ),
            ]
            if github_enabled
            else None
        ),
    )


def test_diagnostic_report_assembles_all_sections() -> None:
    data = _input(github_enabled=True)
    final = run_full_pipeline(data)["final_output"]
    report = build_diagnostic_report(data, final)

    assert report["schema_version"] == DIAGNOSTIC_REPORT_SCHEMA_VERSION
    assert report["data_sources"]["github"] == "available"

    gh = report["github_forensics"]
    assert gh["status"] == "AVAILABLE"
    assert gh["commits_sampled"] == 3
    assert gh["is_partial_history"] is True
    assert gh["commit_pattern_classification"] == "BIG_BANG"  # 2/3 big-bang >= 50%
    breakdown = gh["commit_pattern_breakdown"]
    assert round(breakdown["incremental_percent"], 1) == 33.3

    sb = report["sandbox_telemetry"]
    assert sb["status"] == "AVAILABLE"
    assert sb["total_sessions"] == 2
    assert sb["keystroke_burst_detections"] == 1
    recursion = next(t for t in sb["topic_performance"] if t["topic"] == "Recursion")
    assert "logical errors" in recursion["error_patterns"]
    assert recursion["notes"]  # paste-in / low-authorship signal surfaced

    quiz = report["adaptive_quiz_results"]
    assert quiz["total_quizzes_taken"] == 3
    loops = next(t for t in quiz["topic_scores"] if t["topic"] == "Loops")
    assert loops["score"] == 90.0

    synthesized = report["synthesized_mastery_profile"]
    assert synthesized["knowledge_gaps"] == final["knowledge_gaps"]
    assert synthesized["strengths"] == final["strengths"]


def test_diagnostic_report_degrades_and_pattern_classifier() -> None:
    data = _input(github_enabled=False)
    final = run_full_pipeline(data)["final_output"]
    report = build_diagnostic_report(data, final)

    assert report["github_forensics"]["status"] == "NO_GITHUB_ACCOUNT_LINKED"
    assert report["data_sources"]["github"] == "unavailable"
    assert report["sandbox_telemetry"]["status"] == "AVAILABLE"
    assert report["adaptive_quiz_results"]["status"] == "AVAILABLE"

    assert _classify_pattern(5, 1, 8) == "BIG_BANG"
    assert _classify_pattern(0, 3, 4) == "INCREMENTAL"
    assert _classify_pattern(2, 2, 6) == "MIXED"