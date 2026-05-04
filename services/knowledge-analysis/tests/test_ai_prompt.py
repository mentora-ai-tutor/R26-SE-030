from app.services.ai_prompt import build_prompt


def test_build_prompt_contains_expected_fields() -> None:
    summary = {
        "commit_count": 8,
        "avg_time_gap": 95,
        "message_quality": 0.32,
        "big_bang": True,
    }

    prompt = build_prompt(summary)

    assert "Total commits: 8" in prompt
    assert "Average time gap between commits (seconds): 95" in prompt
    assert "Commit message quality score (0.0 - 1.0): 0.32" in prompt
    assert "Big Bang development detected: True" in prompt
    assert "Return ONLY valid JSON." in prompt
    assert '"weaknesses": ["string", "string", "string"]' in prompt
    assert '"ai_dependency": "Low | Medium | High"' in prompt
