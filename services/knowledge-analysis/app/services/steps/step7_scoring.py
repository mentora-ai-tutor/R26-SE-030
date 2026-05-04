from app.core.constants import WEIGHTS
from app.models.schemas import LearnerInput


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
        quiz_score = quiz_map.get(topic, 0.5)
        sbox_score = sbox_map.get(topic, 0.5)

        if mode_result["mode"] == "full":
            fs = a.get("forensic_signals") or {}
            gran = fs.get("diff_granularity", 0.5)
            refactor = min(fs.get("refactor_freq", 0.5), 1.0)
            big_bang = fs.get("big_bang_ratio", 0.0)
            for_score = max(gran * 0.5 + refactor * 0.3 - big_bang * 0.5, 0.0)
        else:
            for_score = 0.5

        mastery = WEIGHTS["sandbox"] * sbox_score + WEIGHTS["forensic"] * for_score + WEIGHTS["quiz"] * quiz_score
        scores[topic] = {
            "mastery_score": round(mastery, 3),
            "quiz_score": round(quiz_score, 3),
            "sandbox_score": round(sbox_score, 3),
            "forensic_score": round(for_score, 3),
            "priority_rank": None,
        }

    ranked = sorted(scores.keys(), key=lambda t: scores[t]["mastery_score"])
    for i, t in enumerate(ranked):
        scores[t]["priority_rank"] = i + 1

    return scores
