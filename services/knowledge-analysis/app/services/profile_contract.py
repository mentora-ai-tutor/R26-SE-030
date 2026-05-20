from __future__ import annotations

from typing import Any, Optional

from app.core.constants import MASTERY_PROFILE_SCHEMA_VERSION, TOPIC_CATALOG
from app.models.schemas import CanonicalMasteryOutput


DEFAULT_TOPIC = {
    "topic_id": "CS-GEN",
    "prerequisite_topics": ["Basic Java Syntax"],
    "related_topics": [],
    "subskills": [
        {
            "subskill": "core concept application",
            "subskill_id": "CS-GEN-CORE",
            "focus": "Review the core concept with small traceable examples.",
            "misconception": "cannot reliably apply the concept independently",
        }
    ],
}


def build_canonical_mastery_output(profile: dict[str, Any], validation: dict[str, Any]) -> dict[str, Any]:
    """Build the DB/API contract consumed by LMG, n8n, peer learning, and dashboards."""
    mode = profile.get("mode", "reduced")
    topic_scores = profile.get("topic_scores", {})
    overall_mastery_score = _pct(profile.get("overall_mastery", 0.0))
    data_sources = {
        "github": "available" if mode == "full" else "unavailable",
        "sandbox": "available",
        "quizzes": "available",
    }

    gaps: list[dict[str, Any]] = []
    strengths: list[dict[str, Any]] = []

    for topic, scores in topic_scores.items():
        topic_meta = _topic_meta(topic)
        mastery_score = _pct(scores.get("mastery_score", 0.0))
        weak_subskills = _weak_subskills(topic, topic_meta, scores, profile)
        confidence = _confidence(scores, validation, data_sources, weak_subskills)

        gap_type = _gap_type(mastery_score, weak_subskills)
        if gap_type:
            gap = {
                "topic": topic,
                "topic_id": topic_meta["topic_id"],
                "gap_type": gap_type,
                "confidence": confidence,
                "mastery_score": mastery_score,
                "weak_subskills": weak_subskills,
                "known_subskills": _known_subskills(topic_meta, weak_subskills),
                "misconceptions": _misconceptions(weak_subskills, scores, profile, topic),
                "observed_error_patterns": _observed_error_patterns(topic, scores, profile, data_sources),
                "evidence_summary": _evidence_summary(topic, mastery_score, scores, profile, data_sources),
                "prerequisite_topics": topic_meta.get("prerequisite_topics", []),
                "related_topics": topic_meta.get("related_topics", []),
                "suggested_intervention": _suggested_intervention(gap_type, weak_subskills, topic_meta),
            }
            gaps.append(gap)
        else:
            strengths.append(
                {
                    "topic": topic,
                    "topic_id": topic_meta["topic_id"],
                    "confidence": confidence,
                    "mastery_score": mastery_score,
                    "mastery_level": "advanced" if mastery_score >= 85 else "proficient",
                    "evidence_summary": _strength_summary(topic, mastery_score, scores, data_sources),
                    "known_subskills": _known_subskills(topic_meta, []),
                    "can_teach_others": mastery_score >= 85 and confidence >= 0.8,
                }
            )

    gaps.sort(key=lambda item: (item["mastery_score"], -item["confidence"]))
    strengths.sort(key=lambda item: item["mastery_score"], reverse=True)

    payload = {
        "schema_version": MASTERY_PROFILE_SCHEMA_VERSION,
        "student_id": profile["student_id"],
        "analysis_timestamp": profile["generated_at"],
        "data_sources": data_sources,
        "mastery_profile": {
            "overall_mastery_score": overall_mastery_score,
            "knowledge_gaps": gaps,
            "strengths": strengths,
        },
        "recommendations": _recommendations(gaps, strengths, data_sources),
        "overall_mastery_score": overall_mastery_score,
        "knowledge_gaps": gaps,
        "strengths": strengths,
        "gap_topic_ids": [gap["topic_id"] for gap in gaps],
        "raw_analysis_payload": {
            "mode": profile.get("mode"),
            "topic_scores": topic_scores,
            "weak_topics": profile.get("weak_topics", []),
            "medium_topics": profile.get("medium_topics", []),
            "strong_topics": profile.get("strong_topics", []),
            "misconception_clusters": profile.get("misconception_clusters", {}),
            "error_frequency": profile.get("error_frequency", {}),
            "validation": validation,
        },
    }

    return CanonicalMasteryOutput.model_validate(payload).model_dump()


def _pct(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    if number <= 1:
        number *= 100
    return round(max(0.0, min(number, 100.0)), 1)


def _topic_meta(topic: str) -> dict[str, Any]:
    return TOPIC_CATALOG.get(topic, DEFAULT_TOPIC)


def _gap_type(mastery_score: float, weak_subskills: list[dict[str, Any]]) -> Optional[str]:
    if not weak_subskills:
        return None
    if mastery_score < 50:
        return "FUNDAMENTAL_GAP"
    if mastery_score < 75:
        return "PARTIAL_GAP"
    if mastery_score < 85 and weak_subskills:
        return "SURFACE_GAP"
    return None


def _weak_subskills(
    topic: str,
    topic_meta: dict[str, Any],
    scores: dict[str, Any],
    profile: dict[str, Any],
) -> list[dict[str, Any]]:
    subskills = topic_meta.get("subskills", DEFAULT_TOPIC["subskills"])
    error_frequency = profile.get("error_frequency", {}).get(topic, {})
    quiz_score = float(scores.get("quiz_score", 0.5))
    sandbox_score = float(scores.get("sandbox_score", 0.5))

    weak_indexes: set[int] = set()
    if quiz_score < 0.75:
        weak_indexes.add(0)
    if sandbox_score < 0.75:
        weak_indexes.add(min(1, len(subskills) - 1))
    if error_frequency.get("logical", 0) >= 0.25 or error_frequency.get("runtime", 0) >= 0.25:
        weak_indexes.add(min(len(subskills) - 1, 1))
    if error_frequency.get("syntax", 0) >= 0.25:
        weak_indexes.add(0)
    if quiz_score < 0.50 or sandbox_score < 0.50:
        weak_indexes.update(range(min(2, len(subskills))))

    if not weak_indexes and (quiz_score < 0.85 or sandbox_score < 0.85):
        weak_indexes.add(0)

    evidence = _subskill_evidence(topic, scores, profile)
    return [
        {
            "subskill": subskills[index]["subskill"],
            "subskill_id": subskills[index]["subskill_id"],
            "status": "weak",
            "evidence": evidence,
            "recommended_content_focus": subskills[index]["focus"],
        }
        for index in sorted(weak_indexes)
    ]


def _known_subskills(
    topic_meta: dict[str, Any],
    weak_subskills: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    weak_ids = {item["subskill_id"] for item in weak_subskills}
    known = []
    for subskill in topic_meta.get("subskills", DEFAULT_TOPIC["subskills"]):
        if subskill["subskill_id"] not in weak_ids:
            known.append(
                {
                    "subskill": subskill["subskill"],
                    "subskill_id": subskill["subskill_id"],
                    "status": "mastered",
                    "evidence": "No major weakness detected for this subskill in the available signals.",
                    "recommended_content_focus": None,
                }
            )
    return known


def _misconceptions(
    weak_subskills: list[dict[str, Any]],
    scores: dict[str, Any],
    profile: dict[str, Any],
    topic: str,
) -> list[str]:
    meta_by_id = {
        subskill["subskill_id"]: subskill
        for subskill in _topic_meta(topic).get("subskills", DEFAULT_TOPIC["subskills"])
    }
    misconceptions = [
        meta_by_id[item["subskill_id"]]["misconception"]
        for item in weak_subskills
        if item["subskill_id"] in meta_by_id
    ]

    if scores.get("quiz_score", 1) < 0.5:
        misconceptions.append("answers conceptual questions incorrectly")
    if topic in profile.get("misconception_clusters", {}).get("AI_Dependency", []):
        misconceptions.append("submitted correct-looking code but needs independent understanding verification")

    return _dedupe(misconceptions)


def _observed_error_patterns(
    topic: str,
    scores: dict[str, Any],
    profile: dict[str, Any],
    data_sources: dict[str, str],
) -> dict[str, list[str]]:
    error_frequency = profile.get("error_frequency", {}).get(topic, {})
    sandbox = []
    if scores.get("sandbox_score", 1) < 0.75:
        sandbox.append("low sandbox success signal")
    if error_frequency.get("syntax", 0) >= 0.25:
        sandbox.append("recurring syntax errors")
    if error_frequency.get("logical", 0) >= 0.25:
        sandbox.append("logical errors during implementation")
    if error_frequency.get("runtime", 0) >= 0.25:
        sandbox.append("runtime failures during execution")

    quizzes = []
    if scores.get("quiz_score", 1) < 0.75:
        quizzes.append("low quiz correctness for this topic")
    if scores.get("quiz_score", 1) < 0.5:
        quizzes.append("major conceptual misunderstanding signal")

    github = []
    if data_sources["github"] == "available":
        if scores.get("forensic_score", 1) < 0.5:
            github.append("low forensic confidence for incremental learning")
        if topic in profile.get("misconception_clusters", {}).get("AI_Dependency", []):
            github.append("authorship-risk signal from commit or editing pattern")

    return {
        "github": github,
        "sandbox": sandbox,
        "quizzes": quizzes,
    }


def _subskill_evidence(topic: str, scores: dict[str, Any], profile: dict[str, Any]) -> str:
    parts = []
    if scores.get("quiz_score", 1) < 0.75:
        parts.append(f"quiz score is {_pct(scores.get('quiz_score', 0))}")
    if scores.get("sandbox_score", 1) < 0.75:
        parts.append(f"sandbox score is {_pct(scores.get('sandbox_score', 0))}")
    error_frequency = profile.get("error_frequency", {}).get(topic, {})
    error_parts = [
        name
        for name, value in error_frequency.items()
        if value >= 0.25
    ]
    if error_parts:
        parts.append("observed " + ", ".join(error_parts) + " errors")
    return "; ".join(parts) if parts else "Topic-level mastery is below the threshold for confident mastery."


def _evidence_summary(
    topic: str,
    mastery_score: float,
    scores: dict[str, Any],
    profile: dict[str, Any],
    data_sources: dict[str, str],
) -> str:
    chunks = [
        f"{topic} mastery is {mastery_score}/100.",
        f"Quiz signal {_pct(scores.get('quiz_score', 0))}/100.",
        f"Sandbox signal {_pct(scores.get('sandbox_score', 0))}/100.",
    ]
    if data_sources["github"] == "available":
        chunks.append(f"GitHub forensic signal {_pct(scores.get('forensic_score', 0))}/100.")
    else:
        chunks.append("GitHub evidence unavailable; diagnosis uses sandbox and quiz signals.")
    if topic in profile.get("misconception_clusters", {}).get("AI_Dependency", []):
        chunks.append("Authorship-risk indicators require live verification before treating submitted code as mastery.")
    return " ".join(chunks)


def _strength_summary(
    topic: str,
    mastery_score: float,
    scores: dict[str, Any],
    data_sources: dict[str, str],
) -> str:
    parts = [
        f"{topic} is currently a strength with mastery {mastery_score}/100.",
        f"Quiz signal {_pct(scores.get('quiz_score', 0))}/100 and sandbox signal {_pct(scores.get('sandbox_score', 0))}/100.",
    ]
    if data_sources["github"] == "available":
        parts.append(f"GitHub forensic signal {_pct(scores.get('forensic_score', 0))}/100.")
    return " ".join(parts)


def _suggested_intervention(
    gap_type: str,
    weak_subskills: list[dict[str, Any]],
    topic_meta: dict[str, Any],
) -> dict[str, Any]:
    objectives = [
        _objective_from_subskill(item["subskill"])
        for item in weak_subskills
    ]
    if not objectives:
        objectives = ["Rebuild confidence on the core topic through guided practice."]

    if gap_type == "FUNDAMENTAL_GAP":
        return {
            "primary": "interactive_tutorial",
            "secondary": ["step_by_step_practice", "debugging_exercise"],
            "difficulty_level": "beginner",
            "estimated_time_minutes": 90,
            "learning_objectives": objectives,
        }
    if gap_type == "PARTIAL_GAP":
        return {
            "primary": "step_by_step_practice",
            "secondary": ["targeted_quiz", "debugging_exercise"],
            "difficulty_level": "intermediate",
            "estimated_time_minutes": 60,
            "learning_objectives": objectives,
        }
    return {
        "primary": "targeted_quiz",
        "secondary": ["short_practice_set", "worked_example"],
        "difficulty_level": "intermediate",
        "estimated_time_minutes": 30,
        "learning_objectives": objectives or topic_meta.get("related_topics", []),
    }


def _objective_from_subskill(subskill: str) -> str:
    return f"Improve {subskill} through traceable examples and independent practice."


def _recommendations(
    gaps: list[dict[str, Any]],
    strengths: list[dict[str, Any]],
    data_sources: dict[str, str],
) -> dict[str, Any]:
    priority_order = [gap["topic"] for gap in gaps]
    advice = "Generate learning materials from weak_subskills before broad topic summaries."
    if not gaps:
        advice = "No major gaps detected; generate enrichment or review material from strengths if needed."

    instructor_parts = []
    if gaps:
        instructor_parts.append("Verify the highest-priority gap with a short live task before marking mastery.")
    if data_sources["github"] == "unavailable":
        instructor_parts.append("GitHub is unavailable, so confidence depends on sandbox and quiz evidence.")
    if strengths:
        instructor_parts.append("Use high-confidence strengths for peer-learning matching where can_teach_others is true.")

    return {
        "priority_order": priority_order,
        "general_advice": advice,
        "for_instructor": " ".join(instructor_parts) if instructor_parts else "Continue monitoring future attempts.",
    }


def _confidence(
    scores: dict[str, Any],
    validation: dict[str, Any],
    data_sources: dict[str, str],
    weak_subskills: list[dict[str, Any]],
) -> float:
    base = float(validation.get("confidence", 0.75))
    available_sources = 2 + (1 if data_sources["github"] == "available" else 0)
    source_factor = available_sources / 3
    agreement_bonus = 0.06 if weak_subskills and scores.get("quiz_score", 1) < 0.75 and scores.get("sandbox_score", 1) < 0.75 else 0
    return round(max(0.35, min(base * source_factor + agreement_bonus, 0.99)), 2)


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    deduped = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            deduped.append(value)
    return deduped
