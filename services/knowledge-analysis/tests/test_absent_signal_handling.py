"""Regression: absent sources must not fabricate neutral 50s.

A student who only completes a quiz has *no* sandbox (or forensic) signal. Those
missing sources must stay None — "no evidence" — instead of being defaulted to 0.5,
which previously dragged a 2/2 topic down to a false PARTIAL_GAP.
"""
from __future__ import annotations

from app.models.schemas import GitHubCommit, LearnerInput, QuizPerformance
from app.services.pipeline import run_full_pipeline


def _quiz_only_input() -> LearnerInput:
    return LearnerInput(
        student_id="STU-NO-SANDBOX-01",
        github_enabled=False,
        quiz_sessions=[
            QuizPerformance(topic="Loops", correct=2, total=2, avg_time_seconds=12),
            QuizPerformance(
                topic="Exception Handling", correct=0, total=1, avg_time_seconds=20
            ),
        ],
        sandbox_sessions=[],
        github_commits=None,
    )


def test_quiz_only_aced_topic_is_not_a_gap() -> None:
    output = run_full_pipeline(_quiz_only_input())["final_output"]

    gaps_by_id = {gap["topic_id"]: gap for gap in output["knowledge_gaps"]}
    strengths = {strength["topic"]: strength for strength in output["strengths"]}

    # Loops was 2/2 -> strength, no false PARTIAL_GAP from a phantom sandbox 50.
    assert "CS101-LOOP" not in gaps_by_id
    assert "Loops" in strengths
    assert strengths["Loops"]["mastery_score"] >= 90

    # Exception Handling was 0/1 -> still a real gap (quiz evidence alone suffices).
    assert "CS102-EXC" in gaps_by_id
    assert gaps_by_id["CS102-EXC"]["gap_type"] == "FUNDAMENTAL_GAP"


def test_quiz_only_scores_keep_absent_signals_none() -> None:
    output = run_full_pipeline(_quiz_only_input())["final_output"]
    topic_scores = output["raw_analysis_payload"]["topic_scores"]

    loops = topic_scores["Loops"]
    assert loops["quiz_score"] == 1.0
    assert loops["sandbox_score"] is None  # no fake 0.5 floor
    assert loops["forensic_score"] is None
    assert loops["mastery_score"] == 1.0


def test_sandbox_only_still_scores_from_available_evidence() -> None:
    from app.models.schemas import SandboxSession

    data = LearnerInput(
        student_id="STU-NO-QUIZ-01",
        github_enabled=False,
        quiz_sessions=[],
        sandbox_sessions=[
            # routes.py aggregates per-topic before piping into the pipeline.
            SandboxSession(
                topic="Arrays",
                compile_attempts=6,
                runtime_errors=0,
                syntax_errors=0,
                logical_errors=2,
                time_to_success_seconds=195,
                error_correction_latency=50,
                keystroke_burst_score=0.5,
                lines_of_code=30,
            ),
        ],
        github_commits=None,
    )
    output = run_full_pipeline(data)["final_output"]
    gaps = {gap["topic_id"]: gap for gap in output["knowledge_gaps"]}

    # 6 attempts, 2 logical errors -> 1 - (0+2)/6 = 0.667.
    # Quiz evidence absent, so the topic is judged on sandbox alone.
    ts = output["raw_analysis_payload"]["topic_scores"]
    assert ts["Arrays"]["quiz_score"] is None
    assert ts["Arrays"]["sandbox_score"] == round(1 - (0 + 2) / 6, 3)

    # 0.667 < 0.75 sandbox -> weak subskills -> PARTIAL_GAP (not a fabricated grade).
    assert "CS101-ARR" in gaps
    assert gaps["CS101-ARR"]["gap_type"] == "PARTIAL_GAP"


def test_full_mode_with_github_still_uses_all_signals() -> None:
    data = LearnerInput(
        student_id="STU-FULL-01",
        github_enabled=True,
        quiz_sessions=[
            QuizPerformance(topic="Loops", correct=9, total=10, avg_time_seconds=15),
        ],
        sandbox_sessions=[],
        github_commits=[
            GitHubCommit(
                timestamp="2026-03-01T10:00:00",
                lines_added=250,
                lines_removed=5,
                is_big_bang=True,
                refactor_frequency=0.2,
                diff_granularity=0.15,
            ),
            GitHubCommit(
                timestamp="2026-03-02T10:00:00",
                lines_added=25,
                lines_removed=10,
                is_big_bang=False,
                refactor_frequency=0.3,
                diff_granularity=0.2,
            ),
        ],
    )
    output = run_full_pipeline(data)["final_output"]
    ts = output["raw_analysis_payload"]["topic_scores"]

    # Full mode keeps all three signals when present: quiz + forensic, no sandbox.
    assert output["data_sources"]["github"] == "available"
    assert ts["Loops"]["quiz_score"] == 0.9
    assert ts["Loops"]["sandbox_score"] is None
    assert ts["Loops"]["forensic_score"] == 0.0
    assert 0 < ts["Loops"]["mastery_score"] < 1.0