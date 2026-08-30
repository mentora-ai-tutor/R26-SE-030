import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


# Test 1: Root System Status (Health Check)
def test_read_root():
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data or "system_status" in data


# Test 2: Agent 1 - Student Onboarding & Diagnostic Quiz Generation
def test_student_onboard_and_diagnose():
    payload = {
        "student_id": "STU_2026_0428",
        "name": "Test Student",
        "current_knowledge_level": "Intermediate",
        "weak_subskills": [
            {
                "topic_id": "CS101-REC",
                "topic": "Recursion",
                "weak_subskill": "base case identification",
            }
        ],
    }
    response = client.post("/api/student/onboard-and-diagnose", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "success"


# Test 3: Agent 1 - Evaluate Diagnostic Quiz Answers
def test_evaluate_diagnostic_quiz():
    payload = {
        "student_id": "STU_2026_0428",
        "submissions": [
            {
                "topic_id": "CS101-REC",
                "selected_option": "if (n <= 1) return 1;",
                "correct_answer": "if (n <= 1) return 1;",
            }
        ],
    }
    response = client.post(
        "/api/student/evaluate-diagnostic-quiz", json=payload
    )
    assert response.status_code == 200
    assert response.json()["status"] == "success"


# Test 4: Agent 2 - Assessment Agent (Code Evaluation)
def test_assessment_evaluate():
    payload = {
        "student_id": "STU_2026_0428",
        "code_snippet": "public class Main { public static void main(String[] args) {} }",
        "language": "java",
    }
    response = client.post("/api/assessment/evaluate", json=payload)
    assert response.status_code == 200


# Test 5: Agent 3 - RAG Content Recommendation
def test_content_recommend():
    payload = {
        "student_id": "STU_2026_0428",
        "weak_subskill": "base case identification",
    }
    response = client.post("/api/content/recommend", json=payload)
    assert response.status_code == 200


# Test 6: Collaborative Editor - Live Room Session Initialization
def test_initialize_collab_session():
    payload = {
        "room_id": "room-101",
        "student_id": "STU_1001",
        "peer_id": "STU_1002",
    }
    response = client.post("/api/collab/initialize-session", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "active"