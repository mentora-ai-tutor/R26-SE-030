"""Pure quiz helpers: generation, adaptive rungs, grading, summarize, client views."""
from __future__ import annotations

from app.services.quiz_engine import generate_quiz
from app.services.quiz_store import (
    climb,
    grade,
    select_next,
    step_down,
    strip_question,
    summarize,
)


def test_generate_quiz_maps_mastery_to_difficulty_and_level() -> None:
    assert generate_quiz("Loops", 0.9)["level"] == "easy"
    assert generate_quiz("Loops", 0.9)["difficulty"] == 0.1  # 1 - 0.9, clamped
    assert generate_quiz("Loops", 0.1)["level"] == "hard"

    mid = generate_quiz("Loops", 0.5)
    assert mid["difficulty"] == 0.5
    assert mid["level"] == "medium"
    assert mid["topic"] == "Loops"
    assert mid["irt_theta"] == 0.0  # mastery 0.5 -> 0
    assert mid["question"] and mid["expected_key"]

    # unknown topic falls back to the Loops bank deterministically
    assert generate_quiz("Nonsense")["topic"] == "Nonsense"


def test_adaptive_helpers_grade_and_serialize() -> None:
    assert climb("easy") == "medium"
    assert climb("hard") == "hard"  # capped
    assert step_down("medium") == "easy"
    assert step_down("easy") == "easy"  # floored

    q = {
        "qid": "q1",
        "topic": "Loops",
        "difficulty": "easy",
        "type": "mcq",
        "question": "What does a for loop do?",
        "code_snippet": None,
        "options": [{"id": "A", "text": "loop"}, {"id": "B", "text": "stop"}],
        "correct_option_id": "A",
        "explanation": "it loops",
        "concept_tested": "for",
    }
    assert grade(q, "A") is True
    assert grade(q, "B") is False

    view = strip_question(q)
    assert view["qid"] == "q1"
    assert "correct_option_id" not in view
    assert "explanation" not in view
    assert strip_question(None) is None

    summary = summarize(
        [
            {"topic": "Loops", "correct": True, "time_seconds": 10.0},
            {"topic": "Loops", "correct": False, "time_seconds": 20.0},
        ]
    )
    assert summary["score_percent"] == 50.0
    assert summary["correct"] == 1 and summary["total"] == 2
    perf = summary["quiz_performance"][0]
    assert perf == {"topic": "Loops", "correct": 1, "total": 2, "avg_time_seconds": 15.0, "retry_count": 0}

    pool = [dict(q), {"qid": "q2", "difficulty": "medium", "topic": "OOP"}]
    picked = select_next(pool, ["q1"], "easy")
    assert picked["qid"] == "q2"  # only unasked question remains
    assert select_next(pool, ["q1", "q2"], "easy") is None