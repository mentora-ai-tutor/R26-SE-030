import app.routes as routes


def test_health_returns_200(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["service"] == "ai-engine"
    assert body["status"] == "running"


def test_code_review_returns_200_with_stubbed_llm(client, monkeypatch):
    async def fake_code_review(code, focus=None):
        return {
            "annotations": [
                {
                    "line_start": 1,
                    "line_end": 1,
                    "category": "style",
                    "severity": "low",
                    "message": "unused import",
                    "suggestion": "remove it",
                }
            ],
            "summary": "Looks good overall.",
            "overall_score": 7,
        }

    monkeypatch.setattr(routes, "code_review", fake_code_review)

    resp = client.post(
        "/api/code-review",
        json={"code": "public class A {}", "focus": "style"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["overall_score"] == 7
    assert body["annotations"][0]["severity"] == "low"
    assert body["model"]


def test_execute_returns_200_with_stubbed_executor(client, monkeypatch):
    def fake_execute(code, stdin_input=None):
        return {
            "success": True,
            "output": "Hello World",
            "error": None,
            "is_compilation_error": False,
            "exit_code": 0,
        }

    monkeypatch.setattr(routes, "execute_java_code", fake_execute)

    resp = client.post(
        "/api/execute",
        json={"code": "public class Main { public static void main(String[] a){ System.out.println(\"Hello World\"); } }"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["output"] == "Hello World"


def test_feedback_returns_200(client, monkeypatch):
    async def fake_feedback(code, output=None, error=None, context=None):
        return "Great job! Consider extracting a helper method."

    monkeypatch.setattr(routes, "generate_feedback", fake_feedback)

    resp = client.post(
        "/api/feedback",
        json={"code": "public class A {}", "output": "ok", "error": None, "context": "practice"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "Great job" in body["feedback"]
    assert body["model"]


def test_execute_input_validation_400(client):
    resp = client.post("/api/execute", json={"code": ""})
    assert resp.status_code == 422


def test_run_with_feedback_returns_200(client, monkeypatch):
    def fake_execute(code, stdin_input=None):
        return {
            "success": True, "output": "42", "error": None,
            "is_compilation_error": False, "exit_code": 0,
        }

    async def fake_feedback(code, output=None, error=None, context=None):
        return "Nice! Variable name could be clearer."

    monkeypatch.setattr(routes, "execute_java_code", fake_execute)
    monkeypatch.setattr(routes, "generate_feedback", fake_feedback)

    resp = client.post(
        "/api/run-with-feedback",
        json={"code": "public class Main { }", "context": "debug"},
    )
    assert resp.status_code == 200
    assert resp.json()["execution"]["output"] == "42"
    assert resp.json()["feedback"]
