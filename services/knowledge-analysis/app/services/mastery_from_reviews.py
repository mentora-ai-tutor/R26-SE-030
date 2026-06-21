"""Bridge: turn a student's GitHub repo reviews into a canonical mastery profile.

Forensics repo reviews are stored in ``repo_review_jobs`` (per-repo LLM findings:
severity + why + fix_hint + suggestions + summary). Nothing previously joined that
data to ``mastery_profiles``, so the Mastery page and Career card stayed empty for
students who only ran reviews. This module aggregates the latest review per repo into
the exact ``CanonicalMasteryOutput`` contract produced by the 10-step pipeline, so the
saved document is indistinguishable (shape-wise) from an ``/analyze`` result.

The topic mapping is keyword-heuristic by necessity: repo reviews are file-level Java
findings, not topic-tagged, so each finding is bucketed into a Java/SE topic by matching
its text. Scores are derived from finding density (severity-weighted issues per repo).
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Optional

from app.core.constants import MASTERY_PROFILE_SCHEMA_VERSION, TOPIC_CATALOG
from app.db.database import get_database
from app.models.schemas import CanonicalMasteryOutput
from app.services.mastery_profile_store import save_mastery_profile

logger = logging.getLogger(__name__)

SEVERITY_WEIGHT = {"high": 3, "medium": 2, "low": 1}

# Score tuning. Repo-review findings are NEGATIVE signals (problems), and the absence of
# findings is only weak-positive evidence — you cannot prove "advanced" mastery purely
# from "nothing was flagged". So a topic the student demonstrably worked in starts at a
# proficient BASE, earns a small bonus for clean usage across MANY repos (breadth), and
# is penalised by finding density (severity-weighted issues per repo touching the topic).
#   mastery = clamp(BASE + breadth_bonus - density * DENSITY_PENALTY, FLOOR, CEILING)
BASE_MASTERY = 80.0
DENSITY_PENALTY = 6.0
BREADTH_BONUS_PER_REPO = 2.0
BREADTH_BONUS_MAX = 10.0
MASTERY_FLOOR = 25.0
MASTERY_CEILING = 95.0
# At/above this mastery a topic the student demonstrably worked in counts as a strength;
# below it (with at least one finding) it is a knowledge gap.
GAP_THRESHOLD = 72.0
# A finding's text is "substantive" (worth showing as evidence) when it is specific
# enough — short generic strings like "The code has an error." are low-signal review noise.
SUBSTANTIVE_WHY_MIN_LEN = 30


def _catalog(name: str) -> dict[str, Any]:
    return TOPIC_CATALOG.get(name, {})


# Topic definitions used by the bridge. Each entry carries the regex patterns that route
# a finding/summary into the topic, plus the canonical metadata (topic_id, subskills,
# prerequisites). Where a topic already exists in TOPIC_CATALOG we reuse its metadata so
# topic_ids/subskill_ids stay consistent with the rest of the system; new SE-review
# themes define their own. Order matters: the FIRST matching topic wins, so list the
# most specific themes before the general ones.
def _build_topic_defs() -> list[dict[str, Any]]:
    defs: list[dict[str, Any]] = []

    def add(topic: str, topic_id: str, patterns: list[str], *, catalog_name: str | None = None,
            prerequisite_topics: list[str] | None = None, related_topics: list[str] | None = None,
            subskills: list[dict[str, str]] | None = None) -> None:
        meta = _catalog(catalog_name) if catalog_name else {}
        defs.append(
            {
                "topic": topic,
                "topic_id": meta.get("topic_id", topic_id),
                "patterns": [re.compile(p, re.IGNORECASE) for p in patterns],
                "prerequisite_topics": meta.get("prerequisite_topics", prerequisite_topics or []),
                "related_topics": meta.get("related_topics", related_topics or []),
                "subskills": meta.get("subskills", subskills or []),
            }
        )

    add(
        "Concurrency & Threads", "CS301-CONC",
        [r"\bthread", r"synchron", r"concurren", r"race condition", r"deadlock",
         r"\bvolatile\b", r"executor", r"thread[- ]safe", r"\block(ing)?\b", r"\batomic\b", r"\basync"],
        prerequisite_topics=["OOP", "Methods"],
        related_topics=["Exception Handling", "Performance"],
        subskills=[
            {"subskill": "thread safety", "subskill_id": "CS301-CONC-SAFETY",
             "focus": "Guard shared mutable state with synchronization or immutability.",
             "misconception": "assumes shared state is safe without synchronization"},
            {"subskill": "coordination primitives", "subskill_id": "CS301-CONC-COORD",
             "focus": "Practice locks, executors, and atomic operations on small examples.",
             "misconception": "uses raw threads without understanding coordination"},
        ],
    )
    add(
        "Exception Handling", "CS102-EXC",
        [r"exception", r"\btry\b", r"\bcatch\b", r"\bfinally\b", r"\bthrow", r"null ?pointer",
         r"\bnpe\b", r"error handling", r"handle (the )?error", r"swallow", r"stack trace"],
        catalog_name="Exception Handling",
    )
    add(
        "File I/O & Resources", "CS102-FILE",
        # Specific I/O/resource patterns only — a bare "file" matches unrelated findings
        # like ".env file committed" (repo hygiene), so it is intentionally excluded.
        [r"try-with-resources", r"did not close", r"unclosed", r"resource leak",
         r"file (read|writ|i/?o)", r"read\w* .*file", r"writ\w* .*file", r"file(input|output|reader|writer)",
         r"\bstream\b", r"\bscanner\b", r"\bflush\b", r"close\w* (the )?(resource|stream|connection|file)",
         r"open\w* (resource|stream|connection|file)"],
        catalog_name="File I/O",
    )
    add(
        "Project Hygiene & Security", "SE-HYGIENE",
        [r"node_modules", r"\.gitignore", r"\.env\b", r"\bsecret", r"credential", r"api[_ ]?key",
         r"\bpassword", r"committed to (the )?repo", r"should not be committed", r"hard[- ]?coded secret",
         r"build artifact", r"\.class\b", r"large file", r"sensitive (data|information)", r"exposed"],
        prerequisite_topics=["Version Control"],
        related_topics=["Code Style & Readability", "Security"],
        subskills=[
            {"subskill": "secret management", "subskill_id": "SE-HYGIENE-SECRET",
             "focus": "Keep secrets out of source control; use env vars and ignore files.",
             "misconception": "commits credentials or .env files to the repository"},
            {"subskill": "repository hygiene", "subskill_id": "SE-HYGIENE-REPO",
             "focus": "Ignore dependencies and build artifacts via .gitignore.",
             "misconception": "commits node_modules/build output instead of ignoring them"},
        ],
    )
    add(
        "Testing & Verification", "SE-TEST",
        [r"\btest", r"junit", r"\bassert", r"unit test", r"coverage", r"\bmock"],
        prerequisite_topics=["OOP"],
        related_topics=["Debugging"],
        subskills=[
            {"subskill": "test coverage", "subskill_id": "SE-TEST-COVER",
             "focus": "Add unit tests for core paths and edge cases.",
             "misconception": "treats manual runs as sufficient verification"},
            {"subskill": "assertion design", "subskill_id": "SE-TEST-ASSERT",
             "focus": "Write focused assertions that pin down expected behaviour.",
             "misconception": "writes tests without meaningful assertions"},
        ],
    )
    add(
        "Input Validation & Robustness", "SE-VALID",
        [r"validat", r"sanitiz", r"bounds? check", r"check for null", r"edge case",
         r"boundary", r"guard clause", r"user input", r"parse error", r"defensive"],
        prerequisite_topics=["Conditionals"],
        related_topics=["Exception Handling"],
        subskills=[
            {"subskill": "input validation", "subskill_id": "SE-VALID-INPUT",
             "focus": "Validate and reject bad input before using it.",
             "misconception": "trusts external input without checks"},
            {"subskill": "edge-case handling", "subskill_id": "SE-VALID-EDGE",
             "focus": "Enumerate boundary and empty cases explicitly.",
             "misconception": "handles only the happy path"},
        ],
    )
    add(
        "Collections & Data Structures", "CS201-DS",
        [r"\blist\b", r"arraylist", r"hashmap", r"\bmap\b", r"\bset\b", r"collection",
         r"\bgeneric", r"iterator", r"data structure", r"linkedlist", r"\bqueue\b", r"\bstack\b"],
        catalog_name="Data Structures",
    )
    add(
        "Algorithms & Complexity", "CS201-ALG",
        [r"algorithm", r"complexity", r"performance", r"time complexity", r"inefficient",
         r"optimi[sz]e", r"o\(n", r"expensive", r"\bsort", r"\bsearch"],
        catalog_name="Algorithms",
    )
    add(
        "Interfaces & Abstraction", "CS201-IFACE",
        [r"interface", r"\bimplement", r"abstraction", r"abstract method", r"\bcontract\b", r"decoupl"],
        prerequisite_topics=["OOP"],
        related_topics=["OOP", "Design Patterns"],
        subskills=[
            {"subskill": "interface design", "subskill_id": "CS201-IFACE-DESIGN",
             "focus": "Define small, cohesive interfaces that capture one role.",
             "misconception": "creates interfaces without a clear single responsibility"},
            {"subskill": "programming to abstractions", "subskill_id": "CS201-IFACE-ABS",
             "focus": "Depend on interfaces rather than concrete classes.",
             "misconception": "couples callers to concrete implementations"},
        ],
    )
    add(
        "OOP & Class Design", "CS201-OOP",
        [r"\bclass design", r"encapsulat", r"\bgetter", r"\bsetter", r"constructor",
         r"inheritance", r"\boverride", r"polymorph", r"abstract class", r"single responsibility",
         r"coupling", r"cohesion", r"object-oriented", r"access modifier", r"instance variable",
         r"\bprivate field", r"should be private"],
        catalog_name="OOP",
    )
    add(
        "API & Architecture Design", "SE-ARCH",
        [r"architecture", r"design pattern", r"\bmodule", r"layering", r"separation of concerns",
         r"dependency injection", r"tight coupling", r"\bendpoint", r"rest api", r"more informative",
         r"more endpoints", r"scalab", r"maintainab", r"\bstructure\b"],
        prerequisite_topics=["OOP", "Interfaces & Abstraction"],
        related_topics=["OOP", "Design Patterns"],
        subskills=[
            {"subskill": "separation of concerns", "subskill_id": "SE-ARCH-SOC",
             "focus": "Split responsibilities across cohesive components.",
             "misconception": "mixes unrelated concerns in one class"},
            {"subskill": "dependency management", "subskill_id": "SE-ARCH-DEP",
             "focus": "Reduce coupling by depending on abstractions.",
             "misconception": "hard-wires dependencies between layers"},
        ],
    )
    add(
        "Code Style & Readability", "SE-STYLE",
        [r"naming", r"variable name", r"convention", r"readab", r"magic number", r"\bcomment",
         r"hard[- ]coded", r"formatting", r"descriptive", r"indentation", r"code style",
         r"method name", r"\btypo", r"unused"],
        prerequisite_topics=["Basic Java Syntax"],
        related_topics=["Maintainability"],
        subskills=[
            {"subskill": "naming and conventions", "subskill_id": "SE-STYLE-NAME",
             "focus": "Use descriptive names and consistent conventions.",
             "misconception": "uses unclear or inconsistent names"},
            {"subskill": "readable structure", "subskill_id": "SE-STYLE-READ",
             "focus": "Keep methods short and avoid magic numbers.",
             "misconception": "writes long methods with unexplained constants"},
        ],
    )
    add(
        "General Code Quality", "CS-GEN",
        [r".*"],  # fallback catch-all
        prerequisite_topics=["Basic Java Syntax"],
        related_topics=[],
        subskills=[
            {"subskill": "core concept application", "subskill_id": "CS-GEN-CORE",
             "focus": "Review the flagged concept with small traceable examples.",
             "misconception": "cannot reliably apply the concept independently"},
        ],
    )
    return defs


TOPIC_DEFS = _build_topic_defs()
_FALLBACK_DEF = TOPIC_DEFS[-1]


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _categorize(text: str) -> dict[str, Any]:
    """Return the first topic def whose pattern matches the text (fallback = General)."""
    if text:
        for topic_def in TOPIC_DEFS:
            if topic_def is _FALLBACK_DEF:
                continue
            if any(pattern.search(text) for pattern in topic_def["patterns"]):
                return topic_def
    return _FALLBACK_DEF


def _latest_review_per_repo(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Dedupe to the most recent completed review per repo full_name.

    Students re-review the same repos many times; counting every job would inflate
    finding density several-fold. ``jobs`` is expected newest-first.
    """
    latest: dict[str, dict[str, Any]] = {}
    for job in jobs:
        for repo in job.get("repos", []) or []:
            full_name = repo.get("full_name")
            if not full_name or repo.get("status") != "done" or not repo.get("review"):
                continue
            if full_name not in latest:
                latest[full_name] = repo["review"]
    return list(latest.values())


def _pct(value: float) -> float:
    return round(max(0.0, min(float(value), 100.0)), 1)


def _is_substantive(why: str) -> bool:
    """Whether a finding's text is specific enough to show as evidence.

    Filters out short, generic review noise (e.g. "The code has an error.") while keeping
    detailed findings. A backtick usually marks a specific code reference, so treat those
    as substantive regardless of length.
    """
    text = (why or "").strip()
    if "`" in text:
        return True
    return len(text) >= SUBSTANTIVE_WHY_MIN_LEN


def _gap_type(mastery: float) -> str:
    if mastery < 50:
        return "FUNDAMENTAL_GAP"
    if mastery < 70:
        return "PARTIAL_GAP"
    return "SURFACE_GAP"


def aggregate_reviews_to_mastery(
    jobs: list[dict[str, Any]],
    public_student_id: str,
    session_id: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Build a canonical mastery payload from a student's repo review jobs.

    Returns ``None`` when there are no completed repo reviews to analyse.
    """
    reviews = _latest_review_per_repo(jobs)
    if not reviews:
        return None

    # Per-topic accumulation across the deduped repos.
    counts: dict[str, dict[str, int]] = defaultdict(lambda: {"high": 0, "medium": 0, "low": 0})
    repos_touched: dict[str, set[str]] = defaultdict(set)
    findings_by_topic: dict[str, list[dict[str, str]]] = defaultdict(list)
    topic_def_by_name: dict[str, dict[str, Any]] = {}

    def note_exposure(topic_def: dict[str, Any], repo_name: str) -> None:
        topic_def_by_name[topic_def["topic"]] = topic_def
        repos_touched[topic_def["topic"]].add(repo_name)

    for review in reviews:
        repo_name = review.get("repo") or "unknown-repo"
        summary = review.get("summary") or ""
        suggestions = review.get("suggestions") or []
        signal_paths = " ".join((review.get("java_signals") or {}).keys())
        context_text = " ".join([summary, " ".join(suggestions), signal_paths])

        # Exposure: which topics did the student demonstrably work in (even with no errors).
        for topic_def in TOPIC_DEFS:
            if topic_def is _FALLBACK_DEF:
                continue
            if any(pattern.search(context_text) for pattern in topic_def["patterns"]):
                note_exposure(topic_def, repo_name)

        # Findings: route each error into a topic and weight by severity.
        for error in review.get("errors") or []:
            severity = (error.get("severity") or "low").lower()
            if severity not in SEVERITY_WEIGHT:
                severity = "low"
            why = (error.get("why") or "").strip()
            fix_hint = (error.get("fix_hint") or "").strip()
            file = error.get("file") or repo_name
            topic_def = _categorize(f"{why} {fix_hint} {file}")
            topic = topic_def["topic"]
            note_exposure(topic_def, repo_name)
            counts[topic][severity] += 1
            findings_by_topic[topic].append(
                {"severity": severity, "why": why, "fix_hint": fix_hint, "file": file, "repo": repo_name}
            )

    if not topic_def_by_name:
        return None

    gaps: list[dict[str, Any]] = []
    strengths: list[dict[str, Any]] = []
    topic_breakdown: dict[str, Any] = {}
    weighted_sum = 0.0
    weight_total = 0

    severity_rank = {"high": 0, "medium": 1, "low": 2}

    for topic, topic_def in topic_def_by_name.items():
        n_repos = max(1, len(repos_touched[topic]))
        c = counts[topic]
        weighted = c["high"] * SEVERITY_WEIGHT["high"] + c["medium"] * SEVERITY_WEIGHT["medium"] + c["low"] * SEVERITY_WEIGHT["low"]
        total_findings = c["high"] + c["medium"] + c["low"]
        density = weighted / n_repos
        breadth_bonus = min(BREADTH_BONUS_MAX, (n_repos - 1) * BREADTH_BONUS_PER_REPO)
        mastery = _pct(max(MASTERY_FLOOR, min(MASTERY_CEILING, BASE_MASTERY + breadth_bonus - density * DENSITY_PENALTY)))

        topic_breakdown[topic] = {
            "topic_id": topic_def["topic_id"],
            "mastery_score": mastery,
            "repos_touched": n_repos,
            "findings": {"high": c["high"], "medium": c["medium"], "low": c["low"]},
        }
        weighted_sum += mastery * n_repos
        weight_total += n_repos

        # Order for display/evidence: most severe first, then substantive (specific) text
        # before generic review noise, then longer (more detailed) first.
        findings = sorted(
            findings_by_topic.get(topic, []),
            key=lambda f: (severity_rank.get(f["severity"], 2), 0 if _is_substantive(f["why"]) else 1, -len(f["why"])),
        )
        subskills = topic_def["subskills"] or _FALLBACK_DEF["subskills"]

        if mastery < GAP_THRESHOLD and total_findings > 0:
            gaps.append(_build_gap(topic, topic_def, mastery, c, findings, subskills, n_repos))
        else:
            strengths.append(_build_strength(topic, topic_def, mastery, findings, subskills, n_repos, total_findings))

    gaps.sort(key=lambda g: (g["mastery_score"], -g["confidence"]))
    strengths.sort(key=lambda s: s["mastery_score"], reverse=True)

    overall = _pct(weighted_sum / weight_total) if weight_total else 60.0

    payload = {
        "schema_version": MASTERY_PROFILE_SCHEMA_VERSION,
        "student_id": public_student_id,
        "session_id": session_id,
        "analysis_timestamp": _utcnow_iso(),
        "data_sources": {
            "github": "available",
            "github_review_repos": str(len(reviews)),
            "github_review_jobs": str(len(jobs)),
            "sandbox": "unavailable",
            "quizzes": "unavailable",
        },
        "mastery_profile": {
            "overall_mastery_score": overall,
            "knowledge_gaps": gaps,
            "strengths": strengths,
        },
        "recommendations": _recommendations(gaps, strengths),
        "overall_mastery_score": overall,
        "knowledge_gaps": gaps,
        "strengths": strengths,
        "gap_topic_ids": [gap["topic_id"] for gap in gaps],
        "raw_analysis_payload": {
            "source": "github_review_bridge",
            "jobs_considered": len(jobs),
            "repos_analyzed": len(reviews),
            "topic_breakdown": topic_breakdown,
        },
    }

    # Validate against the same contract the pipeline emits so downstream consumers
    # (LMG, career, dashboards) get an identical shape; raises on any drift.
    return CanonicalMasteryOutput.model_validate(payload).model_dump()


def _confidence_gap(total_findings: int, n_repos: int) -> float:
    return round(max(0.45, min(0.95, 0.5 + 0.04 * total_findings + 0.05 * n_repos)), 2)


def _confidence_strength(total_findings: int, n_repos: int) -> float:
    return round(max(0.4, min(0.95, 0.55 + 0.07 * n_repos - 0.03 * total_findings)), 2)


def _build_gap(
    topic: str,
    topic_def: dict[str, Any],
    mastery: float,
    counts: dict[str, int],
    findings: list[dict[str, str]],
    subskills: list[dict[str, str]],
    n_repos: int,
) -> dict[str, Any]:
    total_findings = counts["high"] + counts["medium"] + counts["low"]
    gap_type = _gap_type(mastery)

    if mastery < 50:
        num_weak = len(subskills)
    elif counts["high"] or counts["medium"]:
        num_weak = min(len(subskills), 2)
    else:
        num_weak = 1
    num_weak = max(1, min(num_weak, len(subskills)))

    weak_subskills: list[dict[str, Any]] = []
    for i in range(num_weak):
        sub = subskills[i]
        finding = findings[i % len(findings)] if findings else None
        if finding:
            evidence = f'{finding["why"]} (in {finding["file"]}, {finding["repo"]})'
            focus = finding["fix_hint"] or sub["focus"]
        else:
            evidence = "GitHub review flagged repeated issues in this area."
            focus = sub["focus"]
        weak_subskills.append(
            {
                "subskill": sub["subskill"],
                "subskill_id": sub["subskill_id"],
                "status": "weak",
                "evidence": evidence,
                "recommended_content_focus": focus,
            }
        )

    weak_ids = {item["subskill_id"] for item in weak_subskills}
    known_subskills = [
        {
            "subskill": sub["subskill"],
            "subskill_id": sub["subskill_id"],
            "status": "mastered",
            "evidence": "No review findings linked to this subskill.",
            "recommended_content_focus": None,
        }
        for sub in subskills
        if sub["subskill_id"] not in weak_ids
    ]

    top = findings[0] if findings else None
    example = f' Example: "{top["why"]}" in {top["file"]}.' if top else ""
    evidence_summary = (
        f"GitHub review flagged {total_findings} issue(s) related to {topic} across "
        f"{n_repos} repo(s) ({counts['high']} high, {counts['medium']} medium, {counts['low']} low). "
        f"Mastery estimated at {mastery}/100.{example}"
    )

    error_lines = []
    seen = set()
    for finding in findings:
        line = f'{finding["why"]} ({finding["file"]})'
        if line not in seen:
            seen.add(line)
            error_lines.append(line)
        if len(error_lines) >= 5:
            break

    fix_objectives: list[str] = []
    for finding in findings:
        hint = finding["fix_hint"]
        if hint and hint not in fix_objectives:
            fix_objectives.append(hint)
        if len(fix_objectives) >= 3:
            break
    if not fix_objectives:
        fix_objectives = [sub["focus"] for sub in subskills[:num_weak]]

    return {
        "topic": topic,
        "topic_id": topic_def["topic_id"],
        "gap_type": gap_type,
        "confidence": _confidence_gap(total_findings, n_repos),
        "mastery_score": mastery,
        "weak_subskills": weak_subskills,
        "known_subskills": known_subskills,
        "misconceptions": _dedupe([sub["misconception"] for sub in subskills[:num_weak]]),
        "observed_error_patterns": {"github_review": error_lines},
        "evidence_summary": evidence_summary,
        "prerequisite_topics": topic_def.get("prerequisite_topics", []),
        "related_topics": topic_def.get("related_topics", []),
        "suggested_intervention": _suggested_intervention(gap_type, fix_objectives),
    }


def _build_strength(
    topic: str,
    topic_def: dict[str, Any],
    mastery: float,
    findings: list[dict[str, str]],
    subskills: list[dict[str, str]],
    n_repos: int,
    total_findings: int,
) -> dict[str, Any]:
    known_subskills = [
        {
            "subskill": sub["subskill"],
            "subskill_id": sub["subskill_id"],
            "status": "mastered",
            "evidence": f"Demonstrated across {n_repos} reviewed repo(s) with few or no findings.",
            "recommended_content_focus": None,
        }
        for sub in subskills
    ]
    if total_findings:
        evidence_summary = (
            f"{topic} is a relative strength (mastery {mastery}/100) across {n_repos} reviewed repo(s); "
            f"only minor review findings ({total_findings}) were noted."
        )
    else:
        evidence_summary = (
            f"{topic} is a strength (mastery {mastery}/100): used across {n_repos} reviewed repo(s) "
            f"with no review findings."
        )
    return {
        "topic": topic,
        "topic_id": topic_def["topic_id"],
        "confidence": _confidence_strength(total_findings, n_repos),
        "mastery_score": mastery,
        "mastery_level": "advanced" if mastery >= 85 else "proficient",
        "evidence_summary": evidence_summary,
        "known_subskills": known_subskills,
        # Strong claim: only when used cleanly (no findings) across several repos.
        "can_teach_others": mastery >= 88 and n_repos >= 3 and total_findings == 0,
    }


def _suggested_intervention(gap_type: str, objectives: list[str]) -> dict[str, Any]:
    objectives = objectives or ["Strengthen this area through guided practice on real code."]
    if gap_type == "FUNDAMENTAL_GAP":
        return {
            "primary": "interactive_tutorial",
            "secondary": ["step_by_step_practice", "debugging_exercise"],
            "difficulty_level": "beginner",
            "estimated_time_minutes": 90,
            "learning_objectives": objectives,
        }
    if gap_type == "PARTIAL_GAP":
        return {
            "primary": "step_by_step_practice",
            "secondary": ["targeted_quiz", "code_refactor_exercise"],
            "difficulty_level": "intermediate",
            "estimated_time_minutes": 60,
            "learning_objectives": objectives,
        }
    return {
        "primary": "code_refactor_exercise",
        "secondary": ["targeted_quiz", "worked_example"],
        "difficulty_level": "intermediate",
        "estimated_time_minutes": 30,
        "learning_objectives": objectives,
    }


def _recommendations(gaps: list[dict[str, Any]], strengths: list[dict[str, Any]]) -> dict[str, Any]:
    priority_order = [gap["topic"] for gap in gaps]
    if gaps:
        advice = (
            "Focus learning material on the weakest GitHub-review topics first, starting with "
            f"{priority_order[0]}. Generate exercises from the flagged fix hints."
        )
    else:
        advice = "No significant gaps surfaced from GitHub reviews; reinforce strengths with enrichment work."

    instructor_parts = ["Profile derived from GitHub repo reviews only; sandbox and quiz signals were unavailable."]
    if gaps:
        instructor_parts.append("Confirm the top gap with a short live task before treating it as settled.")
    if strengths:
        instructor_parts.append("Use can_teach_others strengths for peer-learning matches.")

    return {
        "priority_order": priority_order,
        "general_advice": advice,
        "for_instructor": " ".join(instructor_parts),
    }


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


async def rebuild_mastery_profile_from_reviews(
    student_object_id: Optional[str],
    public_student_id: Optional[str],
) -> Optional[dict[str, Any]]:
    """Read a student's repo reviews, build a mastery profile, and persist it.

    Keyed exactly like the rest of the system: ``repo_review_jobs`` are read by the
    student's Mongo ObjectId (``student_id``) and the profile is written under the public
    ``student_id`` that the Mastery page queries. Returns the saved canonical profile, or
    ``None`` when there is nothing to analyse.
    """
    if not student_object_id or not public_student_id:
        logger.info("Mastery bridge skipped: missing student ids (obj=%s, public=%s)",
                    student_object_id, public_student_id)
        return None

    db = get_database()
    jobs = (
        await db.repo_review_jobs.find({"student_id": student_object_id})
        .sort("created_at", -1)
        .to_list(length=200)
    )
    payload = aggregate_reviews_to_mastery(jobs, public_student_id)
    if payload is None:
        logger.info("Mastery bridge: no completed reviews for student %s", public_student_id)
        return None

    saved = await save_mastery_profile(
        payload,
        raw_analysis_payload=payload.get("raw_analysis_payload"),
        diagnostic_report=None,
    )
    logger.info(
        "Mastery bridge: saved profile for %s (overall=%s, gaps=%s, strengths=%s)",
        public_student_id,
        payload.get("overall_mastery_score"),
        len(payload.get("knowledge_gaps", [])),
        len(payload.get("strengths", [])),
    )
    return saved
