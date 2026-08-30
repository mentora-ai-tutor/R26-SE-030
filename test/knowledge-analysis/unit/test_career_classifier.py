"""Career-fit classifier units: model inference + readiness + role matching (NumPy only)."""
from __future__ import annotations

from app.services.career.model import load_model, readiness_level
from app.services.career.predictor import _match_role


def test_readiness_level_requires_difficulty_ceiling() -> None:
    assert readiness_level(80, "hard") == "Strong Junior"
    assert readiness_level(90, "easy") == "Foundational"
    assert readiness_level(60, "medium") == "Job-ready (Junior)"
    assert readiness_level(40, "medium") == "Foundational"
    assert readiness_level(55, "easy") == "Foundational"  # 55 meets score bar but easy ceiling blocks Job-ready


def test_model_rank_is_calibrated_and_consistent() -> None:
    model = load_model()
    x = [0.8] * len(model.feature_axes)

    proba = model.predict_proba(x)
    assert proba.shape == (len(model.roles),)
    assert abs(float(proba.sum()) - 1.0) < 1e-9
    assert 0.0 <= float(proba.min()) <= float(proba.max()) <= 1.0

    ranked = model.rank(x)
    assert len(ranked) == len(model.roles)
    assert ranked[0][1] == float(proba.max())  # best-fit role has the top probability
    top = max(p for _, p in ranked)
    assert top == ranked[0][1]


def test_gaps_and_matched_are_complementary() -> None:
    model = load_model()
    role = "DSA / Algorithms-focused Engineer"
    near_max = [0.9, 0.9, 0.9, 0.95, 0.9, 0.9, 0.9, 0.9]

    assert model.matched_for(near_max, role)  # strong vector satisfies the role
    assert model.gaps_for(near_max, role) == []

    floor = [0.1] * len(model.feature_axes)
    gaps = model.gaps_for(floor, role)
    assert len(gaps) == len(model.feature_axes)  # every axis is below requirement
    assert all(g["gap"] > 0 for g in gaps)
    assert all(0 <= g["gap"] <= 1 for g in gaps)
    assert model.matched_for(floor, role) == []


def test_match_role_maps_aspirations_to_stated_labels() -> None:
    model = load_model()
    roles = model.roles

    assert _match_role("I want to be a backend developer", roles) == "Junior Java / Backend Developer"
    assert _match_role("competitive programming and algorithms", roles) == "DSA / Algorithms-focused Engineer"
    assert _match_role("QA and test automation", roles) == "QA / Test Automation Engineer"
    assert _match_role("software engineer", roles) == "General Software Engineer"
    assert _match_role("astronaut", roles) is None