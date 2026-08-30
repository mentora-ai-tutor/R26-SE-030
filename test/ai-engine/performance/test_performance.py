import asyncio
import json
import logging
import time

logger = logging.getLogger(__name__)

import app.services.ollama_service as ollama_mod


def test_parse_100_ai_json_responses_under_1s():
    raw = (
        '{"annotations": [], "summary": "looks fine", "overall_score": 8}'
    )

    parsed = []
    start = time.perf_counter()
    for _ in range(100):
        parsed.append(_parse_roundtrip(raw))
    elapsed = time.perf_counter() - start

    logger.info("Parsing 100 JSON responses took %.4fs", elapsed)
    assert len(parsed) == 100
    assert elapsed < 1.0


def _parse_roundtrip(raw: str) -> dict:
    candidate = ollama_mod._find_balanced_json(raw)
    return json.loads(candidate)


def test_overridden_execute_endpoint_under_1s(client, monkeypatch):
    import app.routes as routes

    def fake_execute(code, stdin_input=None):
        return {
            "success": True, "output": "x", "error": None,
            "is_compilation_error": False, "exit_code": 0,
        }

    monkeypatch.setattr(routes, "execute_java_code", fake_execute)

    payload = {"code": "public class Main { }"}
    start = time.perf_counter()
    resp = client.post("/api/execute", json=payload)
    elapsed = time.perf_counter() - start

    logger.info("Overridden /api/execute round-trip took %.4fs", elapsed)
    assert resp.status_code == 200
    assert elapsed < 1.0
