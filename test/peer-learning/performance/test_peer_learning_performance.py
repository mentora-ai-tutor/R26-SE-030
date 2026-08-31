"""Performance smoke tests: generous timing bounds using time.perf_counter().

These assert that pure parsing/agent-response logic and an overridden HTTP
endpoint complete comfortably within loose wall-clock budgets, so they remain
stable on CI machines.
"""

import time
import json

from app.api.rag_routes import extract_json_from_text
from app.agents.assessment_agent import AssessmentAgent

LLM_LIKE_RESPONSES = [
    (
        'Sure! Here you go:\n'
        + json.dumps(
            {
                "tutorial_title": "Java Masterclass: Exceptions (try-catch)",
                "key_highlights": ["a", "b", "c", "d"],
                "common_pitfalls": ["p1", "p2", "p3"],
            }
        )
        + "\nHope that helps."
    )
    for _ in range(200)
]


def test_200_agent_response_parses_under_1s():
    start = time.perf_counter()
    for text in LLM_LIKE_RESPONSES:
        parsed = extract_json_from_text(text)
        assert parsed["tutorial_title"]
    elapsed = time.perf_counter() - start
    print(f"[perf] 200 agent-response parses took {elapsed:.4f}s")
    assert elapsed < 1.0


def test_200_syntax_checks_under_1s():
    agent = AssessmentAgent()
    agent.javac_available = False
    valid_code = (
        "public class Main {\n"
        "    public static void main(String[] args) {\n"
        "        int x = 5;\n"
        "        System.out.println(x);\n"
        "    }\n"
        "}"
    )
    start = time.perf_counter()
    for _ in range(200):
        ok, errors = agent._fallback_syntax_check(valid_code)
        assert ok is True and errors == []
    elapsed = time.perf_counter() - start
    print(f"[perf] 200 syntax checks took {elapsed:.4f}s")
    assert elapsed < 1.0


def test_overridden_endpoint_under_1s(client):
    from app.models.schemas import RecommendationRequest
    from app.api.rag_routes import recommend_learning_materials

    request = RecommendationRequest(
        student_id="PERF_S", topic="Exceptions", weak_subskill="try-catch"
    )

    # Warm up JIT / import overhead once outside the timed window.
    recommend_learning_materials(request)

    start = time.perf_counter()
    resp = client.post(
        "/api/rag-content/recommend",
        json={
            "student_id": "PERF_S",
            "topic": "Exceptions",
            "weak_subskill": "try-catch",
        },
    )
    elapsed = time.perf_counter() - start
    assert resp.status_code == 200
    print(f"[perf] overridden /api/rag-content/recommend took {elapsed:.4f}s")
    assert elapsed < 1.0
