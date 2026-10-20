"""Regenerate the canonical Diagnostic JSON Payload examples from the live model.

These examples are the reference teammates integrate against. They are built by the
real `build_canonical_mastery_output()` and validated by `CanonicalMasteryOutput`, so
they can never drift from what KAA actually emits. Re-run after any contract change:

    cd services/knowledge-analysis
    python ../../docs/examples/generate_examples.py

Writes:
    docs/examples/diagnostic_payload_with_github.json     (Mode A — GitHub available)
    docs/examples/diagnostic_payload_without_github.json  (Mode B — sandbox-only)
"""
import json
import os

from app.services.profile_contract import build_canonical_mastery_output

HERE = os.path.dirname(os.path.abspath(__file__))

# Mode A — GitHub available (mode=full): triangulated GitHub + sandbox + quiz signal.
PROFILE_FULL = {
    "mode": "full",
    "student_id": "STU-2026-0428",
    "session_id": "8f2a1c34-5e6b-4d7a-9c11-2b3e4f5a6d7c",
    "generated_at": "2026-03-18T14:30:00Z",
    "overall_mastery": 0.58,
    "topic_scores": {
        "Loops":               {"mastery_score": 0.95, "quiz_score": 0.95, "sandbox_score": 0.90, "forensic_score": 0.80},
        "Recursion":           {"mastery_score": 0.41, "quiz_score": 0.20, "sandbox_score": 0.00, "forensic_score": 0.30},
        "Binary Search Trees": {"mastery_score": 0.30, "quiz_score": 0.15, "sandbox_score": 0.50, "forensic_score": 0.06},
        "Exception Handling":  {"mastery_score": 0.60, "quiz_score": 0.60, "sandbox_score": 0.67, "forensic_score": 0.60},
        "File I/O":            {"mastery_score": 0.92, "quiz_score": 0.90, "sandbox_score": 0.92, "forensic_score": 0.94},
    },
    "weak_topics": ["Recursion", "Binary Search Trees"],
    "medium_topics": ["Exception Handling"],
    "strong_topics": ["Loops", "File I/O"],
    "misconception_clusters": {"AI_Dependency": ["Recursion", "Binary Search Trees"]},
    "error_frequency": {
        "Recursion": {"logical": 0.80, "runtime": 0.30},
        "Binary Search Trees": {"logical": 0.50},
        "Exception Handling": {"logical": 0.30},
    },
}
VALIDATION_FULL = {"data_quality": "high", "confidence": 0.85, "warnings": []}

# Mode B — GitHub unavailable (mode=reduced): sandbox + quiz only, confidence scaled down.
PROFILE_REDUCED = {
    "mode": "reduced",
    "student_id": "STU-2026-0932",
    "session_id": None,
    "generated_at": "2026-03-18T15:00:00Z",
    "overall_mastery": 0.78,
    "topic_scores": {
        "Loops":               {"mastery_score": 0.98, "quiz_score": 0.98, "sandbox_score": 0.95},
        "Recursion":           {"mastery_score": 0.70, "quiz_score": 0.70, "sandbox_score": 0.74},
        "Binary Search Trees": {"mastery_score": 0.66, "quiz_score": 0.65, "sandbox_score": 0.67},
        "Exception Handling":  {"mastery_score": 0.92, "quiz_score": 0.92, "sandbox_score": 0.95},
        "OOP - Inheritance":   {"mastery_score": 0.88, "quiz_score": 0.88, "sandbox_score": 0.90},
    },
    "weak_topics": ["Binary Search Trees", "Recursion"],
    "medium_topics": [],
    "strong_topics": ["Loops", "Exception Handling", "OOP - Inheritance"],
    "misconception_clusters": {},
    "error_frequency": {
        "Recursion": {"runtime": 0.25},
        "Binary Search Trees": {"logical": 0.30},
    },
}
VALIDATION_REDUCED = {"data_quality": "medium", "confidence": 0.75, "warnings": ["github_unavailable"]}


def _write(name, profile, validation):
    payload = build_canonical_mastery_output(profile, validation)  # raises if invalid
    path = os.path.join(HERE, name)
    with open(path, "w") as handle:
        json.dump(payload, handle, indent=2)
    print(f"wrote {name}  (schema_version={payload['schema_version']}, github={payload['data_sources']['github']})")


if __name__ == "__main__":
    _write("diagnostic_payload_with_github.json", PROFILE_FULL, VALIDATION_FULL)
    _write("diagnostic_payload_without_github.json", PROFILE_REDUCED, VALIDATION_REDUCED)
