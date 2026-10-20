"""Unit tests for sandbox challenge assembly — seed integrity, difficulty ordering,
and the client view that must hide reference solutions."""
from app.services import sandbox_challenge_generator as gen


def test_seed_challenges_load_and_are_complete():
    seeds = gen.load_seed_challenges()
    assert seeds, "seed challenges must not be empty"
    for c in seeds:
        assert c["title"] and c["prompt"] and c["starter_code"]
        assert c["expected_output"] not in (None, "")
        assert c["difficulty"] in gen.DIFFICULTY_ORDER
        assert c["source"] == "seed"


def test_by_difficulty_orders_simple_to_hard():
    mixed = [
        {"difficulty": "hard"},
        {"difficulty": "easy"},
        {"difficulty": "medium"},
    ]
    ordered = [c["difficulty"] for c in gen._by_difficulty(mixed)]
    assert ordered == ["easy", "medium", "hard"]


def test_client_view_hides_reference_solution():
    full = {
        "id": "x", "title": "t", "topic": "Loops", "difficulty": "easy",
        "prompt": "p", "starter_code": "code", "reference_solution": "SECRET",
        "expected_output": "30", "stdin": None, "source": "generated",
    }
    view = gen.client_view(full)
    assert "reference_solution" not in view
    assert view["expected_output"] == "30"  # expected output stays (UI shows it)
    assert view["starter_code"] == "code" and view["id"] == "x"
