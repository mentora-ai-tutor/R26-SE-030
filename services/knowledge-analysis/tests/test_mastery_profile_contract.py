from fastapi.testclient import TestClient

from app.main import app
from app.models.schemas import GitHubCommit, LearnerInput, QuizPerformance, SandboxSession
from app.services.mastery_profile_store import build_mastery_profile_document
from app.services.pipeline import run_full_pipeline


def _input_with_github() -> LearnerInput:
    return LearnerInput(
        student_id="STU-2026-0428",
        github_enabled=True,
        quiz_sessions=[
            QuizPerformance(topic="Loops", correct=9, total=10, avg_time_seconds=15),
            QuizPerformance(topic="Recursion", correct=2, total=10, avg_time_seconds=40, retry_count=5),
        ],
        sandbox_sessions=[
            SandboxSession(
                topic="Loops",
                compile_attempts=5,
                runtime_errors=0,
                syntax_errors=1,
                logical_errors=0,
                time_to_success_seconds=120,
                error_correction_latency=20,
                keystroke_burst_score=0.1,
                lines_of_code=40,
            ),
            SandboxSession(
                topic="Recursion",
                compile_attempts=6,
                runtime_errors=4,
                syntax_errors=1,
                logical_errors=4,
                time_to_success_seconds=45,
                error_correction_latency=2,
                keystroke_burst_score=0.9,
                lines_of_code=35,
            ),
        ],
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


def _input_without_github() -> LearnerInput:
    return LearnerInput(
        student_id="STU-2026-0932",
        github_enabled=False,
        quiz_sessions=[
            QuizPerformance(topic="Loops", correct=10, total=10, avg_time_seconds=12),
            QuizPerformance(topic="Recursion", correct=7, total=10, avg_time_seconds=30, retry_count=1),
        ],
        sandbox_sessions=[
            SandboxSession(
                topic="Loops",
                compile_attempts=4,
                runtime_errors=0,
                syntax_errors=0,
                logical_errors=0,
                time_to_success_seconds=90,
                error_correction_latency=30,
                keystroke_burst_score=0.1,
                lines_of_code=35,
            ),
            SandboxSession(
                topic="Recursion",
                compile_attempts=8,
                runtime_errors=1,
                syntax_errors=0,
                logical_errors=1,
                time_to_success_seconds=260,
                error_correction_latency=35,
                keystroke_burst_score=0.2,
                lines_of_code=40,
            ),
        ],
        github_commits=None,
    )


def test_full_mode_output_contains_lmg_ready_gap_contract() -> None:
    output = run_full_pipeline(_input_with_github())["final_output"]

    assert output["schema_version"] == "kaa-lmg-v1.0"
    assert output["session_id"]
    assert output["analysis_timestamp"].endswith("Z")
    assert output["data_sources"]["github"] == "available"
    assert output["mastery_profile"]["knowledge_gaps"] == output["knowledge_gaps"]
    assert output["gap_topic_ids"] == [gap["topic_id"] for gap in output["knowledge_gaps"]]

    gap = next(g for g in output["knowledge_gaps"] if g["topic"] == "Recursion")
    assert gap["topic_id"] == "CS101-REC"
    assert gap["gap_type"] == "FUNDAMENTAL_GAP"
    assert 0 <= gap["confidence"] <= 1
    assert 0 <= gap["mastery_score"] <= 100
    assert gap["weak_subskills"]
    assert gap["suggested_intervention"]["learning_objectives"]
    assert isinstance(gap["observed_error_patterns"]["github"], list)


def test_reduced_mode_uses_empty_github_evidence_lists() -> None:
    output = run_full_pipeline(_input_without_github())["final_output"]

    assert output["data_sources"]["github"] == "unavailable"
    gap = next(g for g in output["knowledge_gaps"] if g["topic"] == "Recursion")
    assert gap["gap_type"] == "PARTIAL_GAP"
    assert gap["observed_error_patterns"]["github"] == []
    assert gap["weak_subskills"]


def test_db_document_keeps_top_level_and_nested_fields_synchronised() -> None:
    output = run_full_pipeline(_input_with_github())["final_output"]
    doc = build_mastery_profile_document(output, raw_analysis_payload={"source": "test"})

    assert doc["mastery_profile"]["knowledge_gaps"] == doc["knowledge_gaps"]
    assert doc["mastery_profile"]["strengths"] == doc["strengths"]
    assert doc["mastery_profile"]["overall_mastery_score"] == doc["overall_mastery_score"]
    assert doc["gap_topic_ids"] == [gap["topic_id"] for gap in doc["knowledge_gaps"]]
    assert doc["raw_analysis_payload"] == {"source": "test"}


def test_latest_profile_endpoint_returns_canonical_shape(monkeypatch) -> None:
    async def fake_latest(student_id: str) -> dict:
        return {
            "schema_version": "kaa-lmg-v1.0",
            "student_id": student_id,
            "analysis_timestamp": "2026-03-18T14:30:00Z",
            "data_sources": {"github": "unavailable", "sandbox": "available", "quizzes": "available"},
            "mastery_profile": {
                "overall_mastery_score": 70,
                "knowledge_gaps": [],
                "strengths": [],
            },
            "recommendations": {},
            "overall_mastery_score": 70,
            "knowledge_gaps": [],
            "strengths": [],
            "gap_topic_ids": [],
        }

    monkeypatch.setattr(
        "app.api.mastery_profile_routes.get_latest_mastery_profile",
        fake_latest,
    )

    response = TestClient(app).get("/api/v1/mastery-profiles/STU-2026-0932/latest")

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["schema_version"] == "kaa-lmg-v1.0"
    assert "mastery_profile" in payload
