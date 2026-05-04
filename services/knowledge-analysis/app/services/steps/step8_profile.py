from datetime import datetime


def step8_build_profile(student_id: str, scored: dict, clusters: dict, mode_result: dict, features: dict) -> dict:
    weak = [t for t, v in scored.items() if v["mastery_score"] < 0.50]
    medium = [t for t, v in scored.items() if 0.50 <= v["mastery_score"] < 0.75]
    strong = [t for t, v in scored.items() if v["mastery_score"] >= 0.75]

    error_dist = {}
    for topic, f in features.items():
        error_dist[topic] = {
            "syntax": round(f.get("syntax_error_rate", 0.0), 3),
            "logical": round(f.get("logical_error_rate", 0.0), 3),
            "runtime": round(f.get("runtime_error_rate", 0.0), 3),
        }

    overall = round(sum(v["mastery_score"] for v in scored.values()) / max(len(scored), 1), 3)

    return {
        "student_id": student_id,
        "mode": mode_result["mode"],
        "overall_mastery": overall,
        "weak_topics": weak,
        "medium_topics": medium,
        "strong_topics": strong,
        "misconception_clusters": clusters,
        "error_frequency": error_dist,
        "topic_scores": scored,
        "ai_dependency_flag": len(clusters.get("AI_Dependency", [])) > 0,
        "generated_at": datetime.utcnow().isoformat(),
    }
