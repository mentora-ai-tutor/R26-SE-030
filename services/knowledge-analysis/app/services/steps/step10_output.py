from app.services.profile_contract import build_canonical_mastery_output


def step10_output(profile: dict, validation: dict) -> dict:
    canonical = build_canonical_mastery_output(profile, validation)
    canonical["legacy_summary"] = {
        "schema_version": "kaa-v1.0",
        "student_id": profile["student_id"],
        "mode": profile["mode"],
        "overall_mastery": profile["overall_mastery"],
        "ai_dependency": profile["ai_dependency_flag"],
        "validation": {
            "confidence": validation["confidence"],
            "warnings": validation["warnings"],
        },
        "mastery_profile": {
            "weak": profile["weak_topics"],
            "medium": profile["medium_topics"],
            "strong": profile["strong_topics"],
        },
        "topic_scores": {
            t: {
                "mastery": v["mastery_score"],
                "priority": v["priority_rank"],
                "quiz": v["quiz_score"],
                "sandbox": v["sandbox_score"],
                "forensic": v["forensic_score"],
            }
            for t, v in profile["topic_scores"].items()
        },
        "misconception_clusters": profile["misconception_clusters"],
        "error_distribution": profile["error_frequency"],
        "pipeline_steps_completed": 10,
        "ready_for_downstream": True,
        "generated_at": profile["generated_at"],
    }
    canonical["pipeline_steps_completed"] = 10
    canonical["ready_for_downstream"] = True
    canonical["generated_at"] = profile["generated_at"]
    return canonical
