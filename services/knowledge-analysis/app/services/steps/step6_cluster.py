def step6_cluster(enriched: dict) -> dict:
    clusters = {
        "AI_Dependency": [],
        "Conceptual_Gap": [],
        "Syntax_Weakness": [],
        "Strong_Performance": [],
    }

    for topic, a in enriched.items():
        issues = " ".join(a.get("issues", []))
        s = a.get("preliminary_score", 1.0)

        if "AI" in issues or "Big-Bang" in issues or "burst" in issues.lower():
            clusters["AI_Dependency"].append(topic)
        elif s < 0.5:
            clusters["Conceptual_Gap"].append(topic)
        elif "syntax" in issues.lower():
            clusters["Syntax_Weakness"].append(topic)
        else:
            clusters["Strong_Performance"].append(topic)

    return clusters
