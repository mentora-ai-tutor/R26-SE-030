from app.models.schemas import GitHubCommit, LearnerInput, QuizPerformance, SandboxSession
from app.services.diagnostic_report import (
    DIAGNOSTIC_REPORT_SCHEMA_VERSION,
    build_diagnostic_report,
)
from app.services.mastery_profile_store import build_mastery_profile_document
from app.services.pipeline import run_full_pipeline


def _sandbox(topic, compile_attempts, runtime, syntax, logical, latency, burst):
    return SandboxSession(
        topic=topic,
        compile_attempts=compile_attempts,
        runtime_errors=runtime,
        syntax_errors=syntax,
        logical_errors=logical,
        time_to_success_seconds=120,
        error_correction_latency=latency,
        keystroke_burst_score=burst,
        lines_of_code=40,
    )


def _input_with_github() -> LearnerInput:
    return LearnerInput(
        student_id="STU-2026-0428",
        github_enabled=True,
        quiz_sessions=[
            QuizPerformance(topic="Loops", correct=9, total=10, avg_time_seconds=15),
            QuizPerformance(topic="Recursion", correct=2, total=10, avg_time_seconds=40, retry_count=5),
        ],
        sandbox_sessions=[
            _sandbox("Loops", 5, 0, 1, 0, 20, 0.1),
            _sandbox("Recursion", 6, 4, 1, 4, 1.5, 0.9),  # fast latency + high burst -> paste note
        ],
        github_commits=[
            GitHubCommit(timestamp="2026-03-01T10:00:00", lines_added=250, lines_removed=5,
                         is_big_bang=True, refactor_frequency=0.2, diff_granularity=0.15),
            GitHubCommit(timestamp="2026-03-02T10:00:00", lines_added=25, lines_removed=10,
                         is_big_bang=False, refactor_frequency=0.3, diff_granularity=0.2),
        ],
    )


def _input_without_github() -> LearnerInput:
    return LearnerInput(
        student_id="STU-2026-0932",
        github_enabled=False,
        quiz_sessions=[QuizPerformance(topic="Loops", correct=10, total=10, avg_time_seconds=12)],
        sandbox_sessions=[_sandbox("Loops", 4, 0, 0, 0, 30, 0.1)],
        github_commits=None,
    )


def test_report_assembles_all_sections_with_github() -> None:
    data = _input_with_github()
    final = run_full_pipeline(data)["final_output"]
    report = build_diagnostic_report(data, final)

    assert report["schema_version"] == DIAGNOSTIC_REPORT_SCHEMA_VERSION
    assert report["data_sources"]["github"] == "available"

    gh = report["github_forensics"]
    assert gh["status"] == "AVAILABLE"
    assert gh["commits_sampled"] == 2
    assert gh["is_partial_history"] is True  # honest scope flag
    breakdown = gh["commit_pattern_breakdown"]
    assert round(breakdown["incremental_percent"] + breakdown["big_bang_percent"]
                 + breakdown["erratic_percent"], 1) == 100.0

    sb = report["sandbox_telemetry"]
    assert sb["total_sessions"] == 2
    assert sb["keystroke_burst_detections"] == 1
    rec = next(t for t in sb["topic_performance"] if t["topic"] == "Recursion")
    assert "logical errors" in rec["error_patterns"]
    assert rec["notes"]  # paste-in suspicion surfaced

    quiz = report["adaptive_quiz_results"]
    assert quiz["total_quizzes_taken"] == 2
    loops = next(t for t in quiz["topic_scores"] if t["topic"] == "Loops")
    assert loops["score"] == 90.0

    # synthesized profile reuses the canonical contract verbatim (never diverges)
    assert report["synthesized_mastery_profile"]["knowledge_gaps"] == final["knowledge_gaps"]
    assert report["synthesized_mastery_profile"]["strengths"] == final["strengths"]


def test_report_degrades_without_github() -> None:
    data = _input_without_github()
    final = run_full_pipeline(data)["final_output"]
    report = build_diagnostic_report(data, final)

    assert report["github_forensics"]["status"] == "NO_GITHUB_ACCOUNT_LINKED"
    assert report["sandbox_telemetry"]["status"] == "AVAILABLE"
    assert report["adaptive_quiz_results"]["status"] == "AVAILABLE"


def test_document_embeds_report_without_touching_canonical_fields() -> None:
    data = _input_with_github()
    final = run_full_pipeline(data)["final_output"]
    report = build_diagnostic_report(data, final)

    # with report -> embedded
    doc = build_mastery_profile_document(final, raw_analysis_payload={"source": "test"},
                                         diagnostic_report=report)
    assert doc["diagnostic_report"]["schema_version"] == DIAGNOSTIC_REPORT_SCHEMA_VERSION
    assert doc["raw_analysis_payload"] == {"source": "test"}  # unchanged contract
    assert doc["mastery_profile"]["knowledge_gaps"] == doc["knowledge_gaps"]

    # without report -> key absent (backward compatible)
    doc_legacy = build_mastery_profile_document(final, raw_analysis_payload={"source": "test"})
    assert "diagnostic_report" not in doc_legacy
