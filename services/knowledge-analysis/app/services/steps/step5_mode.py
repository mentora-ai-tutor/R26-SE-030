from app.models.schemas import LearnerInput


def step5_mode_execution(data: LearnerInput, features: dict, analysis: dict) -> dict:
    mode = "full" if (data.github_enabled and data.github_commits) else "reduced"
    enriched = {}

    for topic, a in analysis.items():
        f = features.get(topic, {})
        ea = dict(a)
        ea["mode"] = mode

        if mode == "full" and data.github_commits:
            big_bang = f.get("big_bang_ratio", 0.0)
            granularity = f.get("avg_granularity", 1.0)
            refactor = f.get("avg_refactor_freq", 0.0)

            if big_bang > 0.4:
                ea["issues"].append("Big-Bang commit pattern - incremental development absent")
                ea["preliminary_score"] = round(ea["preliminary_score"] - 0.15, 3)

            if granularity < 0.3:
                ea["issues"].append("Coarse diff granularity - AI-generated bulk code suspected")
                ea["preliminary_score"] = round(ea["preliminary_score"] - 0.10, 3)

            if refactor < 0.5:
                ea["issues"].append("Low refactoring frequency - no iterative improvement observed")
                ea["preliminary_score"] = round(ea["preliminary_score"] - 0.05, 3)

            ea["forensic_signals"] = {
                "big_bang_ratio": round(big_bang, 3),
                "diff_granularity": round(granularity, 3),
                "refactor_freq": round(refactor, 3),
            }
        else:
            ea["forensic_signals"] = None

        ea["preliminary_score"] = round(max(ea["preliminary_score"], 0.0), 3)
        enriched[topic] = ea

    return {"mode": mode, "enriched_analysis": enriched}
