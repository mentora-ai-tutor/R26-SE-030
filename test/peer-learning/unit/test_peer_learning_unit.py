"""Unit tests for pure, DB/LLM-free logic in the peer-learning service.

These exercise functions that do not require a live PostgreSQL/Mongo/Chroma or
an LLM call.  Where a module requires `openai`/`langchain_openai` at import
time, the conftest injects lightweight stubs and forces the deterministic
fallback paths (dummy OPENAI_API_KEY), so the pure logic is still exercised.
"""

from app.agents.assessment_agent import AssessmentAgent


def _agent():
    # Setting javac_available explicitly makes the check deterministic
    # regardless of whether a JDK is installed on the host.
    a = AssessmentAgent()
    a.javac_available = False
    return a


# ---------------------------------------------------------------------------
# AssessmentAgent syntax / complexity logic
# ---------------------------------------------------------------------------

def test_fallback_syntax_check_accepts_balanced_code():
    code = (
        "public class Main {\n"
        "    public static void main(String[] args) {\n"
        "        int x = 5;\n"
        "        System.out.println(x);\n"
        "    }\n"
        "}"
    )
    valid, errors = _agent()._fallback_syntax_check(code)
    assert valid is True
    assert errors == []


def test_fallback_syntax_check_rejects_mismatched_braces():
    code = "public class Main { public static void main(String[] args) { }"
    valid, errors = _agent()._fallback_syntax_check(code)
    assert valid is False
    assert any("braces" in e.lower() for e in errors)


def test_fallback_syntax_check_rejects_missing_semicolon():
    code = (
        "public class Main {\n"
        "    public static void main(String[] args) {\n"
        "        int x = 5\n"
        "    }\n"
        "}"
    )
    valid, errors = _agent()._fallback_syntax_check(code)
    assert valid is False
    assert any("semicolon" in e.lower() or ";" in e for e in errors)


def test_estimate_complexity():
    a = _agent()
    assert a._estimate_complexity("x = 1;") == "O(1)"
    assert a._estimate_complexity("for (int i=0;i<n;i++){}") == "O(n)"
    assert a._estimate_complexity(
        "for(...){ for(...){ while(...){} } }"
    ) == "O(n^3)"


def test_evaluate_java_code_empty_and_class_check():
    a = _agent()
    empty = a.evaluate_java_code("S", "")
    assert empty["evaluation"]["is_valid"] is False
    assert "empty" in empty["evaluation"]["feedback"].lower()

    no_class = a.evaluate_java_code("S", "public void run() {}")
    assert no_class["evaluation"]["is_valid"] is False
    assert "class" in no_class["evaluation"]["feedback"].lower()


def test_evaluate_java_code_valid():
    code = (
        "public class Main {\n"
        "    public static void main(String[] args) {\n"
        "        System.out.println(\"hi\");\n"
        "    }\n"
        "}"
    )
    resp = _agent().evaluate_java_code("S1", code)
    assert resp["evaluation"]["is_valid"] is True
    assert resp["status"] == "success"
    assert resp["language"] == "java"


# ---------------------------------------------------------------------------
# Difficulty / fallback helpers (pure)
# ---------------------------------------------------------------------------

def test_derive_difficulty_level_mapping():
    from app.api.individual_quiz_routes import derive_difficulty_level as q
    from app.api.question_generator_routes import derive_difficulty_level as g
    assert q(20) == "beginner"
    assert q(None) == "beginner"
    assert q(55) == "intermediate"
    assert q(85) == "advanced"
    assert g(10) == "beginner"
    assert g(50) == "intermediate"
    assert g(95) == "advanced"


def test_rag_extract_json_from_text():
    from app.api.rag_routes import extract_json_from_text
    import json as _json
    payload = '{"tutorial_title": "T", "key_highlights": ["a"]}'
    wrapped = f"Here is the JSON: {payload}  trailing text"
    assert extract_json_from_text(wrapped) == _json.loads(payload)


def test_rag_fallback_response_structure():
    from app.models.schemas import RecommendationRequest
    from app.api.rag_routes import generate_english_fallback_response
    req = RecommendationRequest(
        student_id="S1", topic="Exceptions", weak_subskill="try-catch"
    )
    resp = generate_english_fallback_response(req, "try-catch")
    assert resp.status == "success"
    assert resp.topic == "Exceptions"
    assert len(resp.key_highlights) >= 4
    assert len(resp.common_pitfalls) >= 3
    assert "class" in resp.practice_code_snippet


def test_student_agent_fallback_task_generation():
    # These hit the OpenAI stub -> service catches -> returns 7 fallback tasks.
    from app.agents.student_agent import (
        generate_all_diagnostic_coding_tasks,
        generate_peer_coding_tasks,
    )
    tasks = generate_all_diagnostic_coding_tasks("T1", "Recursion", "base case")
    assert isinstance(tasks, list)
    assert len(tasks) == 7
    types_ = {t["task_type"] for t in tasks}
    assert "write_code" in types_
    assert all("starter_code" in t for t in tasks)

    peer_tasks = generate_peer_coding_tasks("Recursion", "base case", mastery_score=40)
    assert len(peer_tasks) == 7
    assert all("task_type" in t for t in peer_tasks)


def test_peer_route_pure_helpers():
    from app.api.peer_routes import (
        _normalize_text,
        _topic_from_entry,
        _topic_score,
        _is_available,
    )
    assert _normalize_text("  Java OOP ") == "java oop"
    assert _topic_from_entry({"name": "Recursion"}) == "Recursion"
    assert _topic_from_entry({}) == ""
    assert _topic_score({"mastery_score": "80"}) == 80.0
    assert _topic_score({}) == 0.0
    assert _is_available({"available_for_peer": False}) is False
    assert _is_available({"is_active": True}) is True
    assert _is_available({}) is True
