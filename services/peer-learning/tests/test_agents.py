import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, Mock, patch
from types import SimpleNamespace
import asyncio
from app.main import app
from app.agents.assessment_agent import assessment_agent
from app.agents.student_agent import grade_coding_submission
from app.api import assessment_routes

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


def test_grader_rejects_unchanged_starter_without_calling_ai():
    starter_code = "public class LoopExample {\n    public static void main(String[] args) {\n        // TODO: your code here\n    }\n}"

    result = grade_coding_submission(
        topic="Java",
        subskill="for loops",
        task_description="Print numbers 1 to 10.",
        evaluation_criteria="Print each number on a new line.",
        submitted_code=starter_code,
        requirements=["Use a for loop from 1 through 10", "Print each number on a new line"],
        starter_code=starter_code,
    )

    assert result["grade"] == "fail"
    assert "starter code is unchanged" in result["feedback"]


def test_grader_accepts_optimized_square_sequence_without_calling_ai():
    submitted_code = """public class OptimizeSquare {
    public static void main(String[] args) {
        int square = 1;
        int nextOddNumber = 3;

        for (int number = 1; number <= 10; number++) {
            System.out.println(square);
            square += nextOddNumber;
            nextOddNumber += 2;
        }
    }
}"""

    with patch("app.agents.student_agent.client.beta.chat.completions.parse") as grade_with_ai:
        result = grade_coding_submission(
            topic="Loops",
            subskill="basic loop syntax",
            task_description="Optimize code to print the squares of numbers from 1 to 10 more efficiently.",
            evaluation_criteria="Refactor for readability and performance.",
            submitted_code=submitted_code,
            requirements=[
                "Refactor the current code for better readability",
                "Consider performance improvements",
                "Reduce the number of multiplications within the loop",
            ],
            task_type="improve_solution",
        )

    assert result["grade"] == "pass"
    assert "successive odd-number increments" in result["feedback"]
    grade_with_ai.assert_not_called()


def test_grader_accepts_implemented_solution_with_retained_todo_comment():
    starter_code = "public class LoopExample {\n    public static void main(String[] args) {\n        // TODO: your code here\n    }\n}"
    submitted_code = "public class LoopExample {\n    public static void main(String[] args) {\n        // TODO: your code here\n        for (int i = 1; i <= 10; i++) { System.out.println(i); }\n    }\n}"
    parsed_result = Mock()
    parsed_result.model_dump.return_value = {
        "grade": "pass",
        "feedback": "The loop prints 1 through 10, one number per line.",
        "sample_approach": "Use an incrementing for loop.",
    }
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(parsed=parsed_result))]
    )

    with patch("app.agents.student_agent.client.beta.chat.completions.parse", return_value=response):
        result = grade_coding_submission(
            topic="Java",
            subskill="for loops",
            task_description="Print numbers 1 to 10.",
            evaluation_criteria="Print each number on a new line.",
            submitted_code=submitted_code,
            requirements=["Use a for loop from 1 through 10", "Print each number on a new line"],
            starter_code=starter_code,
        )

    assert result["grade"] == "pass"


def test_improve_solution_grader_allows_readability_refactor_of_optimal_algorithm():
    starter_code = (
        "public class Fibonacci { public static void printFibonacci(int count) { "
        "int current = 0; int next = 1; for (int i = 0; i < count; i++) { "
        "System.out.print(current + \" \" ); int nextValue = current + next; "
        "current = next; next = nextValue; } } }"
    )
    submitted_code = (
        "public class Fibonacci { public static void printFibonacci(int numberOfTerms) { "
        "int currentNumber = 0; int nextNumber = 1; "
        "for (int position = 0; position < numberOfTerms; position++) { "
        "System.out.print(currentNumber + \" \" ); "
        "int followingNumber = currentNumber + nextNumber; "
        "currentNumber = nextNumber; nextNumber = followingNumber; } } }"
    )
    parsed_result = Mock()
    parsed_result.model_dump.return_value = {
        "grade": "pass",
        "feedback": "Descriptive names improve clarity and output is preserved.",
        "sample_approach": "Keep the iterative algorithm and clarify the names.",
    }
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(parsed=parsed_result))]
    )
    captured = {}

    def parse_grade(**kwargs):
        captured["prompt"] = kwargs["messages"][1]["content"]
        return response

    with patch("app.agents.student_agent.client.beta.chat.completions.parse", side_effect=parse_grade):
        result = grade_coding_submission(
            topic="Loops",
            subskill="basic loop syntax",
            task_description="Refactor the Fibonacci code for clarity without changing output.",
            evaluation_criteria="Preserve output and improve readability.",
            submitted_code=submitted_code,
            requirements=["Preserve output", "Use descriptive variable names"],
            starter_code=starter_code,
            task_type="improve_solution",
        )

    assert result["grade"] == "pass"
    assert "Original Starter Code" in captured["prompt"]
    assert "already optimal" in captured["prompt"]
    assert "Do not fail solely because" in captured["prompt"]


def test_failed_improve_solution_receives_independent_review():
    first_grade = Mock()
    first_grade.model_dump.return_value = {
        "grade": "fail",
        "feedback": "The solution did not improve complexity.",
        "sample_approach": "Consider clearer names.",
    }
    review_grade = Mock()
    review_grade.model_dump.return_value = {
        "grade": "pass",
        "feedback": "Descriptive names improve clarity and behavior is preserved.",
        "sample_approach": "Keep the iterative approach with clear names.",
    }
    responses = [
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=first_grade))]),
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(parsed=review_grade))]),
    ]
    captured_prompts = []

    def parse_grade(**kwargs):
        captured_prompts.append(kwargs["messages"][1]["content"])
        return responses.pop(0)

    with patch("app.agents.student_agent.client.beta.chat.completions.parse", side_effect=parse_grade) as grade_with_ai:
        result = grade_coding_submission(
            topic="Loops",
            subskill="basic loop syntax",
            task_description="Refactor the solution for readability without changing output.",
            evaluation_criteria="Preserve behavior and improve clarity.",
            submitted_code="class Fibonacci { int currentNumber = 0; int nextNumber = 1; }",
            requirements=["Preserve output", "Use descriptive names"],
            starter_code="class Fibonacci { int current = 0; int next = 1; }",
            task_type="improve_solution",
        )

    assert result["grade"] == "pass"
    assert grade_with_ai.call_count == 2
    assert "specific unmet requirement" in captured_prompts[1]


def test_compilation_validation_result_is_distinct_from_runtime_test_execution():
    result = assessment_agent.evaluate_java_code(
        student_id="test-student",
        code="public class Main { public static void main(String[] args) {} }",
    )

    assert result["evaluation"]["is_valid"] is True
    assert result["tests_executed"] is False
    assert result["evaluation"]["tests_executed"] is False
    assert result["evaluation"]["passed_tests"] is True


def test_passing_final_collaborative_task_closes_session_with_final_result():
    room = {
        "_id": "room-doc-1",
        "room_id": "room-1",
        "learner_student_id": "test-student",
        "status": "in_progress",
        "current_task": 7,
        "topic": "Java",
        "target_subskill": "for loops",
        "coding_tasks": [
            {
                "task_number": task_number,
                "task_type": "improve_solution" if task_number == 7 else "write_code",
                "task_description": "Print numbers 1 to 10.",
                "evaluation_criteria": "Use a for loop and print each number.",
                "requirements": ["Print 1 through 10"],
                "starter_code": "public class Main { public static void main(String[] args) { } }",
            }
            for task_number in range(1, 8)
        ],
        "task_progress": [
            {"task_number": task_number, "status": "completed" if task_number < 7 else "available", "attempts": 1 if task_number < 7 else 0, "passed": task_number < 7}
            for task_number in range(1, 8)
        ],
        "results": [],
    }

    class FakeRooms:
        def find_one(self, *_args, **_kwargs):
            return room

        def update_one(self, _query, update):
            room["results"].extend(update["$push"]["results"] if isinstance(update["$push"]["results"], list) else [update["$push"]["results"]])
            room.update(update["$set"])
            return SimpleNamespace(matched_count=1)

    broadcast = AsyncMock()
    with (
        patch.object(assessment_routes, "get_latest_student_analysis", return_value={}),
        patch.object(assessment_routes.assessment_agent, "evaluate_java_code", return_value={"evaluation": {"is_valid": True}}),
        patch.object(assessment_routes, "save_assessment"),
        patch.object(assessment_routes, "get_collection", return_value=FakeRooms()),
        patch.object(assessment_routes, "grade_coding_submission", return_value={"grade": "pass", "feedback": "Correct.", "sample_approach": "Loop through the range."}),
        patch.object(assessment_routes, "summarize_diagnostic_session", return_value={"key_points": ["Loops"], "question_summaries": []}),
        patch.object(assessment_routes.collab_manager, "broadcast_all", broadcast),
    ):
        response = asyncio.run(assessment_routes.evaluate_code(
            assessment_routes.CodeEvaluationRequest(code="public class Main { public static void main(String[] args) { for (int i = 1; i <= 10; i++) System.out.println(i); } }"),
            token_student_id="test-student",
        ))

    assert response["status"] == "session_complete"
    assert response["task_number"] == 7
    assert response["session_summary"]["results"][-1]["passed"] is True
    assert response["session_summary"]["results"][-1]["task_number"] == 7
    assert room["status"] == "completed"