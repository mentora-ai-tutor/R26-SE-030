"""Topic -> competency-axis mapping and inference-time featurisation.

Bridges what KAA *measures* (the canonical mastery profile + the adaptive quiz result)
into the 8-axis space the career-fit model is trained in (``ml/career_lib.py``).

It reads the **canonical contract** returned by ``get_latest_mastery_profile`` —
``knowledge_gaps[]`` and ``strengths[]`` (each carries ``topic`` + ``mastery_score`` 0–100)
plus ``data_sources`` and ``overall_mastery_score`` — NOT the raw pipeline payload, so it
stays decoupled from internal pipeline shapes.

Drift safety: axis values are keyed by axis id here; the final vector ORDER comes from the
trained ``feature_axes.json`` at serve time (``model.py``). The axis ids / topic groupings
mirror ``ml/career_lib.FEATURE_AXES`` — ``tests/test_career.py`` asserts they line up.

Pure Python (no numpy) so it is cheap to import anywhere in the service.
"""
from __future__ import annotations

from typing import Any, Dict, List

AXIS_IDS: List[str] = ["A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8"]

# Measured topics -> axis. Names match app/core/constants.py (JAVA_TOPICS + TOPIC_CATALOG).
# A7 (fluency) and A8 (authorship) are derived, not topic-sourced.
TOPIC_TO_AXIS: Dict[str, str] = {
    "Loops": "A1", "Arrays": "A1",
    "OOP": "A2", "OOP - Inheritance": "A2", "Interfaces": "A2",
    "Data Structures": "A3", "Collections": "A3", "Binary Search Trees": "A3",
    "Algorithms": "A4", "Recursion": "A4",
    "Exception Handling": "A5", "File I/O": "A5",
    "Threads": "A6",
}

_NEUTRAL = 0.5  # used when an axis has no evidence


def _as_unit(value: Any) -> float:
    """Coerce a 0-100 or 0-1 score to 0-1."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return _NEUTRAL
    if v > 1.0:
        v /= 100.0
    return max(0.0, min(v, 1.0))


def topic_mastery_from_profile(profile: Dict[str, Any]) -> Dict[str, float]:
    """Reconstruct {topic: mastery_unit} from the canonical gaps + strengths."""
    out: Dict[str, float] = {}
    for item in (profile.get("knowledge_gaps") or []):
        if item.get("topic"):
            out[item["topic"]] = _as_unit(item.get("mastery_score"))
    for item in (profile.get("strengths") or []):
        if item.get("topic"):
            out[item["topic"]] = _as_unit(item.get("mastery_score"))
    return out


def topic_mastery_from_quiz(quiz_result: Dict[str, Any]) -> Dict[str, float]:
    """Reconstruct {topic: mastery_unit} straight from quiz topic_performance
    (correct/total). Used when there is no mastery profile yet — e.g. right after the
    SkillCheckPanel quiz, before any /analyze run."""
    out: Dict[str, float] = {}
    for p in (quiz_result.get("topic_performance") or []):
        topic, total = p.get("topic"), p.get("total") or 0
        if topic and total:
            out[topic] = max(0.0, min((p.get("correct") or 0) / total, 1.0))
    return out


def measured_axis_values(topic_mastery: Dict[str, float]) -> Dict[str, float]:
    """Average per-topic mastery into A1–A6."""
    buckets: Dict[str, List[float]] = {a: [] for a in AXIS_IDS[:6]}
    for topic, mastery in topic_mastery.items():
        axis = TOPIC_TO_AXIS.get(topic)
        if axis:
            buckets[axis].append(_as_unit(mastery))
    return {a: (sum(v) / len(v) if v else _NEUTRAL) for a, v in buckets.items()}


def _fluency_axis(quiz_result: Dict[str, Any], overall_unit: float) -> float:
    """A7 — problem-solving fluency from quiz dynamics: speed, low retries, difficulty
    ceiling, and overall mastery. Falls back to overall level when no quiz dynamics."""
    if not quiz_result:
        return overall_unit
    perf = quiz_result.get("topic_performance") or []
    n = len(perf)
    avg_time = sum(float(p.get("avg_time_seconds", 0.0)) for p in perf) / n if n else 45.0
    retries = sum(float(p.get("retry_count", 0.0)) for p in perf) / n if n else 0.0
    speed = max(0.0, min((45.0 - avg_time) / 35.0, 1.0))  # ~10s fast -> 1, 45s+ slow -> 0
    retry_pen = max(0.0, 1.0 - 0.2 * retries)
    ceiling = {"easy": 0.34, "medium": 0.67, "hard": 1.0}.get(
        quiz_result.get("difficulty_reached", "medium"), 0.67
    )
    return round(0.35 * overall_unit + 0.25 * speed + 0.15 * retry_pen + 0.25 * ceiling, 4)


def _authorship_axis(profile: Dict[str, Any]) -> float:
    """A8 — independent authorship. Positive signal only when GitHub evidence exists;
    neutral (low confidence) otherwise. Dampened if any gap flags authorship risk."""
    github = (profile.get("data_sources") or {}).get("github") == "available"
    base = 0.62 if github else _NEUTRAL
    risky = any(
        "authorship" in m.lower() or "independent understanding" in m.lower()
        for gap in (profile.get("knowledge_gaps") or [])
        for m in (gap.get("misconceptions") or [])
    )
    if risky:
        base *= 0.6
    return round(base, 4)


def _merged_topic_mastery(profile: Dict[str, Any], quiz_result: Dict[str, Any]) -> Dict[str, float]:
    """Per-topic mastery from the profile (preferred — it fuses quiz+sandbox+forensic),
    topped up with quiz-only topics so a quiz-alone student still gets axis coverage."""
    tm = topic_mastery_from_profile(profile)
    for topic, mastery in topic_mastery_from_quiz(quiz_result).items():
        tm.setdefault(topic, mastery)  # profile value wins when both exist
    return tm


def build_axis_values(profile: Dict[str, Any] | None, quiz_result: Dict[str, Any] | None) -> Dict[str, float]:
    """Combine measured + derived axes into the full {axis_id: value} map (0–1).

    Works from a mastery profile, a quiz result, or both. Overall level falls back to the
    quiz score_percent when no profile exists (e.g. straight after the SkillCheckPanel)."""
    profile = profile or {}
    quiz_result = quiz_result or {}
    overall = profile.get("overall_mastery_score")
    if overall is None:
        overall = quiz_result.get("score_percent")
    overall_unit = _as_unit(overall if overall is not None else 50.0)

    values = measured_axis_values(_merged_topic_mastery(profile, quiz_result))
    values["A7"] = _fluency_axis(quiz_result, overall_unit)
    values["A8"] = _authorship_axis(profile)
    return values


def evidence_strength(profile: Dict[str, Any] | None, quiz_result: Dict[str, Any] | None) -> Dict[str, Any]:
    """How much signal backs the prediction — drives the model's evidence gate. Either a
    mastery profile OR a quiz result counts toward topic coverage."""
    profile = profile or {}
    quiz_result = quiz_result or {}
    topic_mastery = _merged_topic_mastery(profile, quiz_result)
    topics_covered = sum(1 for t in topic_mastery if t in TOPIC_TO_AXIS)
    questions = sum(int(p.get("total", 0) or 0) for p in (quiz_result.get("topic_performance") or []))
    return {
        "topics_covered": topics_covered,
        "questions_answered": questions,
        "github_available": (profile.get("data_sources") or {}).get("github") == "available",
        "sufficient": topics_covered >= 3,
    }
