from app.core.constants import WEIGHTS
from app.models.schemas import LearnerInput


def _weighted(entries: list[tuple[float, float]]) -> float:
    """Weighted mean over *present* signals only.

    Renormalise so a topic scored from a single source (e.g. quiz-only) is judged on
    that source alone instead of being dragged toward a phantom neutral 50 by missing
    sandbox/forensic signals.
    """
    if not entries:
        return 0.5
    total_weight = sum(weight for weight, _ in entries)
    if total_weight <= 0:
        return 0.5
    return sum(weight * value for weight, value in entries) / total_weight


def step7_score(data: LearnerInput, features: dict, mode_result: dict) -> dict:
    del features
    scores = {}
    enriched = mode_result["enriched_analysis"]
    quiz_map = {s.topic: s.correct / max(s.total, 1) for s in data.quiz_sessions}
    sbox_map = {
        s.topic: 1 - min((s.runtime_errors + s.logical_errors) / max(s.compile_attempts, 1), 1)
        for s in data.sandbox_sessions
    }

    for topic, a in enriched.items():
        # Absent sources stay None — no phantom neutral scores. A missing quiz or
        # sandbox signal means "no evidence", not "50% mastery".
        quiz_score = quiz_map.get(topic)
        sbox_score = sbox_map.get(topic)

        if mode_result["mode"] == "full":
            fs = a.get("forensic_signals") or {}
            gran = fs.get("diff_granularity", 0.5)
            refactor = min(fs.get("refactor_freq", 0.5), 1.0)
            big_bang = fs.get("big_bang_ratio", 0.0)
            for_score = max(gran * 0.5 + refactor * 0.3 - big_bang * 0.5, 0.0)
        else:
            for_score = None

        entries = []
        if sbox_score is not None:
            entries.append((WEIGHTS["sandbox"], sbox_score))
        if for_score is not None:
            entries.append((WEIGHTS["forensic"], for_score))
        if quiz_score is not None:
            entries.append((WEIGHTS["quiz"], quiz_score))

        mastery = _weighted(entries)

        scores[topic] = {
            "mastery_score": round(mastery, 3),
            "quiz_score": round(quiz_score, 3) if quiz_score is not None else None,
            "sandbox_score": round(sbox_score, 3) if sbox_score is not None else None,
            "forensic_score": round(for_score, 3) if for_score is not None else None,
            "priority_rank": None,
        }

    ranked = sorted(scores.keys(), key=lambda t: scores[t]["mastery_score"])
    for i, t in enumerate(ranked):
        scores[t]["priority_rank"] = i + 1

    return scores