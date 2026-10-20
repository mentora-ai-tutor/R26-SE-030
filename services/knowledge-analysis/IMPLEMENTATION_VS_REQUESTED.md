# KAA Output — Requested Design vs. Implemented (Backend)

**Scope:** compares the two JSON designs requested for the Knowledge Analysis Agent
(the rich *forensic* JSON and the downstream-consumption *mastery* JSON) against what the
backend actually builds, validates, and saves today.

**Source of truth in code:**
- `app/models/schemas.py` → `CanonicalMasteryOutput`, `KnowledgeGap`, `Strength`, `SubskillDiagnosis`, `SuggestedIntervention`
- `app/services/profile_contract.py` → `build_canonical_mastery_output()`
- `app/services/diagnostic_report.py` → `build_diagnostic_report()`
- `app/services/mastery_profile_store.py` → `save_mastery_profile()` / `build_mastery_profile_document()`
- `app/api/routes.py` (`POST /analyze`), `app/api/mastery_profile_routes.py` (`GET /api/v1/mastery-profiles/{id}/latest`)
- Tests: `tests/test_diagnostic_report.py`, `tests/test_mastery_profile_contract.py` (suite: **20 passing**)

---

## TL;DR verdict

The requested design is delivered across **two layers in one saved document** (`knowledge_analysis.mastery_profiles`):

| Requested design | Where it lives now | Status |
|---|---|---|
| Downstream-consumption JSON (`mastery_profile.knowledge_gaps[]/strengths[]`, `topic_id`, `gap_type`, `misconceptions`, `observed_error_patterns`, `suggested_intervention`, prerequisites) | **Canonical contract** (`CanonicalMasteryOutput`), top of the doc | ✅ Implemented (and richer — adds `weak_subskills[]`) |
| Rich forensic JSON (`github_forensics`, `sandbox_telemetry`, `adaptive_quiz_results`, `synthesized_mastery_profile`, `recommendations`) | **`diagnostic_report`** companion, embedded in same doc | ✅ Implemented (with honest scope limits) |
| File-level AI detection, real commit totals, commit-message quality, repo-review linkage | — | ❌ Not built (data not available to the pipeline) |

**Structure & graceful degradation: fully achieved.** **Some values are computed (not authored) and some rich forensic fields are intentionally omitted** — details below.

---

## Layer 1 — Downstream-consumption JSON (the "Example 2" design)

Requested per-gap fields → implemented in `KnowledgeGap` (`schemas.py`):

| Requested field | Implemented? | Notes |
|---|---|---|
| `topic` | ✅ | |
| `topic_id` | ✅ | Stable IDs from `TOPIC_CATALOG` (e.g. `CS101-REC`) |
| `gap_type` | ✅ (extended) | Requested `FUNDAMENTAL_GAP`/`PARTIAL_GAP`; impl adds **`SURFACE_GAP`**. Assigned by mastery thresholds (`<50/<75/<85`), not analyst judgement |
| `confidence` | ✅ (computed) | 0–1, but **calculated** (`base × source_factor + agreement_bonus`, clamped 0.35–0.99), not hand-set. GitHub present raises it |
| `misconceptions` | ✅ | From `TOPIC_CATALOG` subskill metadata + generic appends |
| `observed_error_patterns {sandbox, quizzes, github}` | ✅ | `github` is **always a list** (`[]` when absent) — never the string `"not available"` |
| `evidence_summary` | ✅ | Generated sentence per gap |
| `prerequisite_topics` / `related_topics` | ✅ | From catalog |
| `suggested_intervention {primary, secondary, difficulty_level, estimated_time_minutes, learning_objectives}` | ✅ | `learning_objectives` are **templated**, not handcrafted prose |
| **`weak_subskills[]`** (not requested) | ➕ added | The key add: pinpoints *which part* of a topic fails ("knows loops, fails off-by-one"). Each has `recommended_content_focus` — the field LMG should drive content from |
| **`known_subskills[]`** (not requested) | ➕ added | Mastered subskills of a weak topic |
| **`mastery_score`** (not requested) | ➕ added | 0–100 raw topic score |

Requested per-strength fields → implemented in `Strength`:

| Requested field | Implemented? | Notes |
|---|---|---|
| `topic`, `topic_id`, `confidence`, `evidence_summary`, `can_teach_others` | ✅ | |
| `mastery_level` | ✅ (extended) | Requested `advanced`/`proficient`; impl adds `beginner` |
| `mastery_score`, `known_subskills[]` | ➕ added | |

Top-level + recommendations:

| Requested | Implemented? | Notes |
|---|---|---|
| `student_id`, `analysis_timestamp`, `data_sources` | ✅ | |
| `mastery_profile.overall_mastery_score` (0–100) | ✅ | |
| `recommendations {priority_order, general_advice, for_instructor}` | ✅ | (This is the *canonical* recommendation shape, not `immediate/short/long_term`) |
| `schema_version`, `session_id`, top-level mirrors, `gap_topic_ids`, `raw_analysis_payload` | ➕ added | Versioning + back-compat |

---

## Layer 2 — Rich forensic JSON (the "Example 1" design) → `diagnostic_report`

Built by `build_diagnostic_report()`, embedded under `diagnostic_report` (own `schema_version: kaa-forensic-report-v1.0`).

### `data_sources`, `student_id`, `analysis_timestamp` — ✅

### `github_forensics`

| Requested field | Implemented? | Saved as / why not |
|---|---|---|
| `commit_pattern_classification` | ✅ | `BIG_BANG`/`INCREMENTAL`/`MIXED` |
| `commit_pattern_breakdown {incremental/big_bang/erratic}` | ✅ | `*_percent` |
| `commit_size_analysis {small/medium/large}` | ✅ | `*_commits_percent` |
| `refactoring_velocity` | ✅ | `refactoring_velocity_avg` |
| `total_commits` (e.g. 147) | ⚠️ partial | `commits_sampled` + `is_partial_history: true` + `history_note`. Only ~10 recent commits fetched → honest lower bound |
| `forensic_confidence_score` (single int) | ⚠️ relocated | Per-topic `forensic_score` in `raw_analysis_payload` + an `authorship_risk` block |
| `topic_risk_flags[]` | ⚠️ relocated | Spread across `authorship_risk.topics` + per-gap `observed_error_patterns.github` |
| `repositories_analyzed`, `analysis_period_days`, `commit_frequency_avg_per_day` | ❌ | Not in pipeline input |
| `commit_message_quality {with_what/with_why/empty%}` | ❌ | `GitHubCommit` has **no message field** — nothing to analyze |
| `ai_detected_segments[]` (per-file AI probability) | ❌ | No file-level detector. Replaced by topic-level `authorship_risk` with explicit "no file-level detection" note |
| When no GitHub | ✅ | `{ "status": "NO_GITHUB_ACCOUNT_LINKED", ... }` |

### `sandbox_telemetry`

| Requested field | Implemented? | Notes |
|---|---|---|
| `total_sessions` | ✅ | |
| `avg_compilation_to_success_ratio` | ✅ | `avg_success_ratio` |
| `avg_error_correction_latency_seconds` | ✅ | |
| `keystroke_burst_detections` | ✅ | |
| `topic_performance[{topic, success, time, error_patterns, notes}]` | ✅ | Emitted **per session** (incl. paste-in suspicion note); not aggregated to `tasks_attempted` per topic |

### `adaptive_quiz_results`

| Requested field | Implemented? | Notes |
|---|---|---|
| `total_quizzes_taken`, `avg_score` | ✅ | |
| `topic_scores[{topic, score, questions_asked}]` | ✅ | Also adds `avg_time_seconds`, `retry_count` |
| per-topic `misconceptions` | ⚠️ relocated | Live in `knowledge_gaps[].misconceptions`, not duplicated here |

### `synthesized_mastery_profile` & `recommendations`

| Requested | Implemented? | Notes |
|---|---|---|
| `overall_mastery_score`, `knowledge_gaps[]`, `strengths[]` | ✅ | **Reuses the canonical gaps/strengths verbatim** so the two layers can never disagree |
| `recommendations` | ✅ | Canonical `{priority_order, general_advice, for_instructor}` shape (not `immediate/short/long_term`) |

---

## Value / semantic differences (same keys, different content)

The implementation does **not** reproduce the hand-authored example *values*:

- **`confidence` is computed, not authored.** A gap the example rated `0.98` comes out ≈`0.81` (full data) or ≈`0.50–0.56` (no GitHub). Direction matches intent; magnitudes differ.
- **`learning_objectives` are templated** (`"Improve <subskill> through traceable examples…"`), not bespoke per-topic sentences. The specific hook lives in `weak_subskills[].recommended_content_focus`.
- **`misconceptions` come from `TOPIC_CATALOG`** (10 topics, 2–3 subskills each) + generic appends — anything outside the catalog falls to a `CS-GEN` stub.
- **`gap_type` is threshold-driven** on `mastery_score`, not multi-signal triangulation.

---

## ❌ Not implemented (and why)

| Capability | Why |
|---|---|
| File-level AI detection (`ai_detected_segments`, per-file `ai_probability`) | KAA has no file-level AST/AI detector. Only topic-level `authorship_risk` |
| Real `total_commits` / `repositories_analyzed` / `commit_frequency` | Only ~10 recent commits fetched; needs a paginated GitHub metrics collector |
| `commit_message_quality` | Commit messages are not part of `GitHubCommit` input schema |
| **Repo-review → diagnostic_report bridge** | `repo_review_jobs` (real review forensics: java level, per-repo findings) is a **separate collection with no code path into `diagnostic_report.github_forensics`**. The forensics section is built from `github_commits` in the `/analyze` request body, not the reviewed repos |
| Internal-key auth on KAA read endpoints | `/analyze` and `/…/latest` are currently **open**; KAA sends `X-Internal-Key` to user-service but doesn't enforce it on its own routes |

---

## Where to see it

- **API:** `POST /analyze` (returns `diagnostic_report` inline) and `GET /api/v1/mastery-profiles/{student_id}/latest` (`data.diagnostic_report`). Internal URL `http://knowledge-analysis:8000`; host `http://localhost:5007`.
- **DB:** `knowledge_analysis.mastery_profiles` — newest doc by `created_at`; expand `diagnostic_report`.
- **Reference instances:** `docs/examples/` (validated payloads + `generate_examples.py` + `SAVED_mastery_profile_document.json`).
- **Frontend:** `/knowledge-assist/mastery` reads `…/latest` and renders gaps/strengths; `diagnostic_report` is in the response but **not yet drawn as a UI panel**.

---

## Bottom line

- **Implemented & saved:** the full downstream-consumption contract (richer than requested, via `weak_subskills`) **plus** the rich forensic/telemetry/quiz report — both in one `mastery_profiles` document, model-validated, tested.
- **Partial by data limit:** GitHub commit totals/forensic depth — flagged honestly as partial, not faked.
- **Not built:** file-level AI detection, commit-message quality, and the `repo_review_jobs` → `diagnostic_report` bridge.
