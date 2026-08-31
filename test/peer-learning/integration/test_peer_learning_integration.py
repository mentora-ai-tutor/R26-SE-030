"""Integration tests: FastAPI TestClient against the real routed app with the
MongoDB session/collection layer overridden to an in-memory fake and all LLM
calls forced onto deterministic fallback paths (see conftest.py).

The existing service routers are registered on `app.main.fastapi_app`, so these
tests exercise the actual HTTP endpoints end-to-end with no network and no real
database.
"""

import datetime

import jwt


def _mastery_payload():
    return {
        "student_id": "STU_TEST_001",
        "analysis_timestamp": "2026-01-01T00:00:00",
        "mastery_profile": {
            "overall_mastery_score": 55,
            "knowledge_gaps": [
                {
                    "topic": "Exceptions",
                    "topic_id": "TOPIC_JAVA_EXC",
                    "gap_type": "weak",
                    "confidence": 0.5,
                    "mastery_score": 40,
                    "weak_subskills": [
                        {
                            "subskill": "try-catch",
                            "subskill_id": "SUB_EXC_01",
                            "status": "weak",
                            "evidence": "erroneous code",
                            "recommended_content_focus": "exception handling",
                        }
                    ],
                    "misconceptions": ["finally always crashes"],
                    "suggested_intervention": {
                        "primary": "remediate exceptions",
                        "secondary": [],
                        "difficulty_level": "beginner",
                        "estimated_time_minutes": 15,
                        "learning_objectives": ["handle checked exceptions"],
                    },
                }
            ],
            "strengths": [],
        },
        "recommendations": {
            "priority_order": ["Exceptions"],
            "general_advice": "Keep practicing",
            "for_instructor": "Provide more examples",
        },
    }


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

def test_health_check(client):
    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "online"
    assert "system_status" in body
    assert body["platform"]


# ---------------------------------------------------------------------------
# Student mastery import + retrieval
# ---------------------------------------------------------------------------

def test_import_and_get_student_analysis(client, auth_student):
    auth_student("STU_TEST_001")
    payload = _mastery_payload()
    resp = client.post("/api/student/import-analysis", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["imported_document"]["student_id"] == "STU_TEST_001"
    assert body["imported_document"]["overall_mastery_score"] == 55

    got = client.get("/api/student/analysis/STU_TEST_001")
    assert got.status_code == 200
    assert got.json()["analysis"]["student_id"] == "STU_TEST_001"


def test_import_analysis_forbidden_student_mismatch(client, auth_student):
    auth_student("STU_TEST_001")
    payload = _mastery_payload()
    payload["student_id"] = "STU_OTHER"
    resp = client.post("/api/student/import-analysis", json=payload)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# RAG content recommendation (fallback, no auth, no LLM)
# ---------------------------------------------------------------------------

def test_rag_content_recommendation_fallback(client):
    resp = client.post(
        "/api/rag-content/recommend",
        json={
            "student_id": "STU_TEST_001",
            "topic": "Exceptions",
            "weak_subskill": "try-catch",
            "misconception": "finally runs always",
            "difficulty_level": "beginner",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["topic"] == "Exceptions"
    assert body["weak_subskill"] == "try-catch"
    assert len(body["key_highlights"]) >= 4
    assert body["practice_code_snippet"]


# ---------------------------------------------------------------------------
# Diagnostic onboarding flow (knowledge-gap driven task generation)
# ---------------------------------------------------------------------------

def test_diagnostic_onboard_and_diagnose(client, auth_student):
    auth_student("STU_TEST_001")
    assert client.post(
        "/api/student/import-analysis", json=_mastery_payload()
    ).status_code == 200

    resp = client.post("/api/student/onboard-and-diagnose")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "in_progress"
    assert body["total_tasks"] == 7
    assert body["current_task_number"] == 1
    assert body["task"]["task_type"]


def test_diagnostic_onboard_without_analysis_404(client, auth_student):
    auth_student("STU_TEST_001")
    resp = client.post("/api/student/onboard-and-diagnose")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Individual quiz (fallback question bank)
# ---------------------------------------------------------------------------

def test_individual_quiz_start_and_submit(client, auth_student):
    auth_student("STU_TEST_001")
    start = client.post(
        "/api/individual-quiz/start",
        json={
            "student_id": "STU_TEST_001",
            "topic": "Exceptions",
            "difficulty_level": "beginner",
        },
    )
    assert start.status_code == 200
    start_body = start.json()
    assert start_body["status"] == "success"
    assert start_body["total_questions"] == 7
    session_id = start_body["session_id"]

    submit = client.post(
        "/api/individual-quiz/submit-answer",
        json={"student_answer": "the output is Caught and then Cleaned"},
    )
    assert submit.status_code == 200
    assert submit.json()["status"] == "success"
    assert submit.json()["is_correct"] is True

    summary = client.get(f"/api/individual-quiz/summary/{session_id}")
    assert summary.status_code == 200
    assert summary.json()["status"] == "success"
    assert summary.json()["total_questions"] == 7


# ---------------------------------------------------------------------------
# Auth boundary: valid JWT accepted, invalid rejected
# ---------------------------------------------------------------------------

def test_jwt_auth_boundary_real_token(real_client):
    from app.config import settings
    from app.api.student_routes import verify_jwt_student
    from app.main import fastapi_app

    fastapi_app.dependency_overrides.pop(verify_jwt_student, None)

    token = jwt.encode(
        {
            "sub": "STU_TEST_001",
            "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=1),
        },
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )
    good = real_client.get(
        "/api/student/diagnostic-session/status",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert good.status_code == 200
    assert good.json()["status"] == "success"

    bad = real_client.get(
        "/api/student/diagnostic-session/status",
        headers={"Authorization": "Bearer not.a.real.token"},
    )
    assert bad.status_code == 401

    missing = real_client.get("/api/student/diagnostic-session/status")
    assert missing.status_code == 401
