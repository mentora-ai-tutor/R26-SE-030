def step4_analyse(features: dict) -> dict:
    analysis = {}
    for topic, f in features.items():
        issues = []
        score = 1.0

        cr = f.get("correctness_rate", 1.0)
        if cr < 0.5:
            issues.append("Low quiz correctness - possible conceptual gap")
            score -= 0.25

        ler = f.get("logical_error_rate", 0.0)
        if ler > 0.4:
            issues.append("High logical error rate in sandbox")
            score -= 0.20

        ser = f.get("syntax_error_rate", 0.0)
        if ser > 0.5:
            issues.append("Recurring syntax errors - shallow familiarity")
            score -= 0.10

        burst = f.get("burst_score", 0.0)
        if burst > 0.7:
            issues.append("Keystroke burst anomaly - possible AI injection detected")
            score -= 0.25

        latency = f.get("correction_latency", 0.0)
        if latency < 3.0 and ler > 0.2:
            issues.append("Sub-human correction speed - AI-assisted fix suspected")
            score -= 0.15

        analysis[topic] = {"issues": issues, "preliminary_score": round(max(score, 0.0), 3)}
    return analysis
