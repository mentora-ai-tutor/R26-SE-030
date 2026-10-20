"""Unit tests for the mastery-from-reviews bridge (pure logic, no DB / no LLM).

Covers the graph-backed topic resolution, score-based rejection categorization,
the 3-source fusion, and the exact-concept gap/strength payload the LMG consumes.
The DB telemetry loaders are exercised indirectly via the aggregate dicts.
"""

from app.services.mastery_from_reviews import (
    aggregate_reviews_to_mastery,
    _categorize,
    _def_for_evidence,
    _fused_mastery,
    _quiz_score,
    _sandbox_score,
)


def _job(repo: str, review: dict) -> dict:
    return {
        "student_id": "objid",
        "status": "completed",
        "repos": [{"full_name": repo, "status": "done", "review": review}],
    }


def _loops_repo() -> dict:
    return _job(
        "student/loops-lab",
        {
            "repo": "student/loops-lab",
            "summary": "Implement for and while loops to sum integers.",
            "java_signals": {"loops_detected": 4, "arrays_used": 3},
            "errors": [
                {
                    "severity": "high",
                    "file": "SumLoop.java",
                    "why": "Loop condition uses a strict bound so the final element is never processed.",
                    "fix_hint": "Use an inclusive bound or a for-each loop.",
                },
                {
                    "severity": "medium",
                    "file": "Nested.java",
                    "why": "Nested loop recomputes the same result on every pass.",
                    "fix_hint": "Hoist invariant computation out of the loop body.",
                },
            ],
            "suggestions": ["Consider a for-each over the collection"],
        },
    )


def _recursion_repo() -> dict:
    return _job(
        "student/recursion-lab",
        {
            "repo": "student/recursion-lab",
            "summary": "Write a recursive factorial; recursion never terminates.",
            "java_signals": {"recursion_detected": 1},
            "errors": [
                {
                    "severity": "high",
                    "file": "Factorial.java",
                    "why": "Base case is never reached because the recursive call does not reduce the argument.",
                    "fix_hint": "Add a base case that stops recursion at the terminating condition.",
                }
            ],
            "suggestions": [],
        },
    )


# ----------------------------------------------------------------- topic labels
def test_def_for_evidence_resolves_quiz_and_sandbox_labels_to_exact_topics():
    assert _def_for_evidence("Loops")["topic_id"] == "CS101-LOOP"
    assert _def_for_evidence("Recursion")["topic_id"] == "CS101-REC"
    assert _def_for_evidence("Binary Search Trees")["topic_id"] == "CS201-BST"
    assert _def_for_evidence("Threads")["topic_id"] == "CS301-CONC"
    assert _def_for_evidence("Iteration Patterns")["topic_id"] == "CS101-ITER"
    assert _def_for_evidence("Nonsense Label") is None


# ------------------------------------------------------------- categorization
def test_categorize_loop_boundary_finding_stays_in_loops():
    text = (
        "Loop condition uses a strict bound so the final element is never processed. "
        "Use an inclusive bound or a for-each loop."
    )
    assert _categorize(text)["topic_id"] == "CS101-LOOP"


def test_categorize_recursion_base_case_is_not_swallowed_by_conditionals():
    text = (
        "Base case is never reached because the recursive call does not reduce the "
        "argument. Add a base case that stops recursion at the terminating condition."
    )
    assert _categorize(text)["topic_id"] == "CS101-REC"


def test_categorize_still_routes_to_review_themes():
    assert _categorize("Password is hard-coded and committed; move it to an env var.")["topic_id"] == "SE-HYGIENE"
    assert _categorize("No unit test covers the add method; add JUnit assertions.")["topic_id"] == "SE-TEST"
    assert _categorize("Two threads mutate the shared counter without synchronization.")["topic_id"] == "CS301-CONC"


# --------------------------------------------------------------- fusion math
def test_quiz_score_is_accuracy():
    assert _quiz_score({"correct": 9, "total": 10}) == 0.9
    assert _quiz_score({"correct": 0, "total": 0}) is None


def test_sandbox_score_penalises_error_density():
    green = {"compile_attempts": 8, "syntax_errors": 0, "runtime_errors": 0, "logical_errors": 0}
    red = {"compile_attempts": 8, "syntax_errors": 1, "runtime_errors": 4, "logical_errors": 0}
    assert _sandbox_score(green) == 1.0
    assert _sandbox_score(red) == 0.438
    assert _sandbox_score({"compile_attempts": 0}) is None


def test_fused_mastery_renormalises_available_weights():
    # review 70/100 (.3) + quiz .9 (.3 weighted) + sandbox .25 (.4) renormalised.
    assert _fused_mastery(70.0, 0.9, 0.25) == 58.0
    # Only-review case stays the review signal.
    assert _fused_mastery(85.0, None, None) == 85.0
    assert _fused_mastery(None, None, None) == 60.0


# ------------------------------------------------------------- no-evidence gate
def test_aggregate_returns_none_without_any_evidence():
    assert aggregate_reviews_to_mastery([], "STU-1") is None


def test_aggregate_builds_profile_from_reviews_alone():
    out = aggregate_reviews_to_mastery([_loops_repo()], "STU-1")
    assert out is not None
    assert out["data_sources"]["github"] == "available"
    assert out["data_sources"]["github_review_repos"] == "1"
    loop = next(g for g in out["mastery_profile"]["knowledge_gaps"] if g["topic_id"] == "CS101-LOOP")
    assert loop["observed_error_patterns"]["github_review"]


# ----------------------------------------------------- full review+evidence run
def test_aggregate_emits_exact_concept_gaps_from_reviews_and_telemetry():
    jobs = [_loops_repo(), _recursion_repo()]
    quiz_evidence = {
        "Loops": {"correct": 9, "total": 10, "avg_time_seconds": 21.0, "retry_count": 1},
        "Recursion": {"correct": 2, "total": 10, "avg_time_seconds": 38.0, "retry_count": 5},
    }
    sandbox_evidence = {
        "Loops": {
            "compile_attempts": 12,
            "syntax_errors": 2,
            "runtime_errors": 4,
            "logical_errors": 4,
            "passed": 2,
            "errors": ["java.lang.ArrayIndexOutOfBoundsException: Index 10 out of bounds for length 10"],
        },
        "Recursion": {
            "compile_attempts": 8,
            "syntax_errors": 1,
            "runtime_errors": 4,
            "logical_errors": 0,
            "passed": 3,
            "errors": ["java.lang.StackOverflowError"],
        },
    }

    out = aggregate_reviews_to_mastery(
        jobs, "STU-1", quiz_evidence=quiz_evidence, sandbox_evidence=sandbox_evidence
    )
    assert out is not None
    assert out["data_sources"]["github"] == "available"
    assert out["data_sources"]["github_review_repos"] == "2"
    assert out["data_sources"]["github_review_jobs"] == "2"

    gaps = {g["topic_id"]: g for g in out["mastery_profile"]["knowledge_gaps"]}

    rec = gaps["CS101-REC"]
    assert rec["gap_type"] == "FUNDAMENTAL_GAP"
    assert rec["week_area"] == "W09 - Recursion"
    assert "CS101-REC-BASE" in rec["weak_concept_ids"]
    assert "base case" in " ".join(rec["weak_concepts"]).lower()
    assert rec["observed_error_patterns"]["github_review"]
    assert any("StackOverflowError" in p for p in rec["observed_error_patterns"]["sandbox"])
    assert any("retry" in p for p in rec["observed_error_patterns"]["quizzes"])
    assert any("base case" in o.lower() for o in rec["suggested_intervention"]["learning_objectives"])

    loop = gaps["CS101-LOOP"]
    assert loop["gap_type"] == "PARTIAL_GAP"
    assert loop["week_area"] == "W02 - Control Flow"
    assert "CS101-LOOP-BOUNDARY" in loop["weak_concept_ids"]
    assert set(loop["observed_error_patterns"]["github_review"]) >= {
        "Loop condition uses a strict bound so the final element is never processed. (SumLoop.java)"
    }

    # Conditionals must NOT be a spurious gap from the loop-boundary finding.
    assert "CS101-COND" not in gaps

    # Every gap carries the additive schema fields.
    for gap in gaps.values():
        assert gap["weak_concepts"]
        assert gap["weak_concept_ids"]
        assert gap["week_area"]


def test_clean_topic_becomes_a_strength_not_a_gap():
    jobs = [_job(
        "student/clean-methods-lab",
        {
            "repo": "student/clean-methods-lab",
            "summary": "Extract helper methods for repeated blocks.",
            "java_signals": {},
            "errors": [],
            "suggestions": ["Great use of small methods"],
        },
    )]
    out = aggregate_reviews_to_mastery(jobs, "STU-2")
    assert out is not None
    topics = {g["topic_id"] for g in out["mastery_profile"]["knowledge_gaps"]}
    assert "CS101-FUNC" not in topics
    strengths = {s["topic_id"]: s for s in out["mastery_profile"]["strengths"]}
    assert "CS101-FUNC" in strengths
    assert strengths["CS101-FUNC"]["mastery_level"] in ("proficient", "advanced")