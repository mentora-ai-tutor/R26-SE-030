"""Integration tests: FastAPI TestClient against the real app with the DB, auth
verify step and every LLM call overridden by in-memory fakes. No real MongoDB,
user-service or Gemini/Ollama is touched.

Auth: the app expects ``Authorization: Bearer <token>`` (verified against the user
service in production). Here ``verify_student_from_authorization`` is patched with a
fixed StudentContext, so ``AUTH_HEADER`` satisfies the real header-parsing contract.
"""
from __future__ import annotations

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

import app.services.sandbox_challenge_generator as scg_mod
import app.services.llm as llm_mod
from app.main import app
from app.services.llm.base import LLMError
from fakes import (
    AUTH_HEADER,
    FakeDatabase,
    FakeLLMRouter,
    PUBLIC_STUDENT_ID,
    STUDENT_OBJECT_ID,
    patch_auth,
    patch_database,
    utcnow,
)


# --------------------------------------------------------------------------- data
def _review_job_doc() -> dict:
    return {
        "_id": ObjectId(),
        "student_id": STUDENT_OBJECT_ID,
        "public_student_id": PUBLIC_STUDENT_ID,
        "seed_version": "review-v1",
        "status": "done",
        "llm_choice": "gemini",
        "repos": [
            {
                "full_name": "student/learning-java",
                "status": "done",
                "review": {
                    "repo": "student/learning-java",
                    "summary": "Solid OOP foundations.",
                    "java_signals": {"level": "Intermediate", "evidence": ["encapsulation"]},
                    "errors": [
                        {
                            "severity": "high",
                            "file": "Main.java",
                            "line": 3,
                            "why": "possible null pointer",
                            "fix_hint": "guard the input",
                        }
                    ],
                    "suggestions": ["extract a helper"],
                },
                "error": None,
                "llm_choice": "gemini",
            }
        ],
        "java_level_inferred": "Intermediate",
        "signals_evidence": ["encapsulation"],
        "created_at": utcnow(),
        "updated_at": utcnow(),
    }


def _sandbox_attempt_doc(
    topic: str, title: str, passed: bool, error: str | None = None
) -> dict:
    return {
        "_id": ObjectId(),
        "student_id": STUDENT_OBJECT_ID,
        "public_student_id": PUBLIC_STUDENT_ID,
        "challenge_id": f"ch-{topic.lower()}",
        "title": title,
        "topic": topic,
        "difficulty": "easy",
        "code": "public class Main { }",
        "stdin": None,
        "expected_output": "30",
        "output": "30" if passed else None,
        "error": error,
        "success": passed,
        "passed": passed,
        "attempt_number": 1,
        "runtime_ms": 120,
        "created_at": utcnow(),
        "updated_at": utcnow(),
    }


def _quiz_result_doc() -> dict:
    return {
        "_id": ObjectId(),
        "student_id": STUDENT_OBJECT_ID,
        "public_student_id": PUBLIC_STUDENT_ID,
        "session_id": "q-1",
        "mode": "sandbox",
        "schema_version": "kaa-quiz-v1.0",
        "score_percent": 70.0,
        "correct": 7,
        "total": 10,
        "difficulty_reached": "medium",
        "topic_performance": [
            {
                "topic": "Loops",
                "correct": 7,
                "total": 10,
                "avg_time_seconds": 18.0,
                "retry_count": 2,
            }
        ],
        "completed_at": utcnow(),
        "created_at": utcnow(),
    }


def _mastery_doc() -> dict:
    now = utcnow()
    gap = {
        "topic": "Recursion",
        "topic_id": "CS101-REC",
        "gap_type": "PARTIAL_GAP",
        "confidence": 0.8,
        "mastery_score": 55.0,
        "weak_subskills": [],
        "known_subskills": [],
        "misconceptions": [],
        "observed_error_patterns": {},
        "evidence_summary": "Recursion mastery is 55/100.",
        "prerequisite_topics": [],
        "related_topics": [],
        "suggested_intervention": {
            "primary": "step_by_step_practice",
            "secondary": [],
            "difficulty_level": "intermediate",
            "estimated_time_minutes": 60,
            "learning_objectives": [],
        },
    }
    gaps = [gap]
    strengths = [
        {
            "topic": "Loops",
            "topic_id": "CS101-LOOP",
            "confidence": 0.9,
            "mastery_score": 92.0,
            "mastery_level": "advanced",
            "evidence_summary": "Loops is a strength.",
            "known_subskills": [],
            "can_teach_others": True,
        },
        {
            "topic": "Arrays",
            "topic_id": "CS101-ARR",
            "confidence": 0.85,
            "mastery_score": 88.0,
            "mastery_level": "advanced",
            "evidence_summary": "Arrays is a strength.",
            "known_subskills": [],
            "can_teach_others": True,
        },
        {
            "topic": "OOP",
            "topic_id": "CS201-OOP",
            "confidence": 0.8,
            "mastery_score": 82.0,
            "mastery_level": "advanced",
            "evidence_summary": "OOP is a strength.",
            "known_subskills": [],
            "can_teach_others": True,
        },
    ]
    return {
        "_id": ObjectId(),
        "schema_version": "kaa-lmg-v1.0",
        "student_id": PUBLIC_STUDENT_ID,
        "session_id": "sess-mastery-1",
        "analysis_timestamp": "2026-05-01T10:00:00Z",
        "data_sources": {
            "github": "available",
            "sandbox": "available",
            "quizzes": "available",
        },
        "mastery_profile": {
            "overall_mastery_score": 79.0,
            "knowledge_gaps": gaps,
            "strengths": strengths,
        },
        "recommendations": {
            "priority_order": ["Recursion"],
            "general_advice": "Work the Recursion gap first.",
            "for_instructor": "Verify with a live task.",
        },
        "overall_mastery_score": 79.0,
        "knowledge_gaps": gaps,
        "strengths": strengths,
        "gap_topic_ids": ["CS101-REC"],
        "created_at": now,
        "updated_at": now,
    }


def _career_quiz_result_doc() -> dict:
    now = utcnow()
    return {
        "_id": ObjectId(),
        "student_id": STUDENT_OBJECT_ID,
        "public_student_id": PUBLIC_STUDENT_ID,
        "session_id": "q-career-1",
        "mode": "sandbox",
        "schema_version": "kaa-quiz-v1.0",
        "score_percent": 84.0,
        "correct": 25,
        "total": 30,
        "difficulty_reached": "medium",
        "topic_performance": [
            {"topic": "Arrays", "correct": 8, "total": 10, "avg_time_seconds": 16.0, "retry_count": 1},
            {"topic": "OOP", "correct": 9, "total": 10, "avg_time_seconds": 20.0, "retry_count": 0},
            {"topic": "Data Structures", "correct": 8, "total": 10, "avg_time_seconds": 22.0, "retry_count": 2},
        ],
        "completed_at": now,
        "created_at": now,
    }


# --------------------------------------------------------------------- fixtures
@pytest.fixture
def env(monkeypatch):
    fdb = FakeDatabase()
    patch_database(monkeypatch, fdb)
    patch_auth(monkeypatch)
    client = TestClient(app)
    yield client, fdb


# ----------------------------------------------------------------------- tests
def test_knowledge_profile_me_endpoint(env) -> None:
    client, fdb = env
    fdb.repo_review_jobs.docs.append(_review_job_doc())
    fdb.sandbox_attempts.docs.append(
        _sandbox_attempt_doc("Loops", "Sum even numbers", passed=True)
    )
    fdb.sandbox_attempts.docs.append(
        _sandbox_attempt_doc("Recursion", "Fibonacci", passed=False, error="ArrayIndexOutOfBoundsException")
    )
    fdb.quiz_results.docs.append(_quiz_result_doc())

    resp = client.get("/api/v1/knowledge-profile/me", headers=AUTH_HEADER)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"

    data = body["data"]
    assert data["student_id"] == STUDENT_OBJECT_ID
    assert data["public_student_id"] == PUBLIC_STUDENT_ID
    assert data["review_summary"]["total_repos"] == 1
    assert data["review_summary"]["findings"] == 1
    assert data["review_summary"]["high_risk"] == 1
    assert data["review_summary"]["latest_java_level"] == "Intermediate"
    assert data["sandbox_summary"]["total_attempts"] == 2
    assert data["sandbox_summary"]["recent_passed"] == 1
    assert data["quiz_summary"]["total_quizzes"] == 1
    assert data["quiz_summary"]["best_score"] == 70.0
    assert len(data["timeline"]) == 4  # 1 quiz + 1 review + 2 sandbox events
    event_types = {event["type"] for event in data["timeline"]}
    assert event_types == {"quiz", "github_review", "sandbox_attempt"}


def test_mastery_profile_latest_fetch(env) -> None:
    client, fdb = env
    fdb.mastery_profiles.docs.append(_mastery_doc())

    resp = client.get(f"/api/v1/mastery-profiles/{PUBLIC_STUDENT_ID}/latest")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["student_id"] == PUBLIC_STUDENT_ID
    assert data["overall_mastery_score"] == 79.0
    assert data["gap_topic_ids"] == ["CS101-REC"]
    assert data["mastery_profile"]["knowledge_gaps"][0]["topic"] == "Recursion"
    assert len(data["mastery_profile"]["strengths"]) == 3


def test_mastery_profile_latest_not_found(env) -> None:
    client, _ = env
    resp = client.get(f"/api/v1/mastery-profiles/{PUBLIC_STUDENT_ID}/latest")
    assert resp.status_code == 404


def test_career_predict_endpoint_with_llm_override(env, monkeypatch) -> None:
    client, fdb = env
    fdb.mastery_profiles.docs.append(_mastery_doc())
    fdb.quiz_results.docs.append(_career_quiz_result_doc())

    router = FakeLLMRouter(error=LLMError("engine down"))  # LLM call is overridden
    monkeypatch.setattr(llm_mod, "get_router", lambda: router)

    resp = client.post(
        "/api/v1/career/predict",
        json={"student_id": PUBLIC_STUDENT_ID, "target_role": "backend developer"},
    )
    assert resp.status_code == 200
    assert router.calls and router.calls[0]["task"] in ("career_narrative", "CareerNarrative")

    data = resp.json()["data"]
    assert data["evidence_sufficient"] is True
    assert data["best_fit_role"] in {
        "Junior Java / Backend Developer",
        "General Software Engineer",
        "DSA / Algorithms-focused Engineer",
        "Systems / Concurrency Engineer",
        "QA / Test Automation Engineer",
    }
    assert len(data["ranked_roles"]) == 3
    assert data["aspiration_alignment"]["stated_role"] == "Junior Java / Backend Developer"
    assert data["narrative"]["headline"].startswith("Your profile best fits")  # template fallback
    assert fdb.career_predictions.docs  # prediction was persisted to the fake DB


def test_sandbox_challenges_generated_path(env, monkeypatch) -> None:
    client, _ = env
    batch = {
        "challenges": [
            {
                "title": "Sum evens",
                "topic": "Loops",
                "difficulty": "easy",
                "prompt": "Print the sum of even numbers 1..10.",
                "starter_code": "public class Main { // TODO }",
                "reference_solution": "public class Main { public static void main(String[] a){ System.out.println(30); } }",
                "stdin": None,
            },
            {
                "title": "Reverse array",
                "topic": "Arrays",
                "difficulty": "medium",
                "prompt": "Print the array reversed.",
                "starter_code": "public class Main { // TODO }",
                "reference_solution": "public class Main { public static void main(String[] a){ System.out.println(\"4 3 2 1\"); } }",
                "stdin": None,
            },
        ]
    }
    router = FakeLLMRouter(result=batch)

    async def _fake_run_java(code, stdin):
        return {"success": True, "output": "42\n"}

    monkeypatch.setattr(scg_mod, "get_router", lambda: router)
    monkeypatch.setattr(scg_mod, "_run_java", _fake_run_java)

    resp = client.get(
        "/api/v1/sandbox/challenges",
        params={"count": 2, "topics": "Loops,Arrays", "llm": "gemini"},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["source"] == "generated"
    assert data["degraded"] is False
    assert len(data["challenges"]) == 2
    assert data["challenges"][0]["difficulty"] == "easy"  # ramps easy -> hard
    assert data["challenges"][0]["expected_output"] == "42"  # authoritative stdout
    assert all("reference_solution" not in c for c in data["challenges"])  # withheld


def test_sandbox_challenges_seed_fallback(env, monkeypatch) -> None:
    client, _ = env
    router = FakeLLMRouter(error=LLMError("no live tiers"))
    monkeypatch.setattr(scg_mod, "get_router", lambda: router)

    resp = client.get(
        "/api/v1/sandbox/challenges",
        params={"count": 3, "llm": "ollama"},
        headers=AUTH_HEADER,
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["source"] == "seed"
    assert data["degraded"] is True
    assert len(data["challenges"]) == 3
    assert all(c["source"] == "seed" for c in data["challenges"])
    assert all(c["expected_output"] for c in data["challenges"])


def test_endpoints_require_bearer_token() -> None:
    # No fixtures here: the REAL verify_student_from_authorization must reject a
    # missing Authorization header (before any token/user-service call happens).
    client = TestClient(app)
    resp = client.get("/api/v1/knowledge-profile/me")
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Authorization header is required"