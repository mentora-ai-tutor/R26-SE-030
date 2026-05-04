from app.models.schemas import LearnerInput


def step3_extract_features(data: LearnerInput, preprocessed: dict) -> dict:
    del preprocessed
    features = {}

    for s in data.quiz_sessions:
        t = s.topic
        features.setdefault(t, {})
        features[t]["correctness_rate"] = round(s.correct / max(s.total, 1), 3)
        features[t]["avg_time_per_q"] = round(s.avg_time_seconds, 1)
        features[t]["retry_rate"] = round(s.retry_count / max(s.total, 1), 3)

    for s in data.sandbox_sessions:
        t = s.topic
        features.setdefault(t, {})
        features[t]["syntax_error_rate"] = round(s.syntax_errors / max(s.compile_attempts, 1), 3)
        features[t]["logical_error_rate"] = round(s.logical_errors / max(s.compile_attempts, 1), 3)
        features[t]["runtime_error_rate"] = round(s.runtime_errors / max(s.compile_attempts, 1), 3)
        features[t]["compile_ratio"] = round(s.compile_attempts / max(s.lines_of_code / 10, 1), 3)
        features[t]["correction_latency"] = round(s.error_correction_latency, 1)
        features[t]["burst_score"] = round(s.keystroke_burst_score, 3)

    if data.github_commits:
        big_bang_count = sum(1 for c in data.github_commits if c.is_big_bang)
        avg_granularity = sum(c.diff_granularity for c in data.github_commits) / max(len(data.github_commits), 1)
        avg_refactor = sum(c.refactor_frequency for c in data.github_commits) / max(len(data.github_commits), 1)
        for t in features:
            features[t]["big_bang_ratio"] = round(big_bang_count / max(len(data.github_commits), 1), 3)
            features[t]["avg_granularity"] = round(avg_granularity, 3)
            features[t]["avg_refactor_freq"] = round(avg_refactor, 3)

    return features
