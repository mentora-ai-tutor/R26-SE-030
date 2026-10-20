"""Tests for the career-fit prediction module (Stage B).

Async store/LLM calls are stubbed so these run with plain ``pytest`` (no Mongo, no
network, no pytest-asyncio) via ``asyncio.run``.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.models.career import CareerNarrative
from app.services.career import competency_map as cm
from app.services.career import featurizer, predictor
from app.services.career.model import load_model, readiness_level
from app.services.career.narrative import _template_narrative

ARTIFACTS = Path(__file__).resolve().parents[1] / "app" / "services" / "career" / "artifacts"


def _profile(github="unavailable"):
    return {
        "overall_mastery_score": 72,
        "data_sources": {"github": github},
        "knowledge_gaps": [
            {"topic": "Threads", "mastery_score": 40, "misconceptions": []},
            {"topic": "Exception Handling", "mastery_score": 55, "misconceptions": []},
        ],
        "strengths": [
            {"topic": "Algorithms", "mastery_score": 90},
            {"topic": "Recursion", "mastery_score": 85},
            {"topic": "Data Structures", "mastery_score": 82},
            {"topic": "OOP", "mastery_score": 78},
            {"topic": "Loops", "mastery_score": 80},
            {"topic": "Arrays", "mastery_score": 76},
        ],
    }


_QUIZ = {"difficulty_reached": "hard",
         "topic_performance": [{"topic": "Algorithms", "total": 6, "correct": 5,
                                "avg_time_seconds": 15, "retry_count": 0}]}


def test_axis_order_matches_trained_artifact():
    axes = json.loads((ARTIFACTS / "feature_axes.json").read_text())["axes"]
    assert cm.AXIS_IDS == axes  # featurizer order must equal trained weight columns


def test_model_predicts_specialisation():
    m = load_model()
    # axis order A1..A8
    assert m.rank([0.7, 0.55, 0.9, 0.92, 0.5, 0.4, 0.85, 0.5])[0][0].startswith("DSA")
    assert "Systems" in m.rank([0.7, 0.6, 0.65, 0.6, 0.6, 0.95, 0.6, 0.5])[0][0]
    assert "QA" in m.rank([0.6, 0.6, 0.5, 0.4, 0.9, 0.3, 0.6, 0.5])[0][0]
    # probabilities are calibrated -> sum to 1
    assert abs(float(m.predict_proba([0.5] * 8).sum()) - 1.0) < 1e-6


def test_featurizer_reconstructs_axes_from_canonical_profile():
    m = load_model()
    x = featurizer.featurize(_profile(), _QUIZ, m.feature_axes)
    assert len(x) == 8 and all(0 <= v <= 1 for v in x)
    # A4 (Algorithms+Recursion) should be high; A6 (Threads gap) should be low
    a4, a6 = x[m.feature_axes.index("A4")], x[m.feature_axes.index("A6")]
    assert a4 > 0.8 and a6 < 0.5


def test_evidence_gate():
    assert featurizer.evidence(_profile(), _QUIZ)["sufficient"] is True
    thin = {"overall_mastery_score": 50, "data_sources": {}, "knowledge_gaps": [],
            "strengths": [{"topic": "Loops", "mastery_score": 60}]}
    assert featurizer.evidence(thin, None)["sufficient"] is False


def test_template_narrative_names_role_and_uses_aspiration():
    nar = _template_narrative({
        "best_fit_role": "DSA / Algorithms-focused Engineer", "fit_score": 0.8,
        "readiness_level": "Strong Junior",
        "matched_competencies": ["Algorithms & Complexity"], "missing_competencies": [],
        "aspiration": {"stated_role": "Systems / Concurrency Engineer",
                       "fit_to_stated": 0.3, "est_hours_to_ready": 20, "gap_to_stated": []},
    })
    assert isinstance(nar, CareerNarrative)
    assert "DSA" in nar.headline
    assert "Systems" in nar.encouragement  # aspiration reconciled


def test_readiness_levels():
    assert readiness_level(80, "hard") == "Strong Junior"
    assert readiness_level(60, "medium") == "Job-ready (Junior)"
    assert readiness_level(30, "easy") == "Foundational"


def test_predict_career_end_to_end(monkeypatch):
    async def fake_profile(_): return _profile()
    async def fake_quiz(_): return _QUIZ
    async def fake_save(_): return {}
    async def fake_narr(facts):
        return CareerNarrative(headline=f"Your profile best fits a {facts['best_fit_role']}.")

    monkeypatch.setattr(predictor, "get_latest_mastery_profile", fake_profile)
    monkeypatch.setattr(predictor, "get_latest_result", fake_quiz)
    monkeypatch.setattr(predictor, "save_career_prediction", fake_save)
    monkeypatch.setattr(predictor, "build_narrative", fake_narr)

    out = asyncio.run(predictor.predict_career("STU_X", target_role="backend"))
    assert out["best_fit_role"] in load_model().roles
    assert out["evidence_sufficient"] is True
    assert len(out["ranked_roles"]) == 3
    assert out["aspiration_alignment"]["stated_role"].startswith("Junior Java")
    assert out["narrative"]["headline"]


def test_predict_career_no_data_is_graceful(monkeypatch):
    async def none_profile(_): return None
    async def none_quiz(_): return None
    monkeypatch.setattr(predictor, "get_latest_mastery_profile", none_profile)
    monkeypatch.setattr(predictor, "get_latest_result", none_quiz)

    out = asyncio.run(predictor.predict_career("STU_NEW"))
    assert out["evidence_sufficient"] is False
    assert out["best_fit_role"] is None
    assert "skill check" in out["note"]


_QUIZ_ONLY = {
    "score_percent": 72.0,
    "difficulty_reached": "medium",
    "topic_performance": [
        {"topic": "Algorithms", "correct": 9, "total": 10, "avg_time_seconds": 16, "retry_count": 0},
        {"topic": "Recursion", "correct": 8, "total": 10, "avg_time_seconds": 18, "retry_count": 0},
        {"topic": "Data Structures", "correct": 7, "total": 10, "avg_time_seconds": 22, "retry_count": 1},
        {"topic": "OOP", "correct": 6, "total": 10, "avg_time_seconds": 25, "retry_count": 1},
    ],
}


def test_featurize_from_quiz_only_no_profile():
    """SkillCheckPanel case: no mastery profile yet, axes come straight from the quiz."""
    m = load_model()
    x = featurizer.featurize(None, _QUIZ_ONLY, m.feature_axes)
    assert len(x) == 8
    assert x[m.feature_axes.index("A4")] > 0.8  # Algorithms+Recursion strong from quiz
    ev = featurizer.evidence(None, _QUIZ_ONLY)
    assert ev["topics_covered"] == 4 and ev["sufficient"] is True


def test_predict_career_from_quiz_only(monkeypatch):
    async def none_profile(_): return None
    async def quiz(_): return _QUIZ_ONLY
    async def fake_save(_): return {}
    async def fake_narr(facts):
        return CareerNarrative(headline=f"Your profile best fits a {facts['best_fit_role']}.")
    monkeypatch.setattr(predictor, "get_latest_mastery_profile", none_profile)
    monkeypatch.setattr(predictor, "get_latest_result", quiz)
    monkeypatch.setattr(predictor, "save_career_prediction", fake_save)
    monkeypatch.setattr(predictor, "build_narrative", fake_narr)

    out = asyncio.run(predictor.predict_career("STU_QUIZ_ONLY"))
    assert out["best_fit_role"] in load_model().roles  # predicted from quiz alone
    assert out["evidence_sufficient"] is True
    assert len(out["ranked_roles"]) == 3


def test_llm_narrative_falls_back_to_template(monkeypatch):
    """If the LLM router raises, build_narrative must return a deterministic template."""
    from app.services.career import narrative as narr_mod

    async def boom(*a, **k):
        raise RuntimeError("LLM down")

    # Force the router call to fail -> template fallback path.
    monkeypatch.setattr("app.services.llm.get_router", lambda: type("R", (), {"generate_json": boom})())
    facts = {"best_fit_role": "QA / Test Automation Engineer", "fit_score": 0.7,
             "readiness_level": "Job-ready (Junior)", "matched_competencies": ["Robustness / Error Handling"],
             "missing_competencies": [], "aspiration": None}
    nar = asyncio.run(narr_mod.build_narrative(facts))
    assert isinstance(nar, CareerNarrative) and "QA" in nar.headline
