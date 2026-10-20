from app.api import individual_quiz_routes as quiz_routes
from app.models.schemas import SubmitAnswerRequest


def _session(student_id, questions):
    return {
        "student_id": student_id,
        "topic": "Java loops",
        "difficulty_level": "beginner",
        "questions": questions,
        "current_index": 0,
        "score": 0,
        "answers_history": [],
    }


def test_incorrect_answer_advances_to_next_question(monkeypatch):
    session_id = "retry-session"
    student_id = "retry-student"
    quiz_routes.QUIZ_SESSIONS[session_id] = _session(student_id, [
        {"id": 1, "question": "Print 1 to 10", "expected_answer": "for loop", "explanation": "Use a loop."},
        {"id": 2, "question": "Next task", "expected_answer": "answer", "explanation": "Next."},
    ])
    quiz_routes.CURRENT_SESSIONS[student_id] = session_id
    monkeypatch.setattr(
        quiz_routes,
        "evaluate_student_answer",
        lambda **_kwargs: {"is_correct": False, "feedback": "Try again."},
    )

    response = quiz_routes.submit_quiz_answer(
        SubmitAnswerRequest(student_answer="wrong"),
        token_student_id=student_id,
    )

    assert response.is_correct is False
    assert response.next_question.id == 2
    assert response.is_quiz_completed is False
    assert quiz_routes.QUIZ_SESSIONS[session_id]["current_index"] == 1


def test_correct_final_answer_completes_session_with_summary(monkeypatch):
    session_id = "final-session"
    student_id = "final-student"
    quiz_routes.QUIZ_SESSIONS[session_id] = _session(student_id, [
        {"id": 1, "question": "Print 1 to 10", "expected_answer": "for loop", "explanation": "Use a loop."},
    ])
    quiz_routes.CURRENT_SESSIONS[student_id] = session_id
    monkeypatch.setattr(
        quiz_routes,
        "evaluate_student_answer",
        lambda **_kwargs: {"is_correct": True, "feedback": "Correct."},
    )

    response = quiz_routes.submit_quiz_answer(
        SubmitAnswerRequest(student_answer="for loop"),
        token_student_id=student_id,
    )

    assert response.is_correct is True
    assert response.is_quiz_completed is True
    assert response.next_question is None
    assert response.session_summary["session_id"] == session_id
    assert response.session_summary["correct_answers"] == 1
    assert response.session_summary["detailed_history"][-1]["is_correct"] is True
    assert "correct_answer" not in response.model_dump()
    assert "expected_answer" not in response.session_summary["detailed_history"][-1]
    assert quiz_routes.QUIZ_SESSIONS[session_id]["status"] == "completed"
    assert quiz_routes.QUIZ_SESSIONS[session_id]["current_index"] == 1


def test_incorrect_final_answer_still_completes_and_reports_mastery(monkeypatch):
    session_id = "incorrect-final-session"
    student_id = "incorrect-final-student"
    quiz_routes.QUIZ_SESSIONS[session_id] = _session(student_id, [
        {"id": 1, "question": "Print 1 to 10", "expected_answer": "for loop", "explanation": "Use a loop."},
    ])
    quiz_routes.CURRENT_SESSIONS[student_id] = session_id
    monkeypatch.setattr(
        quiz_routes,
        "evaluate_student_answer",
        lambda **_kwargs: {"is_correct": False, "feedback": "Not correct."},
    )

    response = quiz_routes.submit_quiz_answer(
        SubmitAnswerRequest(student_answer="wrong"),
        token_student_id=student_id,
    )

    assert response.is_correct is False
    assert response.is_quiz_completed is True
    assert response.session_summary["correct_answers"] == 0
    assert response.session_summary["mastery_score"] == 0
    assert quiz_routes.QUIZ_SESSIONS[session_id]["status"] == "completed"


def test_exact_answer_passes_without_llm_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "dummy_key")

    result = quiz_routes.evaluate_student_answer(
        question="Write a loop.",
        expected_answer="for (int i = 1; i <= 10; i++) { System.out.println(i); }",
        student_answer="for (int i=1; i<=10; i++) {\n System.out.println(i);\n}",
    )

    assert result["is_correct"] is True


def test_mastery_start_generates_questions_for_analyzed_topic(monkeypatch):
    session_id = "mastery-session"
    generated = [{"id": index, "question": f"Question {index}", "expected_answer": "answer"} for index in range(1, 8)]
    called = {}
    monkeypatch.setattr(
        quiz_routes,
        "get_latest_student_analysis",
        lambda _student_id: {
            "knowledge_gaps": [{"topic": "Java for loops"}],
            "mastery_profile": {"overall_mastery_score": 30},
        },
    )

    def generate(topic, difficulty):
        called["topic"] = topic
        called["difficulty"] = difficulty
        return generated

    monkeypatch.setattr(quiz_routes, "generate_random_7_questions", generate)
    monkeypatch.setattr(quiz_routes.uuid, "uuid4", lambda: session_id)

    response = quiz_routes.start_individual_quiz(token_student_id="mastery-student", request=None)

    assert called == {"topic": "Java for loops", "difficulty": "beginner"}
    assert response.session_id == session_id
    assert response.first_question.question == "Question 1"


def test_mastery_score_uses_first_attempts_and_updates_student_analysis(monkeypatch):
    session_id = "scored-session"
    student_id = "scored-student"
    analysis = {
        "_id": "analysis-1",
        "student_id": student_id,
        "mastery_profile": {
            "overall_mastery_score": 30,
            "knowledge_gaps": [
                {"topic": "Java loops", "mastery_score": 20},
                {"topic": "Recursion", "mastery_score": 40},
            ],
        },
    }
    quiz_routes.QUIZ_SESSIONS[session_id] = _session(student_id, [
        {"id": 1, "question": "First", "expected_answer": "one", "explanation": "First explanation."},
        {"id": 2, "question": "Second", "expected_answer": "two", "explanation": "Second explanation."},
    ])
    quiz_routes.QUIZ_SESSIONS[session_id].update({
        "session_id": session_id,
        "analysis_id": analysis["_id"],
    })
    quiz_routes.CURRENT_SESSIONS[student_id] = session_id
    eval_results = iter([
        {"is_correct": False, "feedback": "No."},
        {"is_correct": True, "feedback": "Yes."},
    ])
    monkeypatch.setattr(quiz_routes, "evaluate_student_answer", lambda **_kwargs: next(eval_results))

    class FakeAnalyses:
        def __init__(self):
            self.update = None

        def find_one(self, query):
            assert query == {"_id": "analysis-1"}
            return analysis

        def update_one(self, query, update):
            assert query == {"_id": "analysis-1", "student_id": student_id}
            self.update = update

    analyses = FakeAnalyses()
    monkeypatch.setattr(quiz_routes, "get_collection", lambda name: analyses)

    wrong_response = quiz_routes.submit_quiz_answer(
        SubmitAnswerRequest(student_answer="wrong"), token_student_id=student_id
    )
    final_response = quiz_routes.submit_quiz_answer(
        SubmitAnswerRequest(student_answer="two"), token_student_id=student_id
    )

    assert "correct_answer" not in wrong_response.model_dump()
    assert "expected_answer" not in final_response.session_summary["detailed_history"][0]
    assert "one" not in wrong_response.explanation
    assert wrong_response.next_question.id == 2
    assert final_response.session_summary["correct_answers"] == 1
    assert final_response.session_summary["correct_on_first_attempt"] == 1
    assert final_response.session_summary["mastery_score"] == 50
    assert final_response.session_summary["overall_mastery_score"] == 45
    updated = analyses.update["$set"]
    assert updated["mastery_profile"]["knowledge_gaps"][0]["mastery_score"] == 50
    assert updated["overall_mastery_score"] == 45
    assert updated["mastery_verification"]["session_id"] == session_id