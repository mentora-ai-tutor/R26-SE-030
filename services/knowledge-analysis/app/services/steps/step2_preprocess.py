from app.models.schemas import LearnerInput


def step2_preprocess(data: LearnerInput) -> dict:
    quiz_norm = {s.topic: round(s.correct / max(s.total, 1), 3) for s in data.quiz_sessions}
    sandbox_norm = {
        s.topic: {
            "error_density": round(
                (s.runtime_errors + s.syntax_errors + s.logical_errors) / max(s.compile_attempts, 1),
                3,
            ),
            "speed_ratio": round(min(s.error_correction_latency / 60.0, 1.0), 3),
            "burst_score": round(s.keystroke_burst_score, 3),
        }
        for s in data.sandbox_sessions
    }
    commit_flags = []
    if data.github_commits:
        for c in data.github_commits:
            commit_flags.append(
                {
                    "big_bang": c.is_big_bang,
                    "granularity": round(c.diff_granularity, 3),
                    "refactor_freq": round(c.refactor_frequency, 3),
                }
            )

    return {
        "quiz_scores_normalised": quiz_norm,
        "sandbox_metrics_normalised": sandbox_norm,
        "commit_flags": commit_flags,
    }
