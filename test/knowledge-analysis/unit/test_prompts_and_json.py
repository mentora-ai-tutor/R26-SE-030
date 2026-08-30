"""Pure prompt-building + LLM JSON parsing/fallback units (no DB, no LLM)."""
from __future__ import annotations

import json

import pytest

from app.services.ai_prompt import build_prompt as build_behavior_prompt
from app.services.prompt_builder import PromptBuilder


def test_behavior_prompt_embeds_metrics_and_strict_rules() -> None:
    summary = {
        "commit_count": 42,
        "avg_time_gap": 120,
        "message_quality": 0.3,
        "big_bang": True,
    }
    prompt = build_behavior_prompt(summary)

    assert "42" in prompt
    assert "Big Bang development detected: True" in prompt
    assert "You MUST follow the output format strictly" in prompt
    assert "Return ONLY valid JSON" in prompt
    assert '"ai_dependency"' in prompt


def test_prompt_builder_time_gap_and_metrics_formatting() -> None:
    builder = PromptBuilder()

    assert builder._format_time_gap(0) == "< 1 second"
    assert builder._format_time_gap(86400) == "1d"
    assert builder._format_time_gap(3661) == "1h 1m"
    assert builder._format_time_gap(59) == "< 1m"

    metrics = builder._format_metrics(
        {"commit_count": 10, "message_quality": 0.6, "big_bang_detected": True}
    )
    assert "Total commits: 10" in metrics
    assert "Big bang pattern detected: True" in metrics
    assert "Total additions: 0 lines" in metrics

    full = builder.build_prompt(
        {"commit_count": 1, "message_quality": 0.4, "big_bang_detected": False}
    )
    assert "STUDENT CODING BEHAVIOR METRICS" in full
    assert "REQUIRED JSON OUTPUT FORMAT" in full
    assert '  "ai_dependency": "Low | Medium | High"' in full


@pytest.fixture
def sample_response() -> str:
    payload = {
        "weaknesses": ["poor iteration habits", "no test discipline"],
        "ai_dependency": "Medium",
        "reasoning": "Frequent big-bang commits suggest assisted coding.",
        "recommendations": ["commit incrementally", "write tests first"],
    }
    return json.dumps(payload)


def test_json_extraction_strips_fences_and_prose(sample_response: str) -> None:
    text = "Here is the analysis:\n```json\n" + sample_response + "\n```"
    cleaned = PromptBuilder.extract_json_from_response(text)
    assert json.loads(cleaned)["ai_dependency"] == "Medium"

    prose = "preamble " + sample_response + " trailing"
    assert json.loads(PromptBuilder.extract_json_from_response(prose))["reasoning"]

    with pytest.raises(ValueError):
        PromptBuilder.extract_json_from_response("no json here at all")

    assert PromptBuilder.validate_analysis_response(sample_response) is True


def test_parse_analysis_response_validates_and_falls_back(sample_response: str) -> None:
    parsed = PromptBuilder.parse_analysis_response(sample_response)
    assert parsed["ai_dependency"] == "Medium"
    assert isinstance(parsed["weaknesses"], list)

    missing = json.dumps({"weaknesses": []})
    with pytest.raises(ValueError, match="Missing required fields"):
        PromptBuilder.parse_analysis_response(missing)

    bad_level = json.dumps(
        {
            "weaknesses": [],
            "ai_dependency": "EXTREME",
            "reasoning": "x",
            "recommendations": [],
        }
    )
    with pytest.raises(ValueError, match="ai_dependency"):
        PromptBuilder.parse_analysis_response(bad_level)

    with pytest.raises(ValueError):
        PromptBuilder.parse_analysis_response("not json")

    safe = PromptBuilder().build_safe_response(
        {"weaknesses": ["w"], "ai_dependency": "low", "reasoning": "r", "recommendations": ["r1"]}
    )
    assert safe["ai_dependency"] == "Low"  # normalized/capitalized