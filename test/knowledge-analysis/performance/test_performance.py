"""Performance smoke checks (loose absolute thresholds to catch regressions).

Each test runs a realistic workload against pure helpers or an overridden
endpoint and asserts a generous wall-clock ceiling. Measured seconds are
logged for the report.
"""
from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.career.model import load_model
from app.services.prompt_builder import PromptBuilder
from fakes import AUTH_HEADER, FakeDatabase, patch_auth, patch_database


@pytest.fixture
def env(monkeypatch):
    fdb = FakeDatabase()
    patch_database(monkeypatch, fdb)
    patch_auth(monkeypatch)
    yield TestClient(app), fdb


def _json_response() -> str:
    return json.dumps(
        {
            "weaknesses": ["poor iteration habits"],
            "ai_dependency": "Medium",
            "reasoning": "Frequent big-bang commits suggest assisted coding.",
            "recommendations": ["commit incrementally"],
        }
    )


def test_fifty_json_parses_under_one_second() -> None:
    fenced = "Here is the analysis:\n```json\n" + _json_response() + "\n```"
    prose = "preamble " + _json_response() + " trailing"

    start = time.perf_counter()
    for _ in range(25):
        PromptBuilder.extract_json_from_response(fenced)
        PromptBuilder.extract_json_from_response(prose)
    elapsed = time.perf_counter() - start

    print(f"  parity: 50 extract_json_from_response parses in {elapsed:.3f}s")
    assert elapsed < 1.0


def test_two_hundred_career_predictions_under_one_second() -> None:
    model = load_model()
    x = [0.62, 0.71, 0.4, 0.55, 0.68, 0.3, 0.58, 0.77]

    start = time.perf_counter()
    for _ in range(200):
        proba = model.predict_proba(x)
        row = model.rank(x)
    elapsed = time.perf_counter() - start

    assert proba.shape == (len(model.roles),)
    assert row[0][1] == float(proba.max())
    print(f"  throughput: 200 predict_proba+rank in {elapsed:.3f}s")
    assert elapsed < 1.0


def test_overridden_endpoint_under_one_second(env) -> None:
    client, _ = env
    client.get("/api/v1/knowledge-profile/me", headers=AUTH_HEADER)  # warm lifespan/caches

    start = time.perf_counter()
    for _ in range(20):
        resp = client.get("/api/v1/knowledge-profile/me", headers=AUTH_HEADER)
    elapsed = time.perf_counter() - start

    assert resp.status_code == 200
    print(f"  endpoint: 20x GET /knowledge-profile/me in {elapsed:.3f}s")
    assert elapsed < 1.0