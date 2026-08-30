"""Rich diagnostic / forensic report — the human-facing companion to the canonical contract.

This is a *pure reshaping* of data the 10-step pipeline already produced (`LearnerInput`
+ the canonical `final_output`). It adds the breakdown sections that the canonical contract
deliberately omits — `github_forensics`, `sandbox_telemetry`, `adaptive_quiz_results` — for
dashboards and instructor review, while reusing the canonical `knowledge_gaps` / `strengths`
verbatim so the two never disagree.

It does NOT recompute mastery, does NOT call the LLM, and does NOT touch any pipeline step.
Honesty constraints (see ARCHITECTURE.md §8):
  * GitHub metrics are labelled partial — KAA only sees the recent commits fetched for context,
    so `commits_sampled` is a lower bound, not a repo-lifetime `total_commits`.
  * No file-level AI-probability is fabricated; authorship risk is reported only as the
    topic-level signal the pipeline actually derives.
"""
from __future__ import annotations

from typing import Any

from app.models.schemas import GitHubCommit, LearnerInput, QuizPerformance, SandboxSession

DIAGNOSTIC_REPORT_SCHEMA_VERSION = "kaa-forensic-report-v1.0"
_BURST_THRESHOLD = 0.7


def build_diagnostic_report(data: LearnerInput, final_output: dict[str, Any]) -> dict[str, Any]:
    """Assemble the rich report from raw learner signals + the canonical pipeline output."""
    data_sources = final_output.get("data_sources", {})
    raw = final_output.get("raw_analysis_payload", {})
    ai_topics = (raw.get("misconception_clusters") or {}).get("AI_Dependency", [])

    return {
        "schema_version": DIAGNOSTIC_REPORT_SCHEMA_VERSION,
        "student_id": final_output.get("student_id", data.student_id),
        "session_id": final_output.get("session_id"),
        "analysis_timestamp": final_output.get("analysis_timestamp"),
        "mode": raw.get("mode"),
        "data_sources": data_sources,
        "github_forensics": _github_forensics(data, raw, ai_topics),
        "sandbox_telemetry": _sandbox_telemetry(data.sandbox_sessions, raw),
        "adaptive_quiz_results": _quiz_results(data.quiz_sessions),
        "synthesized_mastery_profile": {
            "overall_mastery_score": final_output.get("overall_mastery_score"),
            "knowledge_gaps": final_output.get("knowledge_gaps", []),
            "strengths": final_output.get("strengths", []),
        },
        "recommendations": final_output.get("recommendations", {}),
    }


def _pct(part: float, whole: float) -> float:
    return round((part / whole) * 100, 1) if whole else 0.0


def _github_forensics(
    data: LearnerInput,
    raw: dict[str, Any],
    ai_topics: list[str],
) -> dict[str, Any]:
    commits = data.github_commits or []
    if not data.github_enabled or not commits:
        return {
            "status": "NO_GITHUB_ACCOUNT_LINKED",
            "message": "No GitHub commits available. Forensics omitted; diagnosis uses sandbox + quiz signals only.",
        }

    n = len(commits)
    big_bang = sum(1 for c in commits if c.is_big_bang)
    incremental = sum(1 for c in commits if not c.is_big_bang and c.diff_granularity >= 0.5)
    erratic = n - big_bang - incremental
    avg_refactor = sum(c.refactor_frequency for c in commits) / n
    avg_granularity = sum(c.diff_granularity for c in commits) / n

    small = sum(1 for c in commits if (c.lines_added + c.lines_removed) < 20)
    large = sum(1 for c in commits if (c.lines_added + c.lines_removed) > 100)
    medium = n - small - large

    return {
        "status": "AVAILABLE",
        # Honest scope: KAA only sees the recent commits fetched for review context.
        "commits_sampled": n,
        "is_partial_history": True,
        "history_note": (
            "Metrics derive from the most recent commits fetched for review context "
            "(~10 per repo), not the repository's full lifetime. commits_sampled is a "
            "lower bound; a deeper paginated collector is required for true total_commits."
        ),
        "commit_pattern_classification": _classify_pattern(big_bang, incremental, n),
        "commit_pattern_breakdown": {
            "incremental_percent": _pct(incremental, n),
            "big_bang_percent": _pct(big_bang, n),
            "erratic_percent": _pct(erratic, n),
        },
        "commit_size_analysis": {
            "small_commits_percent": _pct(small, n),
            "medium_commits_percent": _pct(medium, n),
            "large_commits_percent": _pct(large, n),
        },
        "refactoring_velocity_avg": round(avg_refactor, 3),
        "avg_diff_granularity": round(avg_granularity, 3),
        "authorship_risk": {
            "flag": bool(ai_topics),
            "topics": ai_topics,
            "basis": "big-bang commits + low diff granularity correlated with weak sandbox/quiz signal",
            "note": "Topic-level signal only. KAA does not perform file-level AI-probability detection.",
        },
    }


def _classify_pattern(big_bang: int, incremental: int, n: int) -> str:
    if _pct(big_bang, n) >= 50:
        return "BIG_BANG"
    if _pct(incremental, n) >= 60:
        return "INCREMENTAL"
    return "MIXED"


def _sandbox_telemetry(
    sessions: list[SandboxSession],
    raw: dict[str, Any],
) -> dict[str, Any]:
    if not sessions:
        return {"status": "NO_SANDBOX_DATA", "total_sessions": 0, "topic_performance": []}

    error_freq = raw.get("error_frequency", {})
    success = [_session_success(s) for s in sessions]
    bursts = sum(1 for s in sessions if s.keystroke_burst_score >= _BURST_THRESHOLD)

    return {
        "status": "AVAILABLE",
        "total_sessions": len(sessions),
        "avg_success_ratio": round(sum(success) / len(success), 3),
        "avg_error_correction_latency_seconds": round(
            sum(s.error_correction_latency for s in sessions) / len(sessions), 2
        ),
        "keystroke_burst_detections": bursts,
        "topic_performance": [
            {
                "topic": s.topic,
                "compile_attempts": s.compile_attempts,
                "success_ratio": round(_session_success(s), 3),
                "time_to_success_seconds": round(s.time_to_success_seconds, 1),
                "error_correction_latency_seconds": round(s.error_correction_latency, 2),
                "error_patterns": _error_patterns(s),
                "notes": _sandbox_notes(s),
            }
            for s in sessions
        ],
    }


def _session_success(s: SandboxSession) -> float:
    return 1 - min((s.runtime_errors + s.logical_errors) / max(s.compile_attempts, 1), 1)


def _error_patterns(s: SandboxSession) -> list[str]:
    patterns = []
    if s.syntax_errors:
        patterns.append("syntax errors")
    if s.logical_errors:
        patterns.append("logical errors")
    if s.runtime_errors:
        patterns.append("runtime errors")
    return patterns


def _sandbox_notes(s: SandboxSession) -> str | None:
    # Fast completion + high keystroke burst is the copy-paste / low-authorship signal.
    if s.keystroke_burst_score >= _BURST_THRESHOLD and s.error_correction_latency < 5:
        return "High keystroke burst with very fast error correction — possible paste-in, verify authorship."
    return None


def _quiz_results(sessions: list[QuizPerformance]) -> dict[str, Any]:
    if not sessions:
        return {"status": "NO_QUIZ_DATA", "total_quizzes_taken": 0, "topic_scores": []}

    scores = [_pct(s.correct, s.total) for s in sessions]
    return {
        "status": "AVAILABLE",
        "total_quizzes_taken": len(sessions),
        "avg_score": round(sum(scores) / len(scores), 1),
        "topic_scores": [
            {
                "topic": s.topic,
                "score": _pct(s.correct, s.total),
                "questions_asked": s.total,
                "avg_time_seconds": round(s.avg_time_seconds, 1),
                "retry_count": s.retry_count,
            }
            for s in sessions
        ],
    }
