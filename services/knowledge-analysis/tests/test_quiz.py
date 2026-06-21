"""Unit tests for the adaptive Java quiz — pure logic + seed bank integrity.

These intentionally avoid Mongo and the LLM: they cover the "simple -> hard" engine
and the offline fallback bank, which is exactly the part that must never regress.
"""
from datetime import datetime, timezone

from app.core.constants import QUIZ_DIFFICULTY_ORDER, QUIZ_SCHEMA_VERSION
from app.models.quiz import QuizResultRecord
from app.models.schemas import QuizPerformance
from app.services import quiz_store
from app.services.quiz_generator import build_seed_pool, load_seed_questions


# --------------------------------------------------------------------- seed bank
def test_seed_bank_loads_and_is_valid():
    seeds = load_seed_questions()
    assert seeds, "seed bank must not be empty"
    for q in seeds:
        ids = {o["id"] for o in q["options"]}
        assert len(q["options"]) >= 2
        assert q["correct_option_id"] in ids
        assert q["difficulty"] in QUIZ_DIFFICULTY_ORDER
        assert q["source"] == "seed"


def test_seed_bank_covers_every_difficulty():
    difficulties = {q["difficulty"] for q in load_seed_questions()}
    assert set(QUIZ_DIFFICULTY_ORDER).issubset(difficulties)


def test_build_seed_pool_ladders_easy_to_hard():
    pool = build_seed_pool(topics=None, types=["mcq", "predict_output"], per_difficulty=2)
    difficulties = {q["difficulty"] for q in pool}
    assert difficulties == set(QUIZ_DIFFICULTY_ORDER)


def test_build_seed_pool_respects_only_difficulty():
    pool = build_seed_pool(
        topics=None, types=["mcq", "predict_output"], per_difficulty=5, only_difficulty="hard"
    )
    assert pool and all(q["difficulty"] == "hard" for q in pool)


# ----------------------------------------------------------------- adaptive rungs
def test_climb_caps_at_hard():
    assert quiz_store.climb("easy") == "medium"
    assert quiz_store.climb("medium") == "hard"
    assert quiz_store.climb("hard") == "hard"


def test_step_down_floors_at_easy():
    assert quiz_store.step_down("hard") == "medium"
    assert quiz_store.step_down("medium") == "easy"
    assert quiz_store.step_down("easy") == "easy"


def _pool():
    return [
        {"qid": "e1", "difficulty": "easy", "topic": "Loops"},
        {"qid": "m1", "difficulty": "medium", "topic": "OOP"},
        {"qid": "h1", "difficulty": "hard", "topic": "Recursion"},
    ]


def test_select_next_prefers_requested_rung():
    assert quiz_store.select_next(_pool(), [], "medium")["qid"] == "m1"
    assert quiz_store.select_next(_pool(), [], "hard")["qid"] == "h1"


def test_select_next_excludes_already_asked():
    nxt = quiz_store.select_next(_pool(), ["e1", "m1"], "easy")
    assert nxt["qid"] == "h1"  # only hard remains; falls through search order


def test_select_next_returns_none_when_exhausted():
    assert quiz_store.select_next(_pool(), ["e1", "m1", "h1"], "easy") is None


def test_select_next_falls_back_when_rung_empty():
    # Request medium but only easy/hard remain -> search order tries harder first.
    pool = [{"qid": "e1", "difficulty": "easy", "topic": "A"},
            {"qid": "h1", "difficulty": "hard", "topic": "B"}]
    assert quiz_store.select_next(pool, [], "medium")["qid"] == "h1"


# ----------------------------------------------------------------------- scoring
def test_grade_matches_correct_option():
    q = {"correct_option_id": "C"}
    assert quiz_store.grade(q, "C") is True
    assert quiz_store.grade(q, "A") is False


def test_summarize_emits_quizperformance_shape():
    answers = [
        {"qid": "1", "topic": "Loops", "correct": True, "time_seconds": 10},
        {"qid": "2", "topic": "Loops", "correct": False, "time_seconds": 20},
        {"qid": "3", "topic": "OOP", "correct": True, "time_seconds": 30},
    ]
    summary = quiz_store.summarize(answers)
    assert summary["total"] == 3
    assert summary["correct"] == 2
    assert summary["score_percent"] == round(2 / 3 * 100, 1)
    # Each per-topic entry must validate against the canonical QuizPerformance model
    # so it can be fed straight into POST /analyze.
    for perf in summary["quiz_performance"]:
        QuizPerformance.model_validate(perf)
    loops = next(p for p in summary["quiz_performance"] if p["topic"] == "Loops")
    assert loops["correct"] == 1 and loops["total"] == 2
    assert loops["avg_time_seconds"] == 15.0


def _answers():
    return [
        {"qid": "1", "topic": "Loops", "difficulty": "easy", "type": "mcq",
         "correct": True, "chosen_option_id": "A", "time_seconds": 10},
        {"qid": "2", "topic": "Recursion", "difficulty": "medium", "type": "predict_output",
         "correct": False, "chosen_option_id": "B", "time_seconds": 22},
    ]


def test_build_result_record_matches_cross_team_contract():
    session_doc = {
        "_id": "abc123", "student_id": "internal-9", "public_student_id": "IT22201232",
        "mode": "sandbox", "job_id": None,
    }
    answers = _answers()
    summary = quiz_store.summarize(answers)
    record = quiz_store._build_result_record(
        session_doc, answers, summary, "hard", datetime(2026, 6, 7, tzinfo=timezone.utc)
    )

    assert record["session_id"] == "abc123"
    assert record["public_student_id"] == "IT22201232"
    assert record["schema_version"] == QUIZ_SCHEMA_VERSION
    assert record["score_percent"] == 50.0
    assert record["difficulty_reached"] == "hard"
    assert len(record["questions"]) == 2
    # topic_performance must be QuizPerformance-shaped (feeds POST /analyze)
    for perf in record["topic_performance"]:
        QuizPerformance.model_validate(perf)

    # The whole record must satisfy the published contract once serialized for the API.
    QuizResultRecord.model_validate(quiz_store._serialize_result(record))


def test_highest_difficulty_picks_hardest_answered():
    answers = [{"difficulty": "easy"}, {"difficulty": "hard"}, {"difficulty": "medium"}]
    assert quiz_store._highest_difficulty(answers) == "hard"
    assert quiz_store._highest_difficulty([{"difficulty": "easy"}]) == "easy"
    assert quiz_store._highest_difficulty([]) == "easy"  # safe default


def test_student_query_keys_on_public_id_only():
    q = quiz_store._student_query("IT22201232")
    assert q == {"public_student_id": "IT22201232"}
    assert "student_id" not in q  # internal id not exposed via the read API


def test_result_from_session_fallback_is_contract_shaped():
    session = {
        "_id": "sess9", "student_id": "internal-1", "public_student_id": "IT22201232",
        "mode": "sandbox", "job_id": None, "status": "completed",
        "answers": _answers(),
        "results": quiz_store.summarize(_answers()),
        "completed_at": datetime(2026, 6, 7, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 6, 7, tzinfo=timezone.utc),
    }
    view = quiz_store._result_from_session(session)
    assert view["recovered_from"] == "quiz_sessions"
    assert view["difficulty_reached"] == "medium"  # hardest answered in _answers()
    QuizResultRecord.model_validate(view)


def test_serialize_result_isoformats_dates_and_renames_id():
    doc = {
        "_id": "objid", "session_id": "s1", "completed_at": datetime(2026, 6, 7, tzinfo=timezone.utc),
        "created_at": datetime(2026, 6, 7, tzinfo=timezone.utc),
    }
    out = quiz_store._serialize_result(doc)
    assert "_id" not in out and out["result_id"] == "objid"
    assert isinstance(out["completed_at"], str) and out["completed_at"].startswith("2026-06-07")


def test_strip_question_withholds_answer_key():
    q = {
        "qid": "x", "topic": "Loops", "difficulty": "easy", "type": "mcq",
        "question": "?", "code_snippet": None, "options": [{"id": "A", "text": "a"}],
        "correct_option_id": "A", "explanation": "secret", "concept_tested": "c",
    }
    stripped = quiz_store.strip_question(q)
    assert "correct_option_id" not in stripped
    assert "explanation" not in stripped
    assert stripped["qid"] == "x" and stripped["options"] == q["options"]
