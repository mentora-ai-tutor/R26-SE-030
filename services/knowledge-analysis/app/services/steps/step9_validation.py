from app.models.schemas import LearnerInput


def step9_validate(profile: dict, data: LearnerInput) -> dict:
    warnings = []
    confidence = 1.0

    ai_topics = profile["misconception_clusters"].get("AI_Dependency", [])
    for t in ai_topics:
        ts = profile["topic_scores"].get(t, {})
        quiz_score = ts.get("quiz_score")
        sandbox_score = ts.get("sandbox_score")
        if (
            quiz_score is not None
            and sandbox_score is not None
            and quiz_score > 0.85
            and sandbox_score < 0.50
        ):
            warnings.append(
                f"'{t}': high quiz score but poor sandbox performance - possible memorisation without understanding"
            )
            confidence -= 0.05

    if profile["mode"] == "reduced":
        warnings.append("GitHub data unavailable - longitudinal forensic confidence reduced")
        confidence -= 0.10

    if len(data.quiz_sessions) < 3:
        warnings.append("Sparse quiz data - profile confidence may be limited")
        confidence -= 0.05

    return {"valid": True, "confidence": round(max(confidence, 0.0), 3), "warnings": warnings}
