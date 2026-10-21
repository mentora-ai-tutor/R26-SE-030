import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.api import student_routes
from app.api.student_routes import (
    _count_passed_diagnostic_tasks,
    _select_knowledge_gap,
    DiagnosticSessionStartRequest,
)
from app.api import individual_quiz_routes
from app.models.schemas import SubmitAnswerRequest

client = TestClient(app)


def test_diagnostic_gap_selection_uses_requested_unlocked_topic():
    gaps = [
        {"topic_id": "exceptions", "topic": "Exception Handling"},
        {"topic_id": "oop", "topic": "OOP and Class Design"},
    ]

    assert _select_knowledge_gap(gaps, "oop", None) == gaps[1]
    assert _select_knowledge_gap(gaps, None, " oop and class design ") == gaps[1]
    assert _select_knowledge_gap(gaps, "unknown", None) is None


def test_diagnostic_session_generates_tasks_for_requested_topic(monkeypatch):
    knowledge_gaps = [
        {
            "topic_id": "exceptions",
            "topic": "Exception Handling",
            "weak_subskills": [{"subskill": "try-catch"}],
        },
        {
            "topic_id": "oop",
            "topic": "OOP and Class Design",
            "weak_subskills": [{"subskill": "inheritance"}],
        },
    ]
    generated_for = {}

    class SessionCollection:
        inserted = None

        def find_one(self, *_args, **_kwargs):
            return None

        def insert_one(self, document):
            self.inserted = document

    collection = SessionCollection()
    monkeypatch.setattr(student_routes, "get_collection", lambda _name: collection)
    monkeypatch.setattr(
        student_routes,
        "get_latest_student_analysis",
        lambda _student_id: {"mastery_profile": {"knowledge_gaps": knowledge_gaps}},
    )

    def generate_tasks(*, topic_id, topic, subskill):
        generated_for.update(topic_id=topic_id, topic=topic, subskill=subskill)
        return [{"task_type": "code"} for _ in range(7)]

    monkeypatch.setattr(student_routes, "generate_all_diagnostic_coding_tasks", generate_tasks)

    response = student_routes.onboard_and_diagnose_student(
        "student-1",
        DiagnosticSessionStartRequest(topic_id="oop", topic="OOP and Class Design"),
    )

    assert response["task"]["task_type"] == "code"
    assert generated_for == {
        "topic_id": "oop",
        "topic": "OOP and Class Design",
        "subskill": "inheritance",
    }
    assert collection.inserted["topic_id"] == "oop"


def test_completed_diagnostic_summary_does_not_include_mastery_score(monkeypatch):
    completed_session = {
        "_id": "session-1",
        "student_id": "student-1",
        "status": "completed",
        "topic_id": "oop",
        "topic": "OOP and Class Design",
        "tasks": [{}, {}],
        "task_progress": [
            {"task_number": 1, "passed": True},
            {"task_number": 2, "passed": True},
        ],
        "tasks_passed": 2,
        "mastery_score": 100,
        "results": [{"passed": True}, {"passed": True}],
    }

    class SessionCollection:
        def find_one(self, *_args, **_kwargs):
            return completed_session

    monkeypatch.setattr(student_routes, "get_collection", lambda _name: SessionCollection())

    response = student_routes.onboard_and_diagnose_student(
        "student-1",
        DiagnosticSessionStartRequest(topic_id="oop"),
    )

    assert response["session_summary"]["tasks_passed"] == 2
    assert "mastery_score" not in response["session_summary"]


def test_diagnostic_task_summary_counts_unique_passed_tasks():
    session = {
        "task_progress": [
            {"task_number": 1, "passed": True},
            {"task_number": 2, "passed": True},
            {"task_number": 3, "passed": False},
        ],
        "results": [
            {"task_number": 1, "passed": False},
            {"task_number": 1, "passed": True},
            {"task_number": 2, "passed": True},
            {"task_number": 2, "passed": True},
        ],
    }

    assert _count_passed_diagnostic_tasks(session) == 2


def test_verification_quiz_score_counts_correct_answers(monkeypatch):
    student_id = "verification-score-test"
    session_id = "verification-score-session"
    original_sessions = individual_quiz_routes.QUIZ_SESSIONS.copy()
    original_current_sessions = individual_quiz_routes.CURRENT_SESSIONS.copy()
    individual_quiz_routes.QUIZ_SESSIONS[session_id] = {
        "student_id": student_id,
        "topic": "OOP and Class Design",
        "questions": [
            {"id": 1, "question": "Question one", "expected_answer": "correct", "explanation": "Explanation one"},
            {"id": 2, "question": "Question two", "expected_answer": "correct", "explanation": "Explanation two"},
        ],
        "current_index": 0,
        "score": 0,
        "answers_history": [],
    }
    individual_quiz_routes.CURRENT_SESSIONS[student_id] = session_id
    monkeypatch.setattr(
        individual_quiz_routes,
        "evaluate_student_answer",
        lambda **kwargs: {
            "is_correct": kwargs["student_answer"] == "correct",
            "feedback": "Evaluated",
        },
    )

    try:
        individual_quiz_routes.submit_quiz_answer(
            SubmitAnswerRequest(student_answer="correct"),
            student_id,
        )
        individual_quiz_routes.submit_quiz_answer(
            SubmitAnswerRequest(student_answer="incorrect"),
            student_id,
        )

        summary = individual_quiz_routes.get_quiz_summary(session_id)
        assert summary.correct_answers == 1
        assert summary.total_questions == 2
        assert summary.score_percentage == 50
    finally:
        individual_quiz_routes.QUIZ_SESSIONS.clear()
        individual_quiz_routes.QUIZ_SESSIONS.update(original_sessions)
        individual_quiz_routes.CURRENT_SESSIONS.clear()
        individual_quiz_routes.CURRENT_SESSIONS.update(original_current_sessions)


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