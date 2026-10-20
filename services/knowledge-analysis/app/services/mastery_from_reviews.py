"""Bridge: turn a student's GitHub repo reviews into a canonical mastery profile.

Forensics repo reviews are stored in ``repo_review_jobs`` (per-repo LLM findings:
severity + why + fix_hint + suggestions + summary). Nothing previously joined that
data to ``mastery_profiles``, so the Mastery page and Career card stayed empty for
students who only ran reviews. This module aggregates the latest review per repo into
the exact ``CanonicalMasteryOutput`` contract produced by the 10-step pipeline, so the
saved document is indistinguishable (shape-wise) from an ``/analyze`` result.

Two sources of evidence are fused here:

* **Repo reviews** — file-level Java engineering findings. The topic mapping is
  keyword-heuristic by necessity: reviews are not topic-tagged, so each finding is
  bucketed into a Java/SE topic by matching its text. Scores are derived from finding
  density (severity-weighted issues per repo).
* **Sandbox + quiz telemetry** — topic-tagged ``sandbox_attempts`` and ``quiz_sessions``
  that students produce during normal learning. These are summed per topic and fused into
  the same mastery score, so a student who *knows the concept* (good quiz score) but
  *cannot actually apply it* (recurring sandbox runtime/logical errors) shows the gap the
  LMG would otherwise miss.

Exact-concept resolution uses the concept graph (``app/data/java_concept_graph.json``):
each topic's leaf concepts carry ``signal_patterns`` that map raw evidence strings to the
specific concept being missed (e.g. "off-by-one" -> loop boundary conditions), plus the
course ``week_area`` and prerequisite chain the Learning Generator can consume directly.
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Optional

from app.core.constants import MASTERY_PROFILE_SCHEMA_VERSION, TOPIC_CATALOG, WEIGHTS
from app.db.database import get_database
from app.models.schemas import CanonicalMasteryOutput
from app.services import concept_graph as cg
from app.services.mastery_profile_store import save_mastery_profile

logger = logging.getLogger(__name__)

SEVERITY_WEIGHT = {"high": 3, "medium": 2, "low": 1}

# Score tuning. Repo-review findings are NEGATIVE signals (problems), and the absence of
# findings is only weak-positive evidence — you cannot prove "advanced" mastery purely
# from "nothing was flagged". So a topic the student demonstrably worked in starts at a
# proficient BASE, earns a small bonus for clean usage across MANY repos (breadth), and
# is penalised by finding density (severity-weighted issues per repo touching the topic).
#   review_mastery = clamp(BASE + breadth_bonus - density * DENSITY_PENALTY)
BASE_MASTERY = 80.0
DENSITY_PENALTY = 6.0
BREADTH_BONUS_PER_REPO = 2.0
BREADTH_BONUS_MAX = 10.0
MASTERY_FLOOR = 25.0
MASTERY_CEILING = 95.0
# At/above this mastery a topic the student demonstrably worked in counts as a strength;
# below it (with at least one evidence source) it is a knowledge gap.
GAP_THRESHOLD = 72.0
# A finding's text is "substantive" (worth showing as evidence) when it is specific
# enough — short generic strings like "The code has an error." are low-signal review noise.
SUBSTANTIVE_WHY_MIN_LEN = 30

# Minimal evidence every gap must explain; odd keys quoted to match schema naming.
_EMPTY_COUNTS = {"high": 0, "medium": 0, "low": 0}


def _catalog(name: str) -> dict[str, Any]:
    return TOPIC_CATALOG.get(name, {})


# ---------------------------------------------------------------------------
# Topic definitions. Two tiers:
#   1. Review themes (curated keyword routing + catalog metadata) — engineering
#      findings (tests, hygiene, style...) captured first because they are specific.
#   2. Concept-tier topics derived from the concept graph — the Java week topics the
#      LMG should target (Loops, Arrays, Recursion...). Their patterns come from the
#      graph's leaf-concept ``signal_patterns`` so raw evidence maps to exact concepts.
#   3. A catch-all fallback (General Code Quality) as the final bucket.
# Order matters: the FIRST matching topic wins, so most-specific themes come first.
def _build_review_topic_defs() -> list[dict[str, Any]]:
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
    )
    add(
        "Exception Handling", "CS102-EXC",
        [r"exception", r"\btry\b", r"\bcatch\b", r"\bfinally\b", r"\bthrow", r"null ?pointer",
         r"\bnpe\b", r"error handling", r"handle (the )?error", r"swallow", r"stack trace"],
        catalog_name="Exception Handling",
    )
    add(
        "File I/O & Resources", "CS102-FILE",
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
    )
    add(
        "Testing & Verification", "SE-TEST",
        [r"\btest", r"junit", r"\bassert", r"unit test", r"coverage", r"\bmock"],
        prerequisite_topics=["OOP"],
        related_topics=["Debugging"],
    )
    add(
        "Input Validation & Robustness", "SE-VALID",
        [r"validat", r"sanitiz", r"bounds? check", r"check for null", r"edge case",
         r"boundary", r"guard clause", r"user input", r"parse error", r"defensive"],
        prerequisite_topics=["Conditionals"],
        related_topics=["Exception Handling"],
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
    )
    add(
        "Code Style & Readability", "SE-STYLE",
        [r"naming", r"variable name", r"convention", r"readab", r"magic number", r"\bcomment",
         r"hard[- ]coded", r"formatting", r"descriptive", r"indentation", r"code style",
         r"method name", r"\btypo", r"unused"],
        prerequisite_topics=["Basic Java Syntax"],
        related_topics=["Maintainability"],
    )
    # Unify subskills with the concept graph: every topic that has a graph node carries
    # the node's leaf concepts as its subskills, so ``weak_subskills`` *are* the exact
    # concepts the LMG remediates and the enrichment reader can resolve them by id.
    for topic_def in defs:
        node = cg.topic_node_by_id(topic_def["topic_id"])
        if node and node.get("concepts"):
            topic_def["subskills"] = _graph_subskills(node)
    return defs


def _graph_subskills(node: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "subskill": concept.get("label", concept["id"]),
            "subskill_id": concept["id"],
            "focus": concept.get("focus") or cg.DEFAULT_FOCUS,
            "misconception": concept.get("misconception") or cg.DEFAULT_MISCONCEPTION,
        }
        for concept in node.get("concepts") or []
    ]


_STOP_WORDS = {"a", "an", "and", "of", "the", "with", "for", "in", "to", "-", "&"}


def _label_word_patterns(label: str) -> list[str]:
    """Boundary patterns for each significant word in a topic label."""
    patterns: list[str] = []
    for word in re.findall(r"[A-Za-z]+", label or ""):
        word = word.lower()
        if word in _STOP_WORDS or len(word) < 3:
            continue
        patterns.append(rf"\b{re.escape(word)}s?\b")
    return patterns


def _build_concept_topic_defs(review_ids: set[str]) -> list[dict[str, Any]]:
    """Concept-tier defs for graph week-topics not already covered by review defs.

    Subskills are the graph's leaf concepts, so the emitted ``weak_subskills`` are
    exactly the concepts the LMG should remediate, and the concept ids double as the
    ``weak_concept_ids`` the enrichment step reads back off the same list.
    """
    defs: list[dict[str, Any]] = []
    for node in cg.get_graph().get("nodes", {}).values():
        node_id = node.get("id")
        concepts = node.get("concepts") or []
        if (
            not node_id
            or node_id in review_ids
            or node_id == "CS-GEN"  # the catch-all fallback bucket covers this node
            or not concepts  # concept-less nodes are covered by the fallback bucket
        ):
            continue  # already routed by a review theme (same topic id / label)
        patterns = _label_word_patterns(node.get("label", ""))
        for concept in concepts:
            for pattern in concept.get("signal_patterns") or []:
                if pattern and not any(re.search(p, pattern, re.IGNORECASE) for p in patterns):
                    patterns.append(pattern)
        defs.append(
            {
                "topic": node.get("label") or node_id,
                "topic_id": node_id,
                "patterns": [re.compile(p, re.IGNORECASE) for p in patterns] or [re.compile(r".*")],
                "prerequisite_topics": cg.prerequisite_chain(node.get("label")),
                "related_topics": cg.related_topics(node.get("label")),
                "subskills": _graph_subskills(node),
                "week_area": node.get("week_area") or cg.DEFAULT_WEEK_AREA,
                "difficulty": int(node.get("difficulty") or cg.DEFAULT_DIFFICULTY),
            }
        )
    return defs


def _build_topic_defs() -> list[dict[str, Any]]:
    review_defs = _build_review_topic_defs()
    concept_defs = _build_concept_topic_defs({d["topic_id"] for d in review_defs})
    fallback = {
        "topic": "General Code Quality",
        "topic_id": "CS-GEN",
        "patterns": [re.compile(r".*")],
        "prerequisite_topics": ["Basic Java Syntax"],
        "related_topics": [],
        "subskills": [
            {
                "subskill": "core concept application",
                "subskill_id": "CS-GEN-CORE",
                "focus": "Review the flagged concept with small traceable examples.",
                "misconception": "cannot reliably apply the concept independently",
            }
        ],
    }
    return review_defs + concept_defs + [fallback]


TOPIC_DEFS = _build_topic_defs()
_FALLBACK_DEF = TOPIC_DEFS[-1]


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _categorize(text: str) -> dict[str, Any]:
    """Route evidence to the topic def that best explains it.

    Each non-fallback def scores one point per matching pattern; the topic's own
    label words are counted once more, so overlapping generic terms (e.g. "condition"
    inside "loop condition" or a recursion base case) do not steal a finding from the
    week topic the text is really about. The most specific def wins; TOPIC_DEFS
    position (review themes before concept tier) breaks ties.
    """
    if not text:
        return _FALLBACK_DEF
    best: Optional[dict[str, Any]] = None
    best_score = 0
    for topic_def in TOPIC_DEFS:
        if topic_def is _FALLBACK_DEF:
            continue
        score = 0
        for pattern in topic_def["patterns"]:
            if pattern.search(text):
                score += 1
        label_word_patterns = [
            re.compile(p, re.IGNORECASE) for p in _label_word_patterns(topic_def["topic"])
        ]
        for pattern in label_word_patterns:
            if pattern.search(text):
                score += 1
        if score > best_score:
            best_score = score
            best = topic_def
    return best or _FALLBACK_DEF


def _def_for_evidence(topic_name: str | None) -> Optional[dict[str, Any]]:
    """Resolve a topic-tagged quiz/sandbox name (e.g. 'Loops') to a topic def."""
    name = (topic_name or "").strip()
    if not name:
        return None
    lowered = name.lower()
    for topic_def in TOPIC_DEFS:
        if topic_def["topic"].lower() == lowered:
            return topic_def
    node = cg.topic_node(name)
    if node:
        for topic_def in TOPIC_DEFS:
            if topic_def["topic_id"] == node["id"]:
                return topic_def
        for topic_def in TOPIC_DEFS:
            if topic_def["topic"].lower() == (node.get("label") or "").lower():
                return topic_def
    return None


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
    """Whether a finding's text is specific enough to show as evidence."""
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


def _quiz_score(perf: Optional[dict[str, Any]]) -> Optional[float]:
    if not perf or not perf.get("total"):
        return None
    return round(max(0.0, min(float(perf.get("correct", 0)) / float(perf["total"]), 1.0)), 3)


def _sandbox_score(attrs: Optional[dict[str, Any]]) -> Optional[float]:
    if not attrs or not attrs.get("compile_attempts"):
        return None
    attempts = float(attrs["compile_attempts"])
    errors = (
        float(attrs.get("runtime_errors", 0))
        + float(attrs.get("logical_errors", 0))
        + 0.5 * float(attrs.get("syntax_errors", 0))
    )
    return round(max(0.0, min(1.0 - errors / attempts, 1.0)), 3)


def _fused_mastery(review_pct: Optional[float], quiz: Optional[float], sandbox: Optional[float]) -> float:
    """Weighted mean over whichever sources are present, renormalised to sum 1.

    Mirrors the pipeline's WEIGHTS (sandbox .4, forensic .3, quiz .3) where the
    repository-forensic signal is supplied by review density.
    """
    available: list[tuple[float, float]] = []
    if review_pct is not None:
        available.append((WEIGHTS["forensic"], review_pct / 100.0))
    if quiz is not None:
        available.append((WEIGHTS["quiz"], quiz))
    if sandbox is not None:
        available.append((WEIGHTS["sandbox"], sandbox))
    if not available:
        return 60.0
    weight_sum = sum(weight for weight, _ in available)
    value = sum(weight * score for weight, score in available) / weight_sum
    return round(max(MASTERY_FLOOR, min(MASTERY_CEILING, round(value * 100, 1))), 1)


def _signals_for_topic(
    topic: str,
    topic_def: dict[str, Any],
    counts: dict[str, dict[str, int]],
    repos_touched: dict[str, set[str]],
    quiz_by_def: dict[str, dict[str, Any]],
    sandbox_by_def: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    c = counts.get(topic) or _EMPTY_COUNTS
    total_findings = c["high"] + c["medium"] + c["low"]
    n_repos = len(repos_touched.get(topic) or set())
    review_touched = n_repos > 0

    review_mastery_pct: Optional[float] = None
    if review_touched:
        weighted = c["high"] * SEVERITY_WEIGHT["high"] + c["medium"] * SEVERITY_WEIGHT["medium"] + c["low"] * SEVERITY_WEIGHT["low"]
        density = weighted / n_repos
        breadth_bonus = min(BREADTH_BONUS_MAX, (n_repos - 1) * BREADTH_BONUS_PER_REPO)
        review_mastery_pct = _pct(max(MASTERY_FLOOR, min(MASTERY_CEILING, BASE_MASTERY + breadth_bonus - density * DENSITY_PENALTY)))

    quiz_buffer = quiz_by_def.get(topic)
    sandbox_buffer = sandbox_by_def.get(topic)
    quiz_score = _quiz_score(quiz_buffer)
    sandbox_score = _sandbox_score(sandbox_buffer)

    mastery = _fused_mastery(review_mastery_pct, quiz_score, sandbox_score)
    sources = int(bool(review_touched)) + int(quiz_score is not None) + int(sandbox_score is not None)
    return {
        "counts": c,
        "total_findings": total_findings,
        "n_repos": n_repos,
        "review_touched": review_touched,
        "review_mastery_pct": review_mastery_pct,
        "quiz_score": quiz_score,
        "sandbox_score": sandbox_score,
        "mastery": mastery,
        "findings": [],
        "sources": max(sources, 1),
        "quiz_attrs": quiz_buffer or {},
        "sandbox_attrs": sandbox_buffer or {},
        "sandbox_error_texts": list((sandbox_buffer or {}).get("errors", []))[:5],
    }


def aggregate_reviews_to_mastery(
    jobs: list[dict[str, Any]],
    public_student_id: str,
    session_id: Optional[str] = None,
    quiz_evidence: Optional[dict[str, dict[str, Any]]] = None,
    sandbox_evidence: Optional[dict[str, dict[str, Any]]] = None,
) -> Optional[dict[str, Any]]:
    """Build a canonical mastery payload from repo reviews + sandbox/quiz telemetry.

    Returns ``None`` when there is no evidence at all (no reviews, quizzes or sandbox
    sessions) to analyse.
    """
    reviews = _latest_review_per_repo(jobs)
    quiz_evidence = quiz_evidence or {}
    sandbox_evidence = sandbox_evidence or {}

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

    # Map topic-tagged quiz/sandbox evidence onto topic defs (label or graph resolution).
    quiz_by_def: dict[str, dict[str, Any]] = {}
    for topic_name, perf in quiz_evidence.items():
        topic_def = _def_for_evidence(topic_name)
        if topic_def:
            topic_def_by_name[topic_def["topic"]] = topic_def
            quiz_by_def[topic_def["topic"]] = perf
    sandbox_by_def: dict[str, dict[str, Any]] = {}
    for topic_name, attrs in sandbox_evidence.items():
        topic_def = _def_for_evidence(topic_name)
        if topic_def:
            topic_def_by_name[topic_def["topic"]] = topic_def
            sandbox_by_def[topic_def["topic"]] = attrs

    if not topic_def_by_name:
        return None

    gaps: list[dict[str, Any]] = []
    strengths: list[dict[str, Any]] = []
    topic_breakdown: dict[str, Any] = {}
    weighted_sum = 0.0
    weight_total = 0

    for topic, topic_def in list(topic_def_by_name.items()):
        signals = _signals_for_topic(topic, topic_def, counts, repos_touched, quiz_by_def, sandbox_by_def)
        findings = findings_by_topic.get(topic) or signals["findings"]
        signals["findings"] = findings
        mastery = signals["mastery"]
        n_repos = signals["n_repos"]

        topic_breakdown[topic] = {
            "topic_id": topic_def["topic_id"],
            "mastery_score": mastery,
            "sources": signals["sources"],
            "repos_touched": n_repos,
            "findings": dict(signals["counts"]),
            "quiz_score": signals["quiz_score"],
            "sandbox_score": signals["sandbox_score"],
            "review_score": signals["review_mastery_pct"],
        }
        weighted_sum += mastery * signals["sources"]
        weight_total += signals["sources"]

        if mastery < GAP_THRESHOLD:
            gaps.append(_build_gap(topic, topic_def, signals, findings_by_topic))
        else:
            strengths.append(_build_strength(topic, topic_def, signals))

    gaps.sort(key=lambda g: (g["mastery_score"], -g["confidence"]))
    strengths.sort(key=lambda s: s["mastery_score"], reverse=True)

    overall = _pct(weighted_sum / weight_total) if weight_total else 60.0

    data_sources = {
        "github": "available" if reviews else "unavailable",
        "sandbox": "available" if sandbox_evidence else "unavailable",
        "quizzes": "available" if quiz_evidence else "unavailable",
        "github_review_repos": str(len(reviews)),
        "github_review_jobs": str(len(jobs)),
    }

    payload = {
        "schema_version": MASTERY_PROFILE_SCHEMA_VERSION,
        "student_id": public_student_id,
        "session_id": session_id,
        "analysis_timestamp": _utcnow_iso(),
        "data_sources": data_sources,
        "mastery_profile": {
            "overall_mastery_score": overall,
            "knowledge_gaps": gaps,
            "strengths": strengths,
        },
        "recommendations": _recommendations(gaps, strengths, data_sources),
        "overall_mastery_score": overall,
        "knowledge_gaps": gaps,
        "strengths": strengths,
        "gap_topic_ids": [gap["topic_id"] for gap in gaps],
        "raw_analysis_payload": {
            "source": "github_review_bridge",
            "jobs_considered": len(jobs),
            "repos_analyzed": len(reviews),
            "evidence_fused": {
                "review": len(reviews),
                "quiz_topics": sorted(quiz_by_def),
                "sandbox_topics": sorted(sandbox_by_def),
            },
            "topic_breakdown": topic_breakdown,
            "concept_graph": {
                "schema_version": cg.schema_version(),
                "reference_path": "app/data/java_concept_graph.json",
            },
        },
    }

    # Validate against the same contract the pipeline emits so downstream consumers
    # (LMG, career, dashboards) get an identical shape; raises on any drift.
    return CanonicalMasteryOutput.model_validate(payload).model_dump()


def _confidence_gap(total_findings: int, n_repos: int, sources: int) -> float:
    base = 0.5 + 0.04 * total_findings + 0.05 * n_repos
    if sources >= 2:
        base += 0.05
    if sources >= 3:
        base += 0.05
    return round(max(0.45, min(0.97, base)), 2)


def _confidence_strength(total_findings: int, n_repos: int, sources: int) -> float:
    base = 0.55 + 0.07 * n_repos - 0.03 * total_findings
    if sources >= 2:
        base += 0.04
    return round(max(0.4, min(0.95, base)), 2)


def _ordinal_weak_subskills(
    subskills: list[dict[str, Any]],
    mastery: float,
    quiz_score: Optional[float],
    sandbox_score: Optional[float],
    counts: dict[str, int],
) -> list[dict[str, Any]]:
    """Fallback selection: pick a number of weak concepts from source signals."""
    if not subskills:
        return []
    if mastery < 50:
        num_weak = len(subskills)
    else:
        num_weak = 1
        if counts.get("high") or counts.get("medium"):
            num_weak = min(2, len(subskills))
        if quiz_score is not None and quiz_score < 0.75:
            num_weak = max(num_weak, min(2, len(subskills)))
        if sandbox_score is not None and sandbox_score < 0.5:
            num_weak = max(num_weak, min(2, len(subskills)))
    num_weak = max(1, min(num_weak, len(subskills)))
    return subskills[:num_weak]


def _subskill_diagnosis(
    topic: str,
    subskills: list[dict[str, Any]],
    signals: dict[str, Any],
    matched_ids: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split subskills/concepts into weak vs known using concept-graph matches first."""
    if not subskills:
        return [], []

    findings = signals["findings"]
    counts = signals["counts"]
    mastery = signals["mastery"]
    quiz_score = signals["quiz_score"]
    sandbox_score = signals["sandbox_score"]
    n_repos = signals["n_repos"]

    if matched_ids:
        weak = [s for s in subskills if s["subskill_id"] in matched_ids]
        if not weak:  # matched ids never hinge on def subskills -> fall back
            weak = _ordinal_weak_subskills(subskills, mastery, quiz_score, sandbox_score, counts)
    else:
        weak = _ordinal_weak_subskills(subskills, mastery, quiz_score, sandbox_score, counts)

    weak_out: list[dict[str, Any]] = []
    weak_ids: set[str] = set()
    for i, sub in enumerate(weak):
        weak_ids.add(sub["subskill_id"])
        finding = findings[i % len(findings)] if findings else None
        concept_match = cg.concept_by_id(topic, sub["subskill_id"])
        if concept_match:
            evidence = _subskill_concept_evidence(topic, concept_match, signals)
            focus = concept_match.get("focus") or sub["focus"]
        elif finding:
            evidence = f'{finding["why"]} (in {finding["file"]}, {finding["repo"]})'
            focus = finding["fix_hint"] or sub["focus"]
        else:
            evidence = "Evidence in this area did not pin down one concept; treat the topic as weak overall."
            focus = sub["focus"]
        weak_out.append(
            {
                "subskill": sub["subskill"],
                "subskill_id": sub["subskill_id"],
                "status": "weak",
                "evidence": evidence,
                "recommended_content_focus": focus,
            }
        )

    known_out = [
        {
            "subskill": sub["subskill"],
            "subskill_id": sub["subskill_id"],
            "status": "mastered",
            "evidence": "No weakness signal linked to this concept in the available evidence.",
            "recommended_content_focus": None,
        }
        for sub in subskills
        if sub["subskill_id"] not in weak_ids
    ]
    return weak_out, known_out


def _subskill_concept_evidence(topic: str, concept: dict[str, Any], signals: dict[str, Any]) -> str:
    source_bits: list[str] = []
    if signals["findings"]:
        source_bits.append("review findings matched its signal patterns")
    if signals["sandbox_score"] is not None and signals["sandbox_score"] < 0.75:
        source_bits.append("repeated sandbox errors around this concept")
    if signals["quiz_score"] is not None and signals["quiz_score"] < 0.75:
        source_bits.append("quiz answers missed the concept")
    detail = "; ".join(source_bits) or "weakness affects this specific concept"
    return f"{concept.get('label', concept['id'])} flagged as weak: {detail}."


def _build_gap(
    topic: str,
    topic_def: dict[str, Any],
    signals: dict[str, Any],
    findings_by_topic: dict[str, list[dict[str, str]]],
) -> dict[str, Any]:
    counts = signals["counts"]
    total_findings = signals["total_findings"]
    n_repos = signals["n_repos"]
    mastery = signals["mastery"]
    findings = findings_by_topic.get(topic) or signals["findings"]
    signals["findings"] = findings
    source_count = signals["sources"]
    gap_type = _gap_type(mastery)

    subskills = topic_def.get("subskills") or _FALLBACK_DEF["subskills"]

    # Concept-graph matching over raw evidence (review findings + sandbox error text).
    evidence_text = _evidence_text(topic, findings, signals)
    matched = cg.match_concepts(topic, evidence_text)
    matched_ids = {concept["id"] for concept in matched}

    weak_subskills, known_subskills = _subskill_diagnosis(topic, subskills, signals, matched_ids)
    if not weak_subskills:  # no subskills at all: fall back to a generic gap entry
        weak_subskills = [
            {
                "subskill": "core concept application",
                "subskill_id": "CS-GEN-CORE",
                "status": "weak",
                "evidence": f"Mastery for {topic} is estimated at {mastery}/100.",
                "recommended_content_focus": cg.DEFAULT_FOCUS,
            }
        ]

    weak_concept_ids = [item["subskill_id"] for item in weak_subskills]
    weak_concepts = [item["subskill"] for item in weak_subskills]

    misconceptions = _misconceptions_for(topic, weak_concept_ids, weak_subskills)

    week_area = cg.week_area(topic)
    prerequisites = cg.prerequisite_chain(topic) or topic_def.get("prerequisite_topics", [])
    related = cg.related_topics(topic) or topic_def.get("related_topics", [])

    observed = _observed_error_patterns(topic, findings, signals)
    evidence_summary = _gap_evidence_summary(topic, mastery, findings, signals, counts, n_repos)

    objectives = cg.objectives_for_weak_concepts(topic, weak_concept_ids)
    if not objectives:
        objectives = _objectives_from_subskills(weak_subskills, findings)

    intervention = _suggested_intervention(gap_type, objectives, week_area)

    return {
        "topic": topic,
        "topic_id": topic_def["topic_id"],
        "gap_type": gap_type,
        "confidence": _confidence_gap(total_findings, n_repos, source_count),
        "mastery_score": mastery,
        "weak_subskills": weak_subskills,
        "known_subskills": known_subskills,
        "misconceptions": misconceptions,
        "observed_error_patterns": observed,
        "evidence_summary": evidence_summary,
        "prerequisite_topics": prerequisites,
        "related_topics": related,
        "suggested_intervention": intervention,
        "weak_concepts": weak_concepts,
        "weak_concept_ids": weak_concept_ids,
        "week_area": week_area,
    }


def _build_strength(
    topic: str,
    topic_def: dict[str, Any],
    signals: dict[str, Any],
) -> dict[str, Any]:
    subskills = topic_def.get("subskills") or _FALLBACK_DEF["subskills"]
    total_findings = signals["total_findings"]
    n_repos = signals["n_repos"]
    mastery = signals["mastery"]

    known_subskills = [
        {
            "subskill": sub["subskill"],
            "subskill_id": sub["subskill_id"],
            "status": "mastered",
            "evidence": f"Demonstrated clean across {max(1, n_repos)} repo(s)/attempts with no weakness signal.",
            "recommended_content_focus": None,
        }
        for sub in subskills
    ]
    parts = [f"{topic} is a current strength (mastery {mastery}/100)."]
    if signals["quiz_score"] is not None:
        parts.append(f"Quiz signal {_pct(signals['quiz_score'] * 100)}/100.")
    if signals["sandbox_score"] is not None:
        parts.append(f"Sandbox signal {_pct(signals['sandbox_score'] * 100)}/100.")
    if n_repos:
        parts.append(f"Used across {n_repos} reviewed repo(s) with {total_findings} review finding(s).")

    return {
        "topic": topic,
        "topic_id": topic_def["topic_id"],
        "confidence": _confidence_strength(total_findings, n_repos, signals["sources"]),
        "mastery_score": mastery,
        "mastery_level": "advanced" if mastery >= 85 else "proficient",
        "evidence_summary": " ".join(parts),
        "known_subskills": known_subskills,
        # Strong claim: only when used cleanly across several repos with corroborating signals.
        "can_teach_others": mastery >= 88 and n_repos >= 3 and total_findings == 0,
    }


def _evidence_text(topic: str, findings: list[dict[str, str]], signals: dict[str, Any]) -> str:
    bits: list[str] = []
    for finding in findings:
        bits.extend([finding.get("why", ""), finding.get("fix_hint", "")])
    if signals.get("sandbox_error_texts"):
        bits.extend(signals["sandbox_error_texts"])
    return " ".join(bits).strip()


def _observed_error_patterns(
    topic: str,
    findings: list[dict[str, str]],
    signals: dict[str, Any],
) -> dict[str, list[str]]:
    observed: dict[str, list[str]] = {}

    error_lines: list[str] = []
    seen: set[str] = set()
    for finding in findings:
        line = f'{finding.get("why", "")} ({finding.get("file", "")})'
        if line and line not in seen:
            seen.add(line)
            error_lines.append(line)
        if len(error_lines) >= 5:
            break
    if error_lines:
        observed["github_review"] = error_lines

    sandbox_lines = list(signals.get("sandbox_error_texts") or [])
    if signals["sandbox_score"] is not None and signals["sandbox_score"] < 0.75:
        attrs = signals.get("sandbox_attrs", {})
        trailing = (
            f"{attrs.get('syntax_errors', 0)} syntax, {attrs.get('runtime_errors', 0)} runtime "
            f"and {attrs.get('logical_errors', 0)} logical error(s) across "
            f"{attrs.get('compile_attempts', 0)} attempt(s)"
        )
        if trailing not in sandbox_lines:
            sandbox_lines.insert(0, trailing)
    if sandbox_lines:
        observed["sandbox"] = sandbox_lines[:5]

    if signals["quiz_score"] is not None and signals["quiz_score"] < 0.85:
        perf = signals.get("quiz_attrs", {})
        suffix = ""
        if perf.get("retry_count"):
            suffix = f" with {perf['retry_count']} retry(ies)"
        observed["quizzes"] = [f"answered {perf.get('correct', 0)}/{perf.get('total', 0)} correctly{suffix}"]

    return observed


def _misconceptions_for(
    topic: str,
    weak_concept_ids: list[str],
    weak_subskills: list[dict[str, Any]],
) -> list[str]:
    misconceptions = cg.misconceptions_for_weak_concepts(topic, weak_concept_ids)
    if not misconceptions:
        # Topic-level fallback when the graph has no leaf-concept entry for the ids.
        for item in weak_subskills:
            c = cg.concept_by_id(topic, item["subskill_id"])
            if c and c.get("misconception"):
                misconceptions.append(c["misconception"])
    deduped = _dedupe([m for m in misconceptions if m])
    return deduped or [cg.DEFAULT_MISCONCEPTION]


def _gap_evidence_summary(
    topic: str,
    mastery: float,
    findings: list[dict[str, str]],
    signals: dict[str, Any],
    counts: dict[str, int],
    n_repos: int,
) -> str:
    chunks: list[str] = []
    if findings:
        chunks.append(
            f"GitHub review flagged {len(findings)} issue(s) related to {topic} across "
            f"{n_repos} repo(s) ({counts['high']} high, {counts['medium']} medium, {counts['low']} low)."
        )
    else:
        chunks.append(f"No review findings surfaced for {topic}.")
    if signals["quiz_score"] is not None:
        perf = signals.get("quiz_attrs", {})
        chunks.append(f"Quiz performance {perf.get('correct', 0)}/{perf.get('total', 0)} "
                      f"({_pct(signals['quiz_score'] * 100)}/100).")
    if signals["sandbox_score"] is not None:
        chunks.append(f"Sandbox signal {_pct(signals['sandbox_score'] * 100)}/100 with recurring errors.")
    chunks.append(f"Mastery estimated at {mastery}/100 using {signals['sources']} evidence source(s).")
    if findings:
        top = findings[0]
        chunks.append(f' Example: "{top.get("why")}" in {top.get("file")}.')
    return " ".join(chunks)


def _objectives_from_subskills(
    weak_subskills: list[dict[str, Any]],
    findings: list[dict[str, str]],
) -> list[str]:
    objectives: list[str] = []
    seen: set[str] = set()
    for finding in findings:
        hint = finding.get("fix_hint")
        if hint and hint not in seen:
            seen.add(hint)
            objectives.append(hint)
    if not objectives:
        for sub in weak_subskills:
            focus = sub.get("recommended_content_focus")
            if focus and focus not in seen:
                seen.add(focus)
                objectives.append(focus)
    return objectives[:5]


def _suggested_intervention(gap_type: str, objectives: list[str], week_area: str | None = None) -> dict[str, Any]:
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


def _recommendations(
    gaps: list[dict[str, Any]],
    strengths: list[dict[str, Any]],
    data_sources: dict[str, str],
) -> dict[str, Any]:
    priority_order = [gap["topic"] for gap in gaps]
    if gaps:
        top = gaps[0]
        parts = [f"Focus learning material on the weakest content first: {top['topic']}."]
        if top.get("week_area") and not top["week_area"].startswith("Engineering"):
            parts.append(f"Target the {top['week_area']} week-area.")
        if top.get("weak_concepts"):
            parts.append("Resolve the flagged concepts: " + ", ".join(top["weak_concepts"][:4]) + ".")
        for instructor in _risk_note(gaps):
            parts.append(instructor)
        advice = " ".join(parts)
    else:
        advice = "No significant gaps surfaced; reinforce strengths with enrichment work."

    instructor_parts: list[str] = []
    if data_sources["sandbox"] == "available" or data_sources["quizzes"] == "available":
        instructor_parts.append(
            "Profile fuses GitHub reviews with sandbox and quiz telemetry where available."
        )
    if gaps:
        instructor_parts.append("Confirm the top gap with a short live task before treating it as settled.")
    if strengths:
        instructor_parts.append("Use can_teach_others strengths for peer-learning matches.")

    return {
        "priority_order": priority_order,
        "general_advice": advice,
        "for_instructor": " ".join(instructor_parts),
    }


def _risk_note(gaps: list[dict[str, Any]]) -> list[str]:
    weak_topics = [gap["topic"] for gap in gaps]
    risk = cg.downstream_topics(weak_topics)
    if not risk:
        return []
    return [f"Weak prerequisites put these at risk: {', '.join(risk[:5])}."]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


# ---------------------------------------------------------------------------
# DB loading: pull topic-tagged quiz + sandbox telemetry for the student.
# ---------------------------------------------------------------------------
async def _load_quiz_evidence(db, student_object_id: str) -> dict[str, dict[str, Any]]:
    """Aggregate completed quiz sessions into per-topic performance (like /analyze/auto)."""
    evidence: dict[str, dict[str, Any]] = {}
    try:
        quiz_docs = (
            await db.quiz_sessions.find({"student_id": student_object_id, "status": "completed"})
            .sort("completed_at", -1)
            .limit(10)
            .to_list(length=10)
        )
    except Exception as exc:  # noqa: BLE001 - telemetry is best-effort enrichment
        logger.info("Quiz evidence unavailable: %s", exc)
        return evidence

    for doc in quiz_docs:
        for ans in doc.get("answers", []) or []:
            topic = ans.get("topic", "Unknown")
            bucket = evidence.setdefault(topic, {"correct": 0, "total": 0, "time": 0.0, "retry_count": 0})
            bucket["total"] += 1
            bucket["time"] += float(ans.get("time_seconds", 0) or 0)
            if ans.get("correct"):
                bucket["correct"] += 1
    return {
        topic: {
            "correct": bucket["correct"],
            "total": bucket["total"],
            "avg_time_seconds": round(bucket["time"] / bucket["total"], 1) if bucket["total"] else 0.0,
            "retry_count": bucket.get("retry_count", 0),
        }
        for topic, bucket in evidence.items()
        if bucket["total"]
    }


async def _load_sandbox_evidence(db, student_object_id: str) -> dict[str, dict[str, Any]]:
    """Aggregate sandbox attempts into per-topic error/success signals + raw error text."""
    evidence: dict[str, dict[str, Any]] = {}
    try:
        attempts = (
            await db.sandbox_attempts.find({"student_id": student_object_id})
            .sort("created_at", -1)
            .limit(50)
            .to_list(length=50)
        )
    except Exception as exc:  # noqa: BLE001 - telemetry is best-effort enrichment
        logger.info("Sandbox evidence unavailable: %s", exc)
        return evidence

    for att in attempts:
        topic = att.get("topic", "Unknown")
        bucket = evidence.setdefault(
            topic,
            {
                "compile_attempts": 0,
                "syntax_errors": 0,
                "runtime_errors": 0,
                "logical_errors": 0,
                "passed": 0,
                "errors": [],
                "time_to_success_seconds": 0.0,
                "error_correction_latency": 0.0,
            },
        )
        bucket["compile_attempts"] += 1
        bucket["time_to_success_seconds"] += float(att.get("runtime_ms") or 0)
        err = (att.get("error") or "").lower()
        if att.get("error"):
            if err not in bucket["errors"]:
                bucket["errors"].append(att["error"])
        if att.get("success") is False:
            if any(
                token in err for token in ("compileerror", "syntax", "cannot find symbol", "error:")
            ):
                bucket["syntax_errors"] += 1
            else:
                bucket["runtime_errors"] += 1
        elif att.get("passed"):
            bucket["passed"] += 1
        else:
            bucket["logical_errors"] += 1
    out: dict[str, dict[str, Any]] = {}
    for topic, bucket in evidence.items():
        attempts_n = max(bucket["compile_attempts"], 1)
        out[topic] = {
            "compile_attempts": bucket["compile_attempts"],
            "syntax_errors": bucket["syntax_errors"],
            "runtime_errors": bucket["runtime_errors"],
            "logical_errors": bucket["logical_errors"],
            "passed": bucket["passed"],
            "errors": bucket["errors"][:5],
            "time_to_success_seconds": round(bucket["time_to_success_seconds"] / attempts_n, 1),
            "error_correction_latency": 10.0,
        }
    return out


async def rebuild_mastery_profile_from_reviews(
    student_object_id: Optional[str],
    public_student_id: Optional[str],
) -> Optional[dict[str, Any]]:
    """Read a student's repo reviews + sandbox/quiz telemetry, build a profile, persist it.

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
    quiz_evidence = await _load_quiz_evidence(db, student_object_id)
    sandbox_evidence = await _load_sandbox_evidence(db, student_object_id)
    payload = aggregate_reviews_to_mastery(
        jobs,
        public_student_id,
        quiz_evidence=quiz_evidence,
        sandbox_evidence=sandbox_evidence,
    )
    if payload is None:
        logger.info("Mastery bridge: no evidence for student %s", public_student_id)
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