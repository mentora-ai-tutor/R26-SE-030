"""Canonical mastery contract shape + stored-document serialization (pure)."""
from __future__ import annotations

from app.models.schemas import CanonicalMasteryOutput
from app.services.mastery_profile_store import build_mastery_profile_document
from app.services.profile_contract import build_canonical_mastery_output


def _profile() -> dict:
    return {
        "student_id": "STU-C-101",
        "session_id": "sess-9f",
        "mode": "reduced",
        "overall_mastery": 0.62,
        "weak_topics": ["Recursion"],
        "medium_topics": ["OOP"],
        "strong_topics": ["Loops", "Arrays"],
        "misconception_clusters": {"AI_Dependency": []},
        "error_frequency": {},
        "topic_scores": {
            "Loops": {"mastery_score": 0.94, "quiz_score": 0.9, "sandbox_score": 0.95, "forensic_score": 0.0},
            "Arrays": {"mastery_score": 0.86, "quiz_score": 0.8, "sandbox_score": 0.9, "forensic_score": 0.0},
            "OOP": {"mastery_score": 0.64, "quiz_score": 0.6, "sandbox_score": 0.7, "forensic_score": 0.0},
            "Recursion": {"mastery_score": 0.42, "quiz_score": 0.4, "sandbox_score": 0.45, "forensic_score": 0.0},
        },
        "generated_at": "2026-04-02T09:30:00Z",
    }


def test_canonical_contract_serializes_to_schema_valid_shape() -> None:
    validation = {"confidence": 0.8}
    out = build_canonical_mastery_output(_profile(), validation)

    # contract shapes must validate against the shared Pydantic model
    CanonicalMasteryOutput.model_validate(out)

    assert out["data_sources"]["github"] == "unavailable"  # reduced mode
    assert out["data_sources"]["sandbox"] == "available"
    # Recursion (42%, quiz/sandbox <0.75) and OOP (64%, partial gap) are both gaps,
    # ordered ascending by mastery; gap_topic_ids mirrors that order.
    assert out["gap_topic_ids"] == ["CS101-REC", "CS201-OOP"]
    assert out["recommendations"]["priority_order"] == ["Recursion", "OOP"]

    recursion, oop = out["knowledge_gaps"]
    assert recursion["gap_type"] == "FUNDAMENTAL_GAP"
    assert recursion["mastery_score"] == 42.0
    assert recursion["topic_id"] == "CS101-REC"
    assert recursion["suggested_intervention"]["primary"] == "interactive_tutorial"
    assert recursion["suggested_intervention"]["difficulty_level"] == "beginner"
    assert oop["gap_type"] == "PARTIAL_GAP"
    assert oop["topic_id"] == "CS201-OOP"
    assert oop["suggested_intervention"]["primary"] == "step_by_step_practice"

    strengths = {s["topic"]: s for s in out["strengths"]}
    assert set(strengths) == {"Loops", "Arrays"}
    loops = strengths["Loops"]
    assert loops["mastery_level"] == "advanced"
    # reduced mode discounts confidence (2/3 source factor, no GitHub), so can_teach_others
    # (mastery >= 85 and confidence >= 0.8) is gated off: 0.8 * 2/3 == 0.53
    assert loops["confidence"] == 0.53
    assert loops["can_teach_others"] is False


def test_mastery_document_shape_mirrors_canonical_fields() -> None:
    canonical = build_canonical_mastery_output(
        _profile(), {"confidence": 0.8, "valid": True}
    )

    doc = build_mastery_profile_document(
        canonical,
        raw_analysis_payload={"mode": "reduced"},
        diagnostic_report={"schema_version": "kaa-forensic-report-v1.0"},
    )

    # nested contract + flattened convenience fields stay in sync
    assert doc["mastery_profile"]["overall_mastery_score"] == doc["overall_mastery_score"]
    assert doc["mastery_profile"]["knowledge_gaps"] == doc["knowledge_gaps"]
    assert doc["gap_topic_ids"] == ["CS101-REC", "CS201-OOP"]
    assert doc["raw_analysis_payload"] == {"mode": "reduced"}
    assert doc["diagnostic_report"]["schema_version"] == "kaa-forensic-report-v1.0"
    assert doc.get("created_at") is not None and doc.get("updated_at") is not None

    # without a diagnostic report the key is absent (backward compatible)
    legacy = build_mastery_profile_document(canonical)
    assert "diagnostic_report" not in legacy