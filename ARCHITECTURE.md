# Mentora — Knowledge Analysis Agent (KAA)
## System Architecture, Status, and Build Plan

**Project:** R26-SE-30 — Agentic AI-Driven Multi-Agent Tutoring System
**Component:** Knowledge Analysis Agent (KAA)
**Author:** Wijekoon K S M — IT22201232
**Supervisor:** Dr. Darshana Kasthurirathna
**Cluster:** COEAI (Centre of Excellence for AI), SLIIT
**Document version:** 1.0

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Status Legend](#2-status-legend)
3. [Project Context](#3-project-context)
4. [Master System Architecture](#4-master-system-architecture)
5. [KAA Internal Architecture](#5-kaa-internal-architecture)
6. [Request Flow — End-to-End](#6-request-flow--end-to-end)
7. [n8n Removal Decision](#7-n8n-removal-decision)
8. [Diagnostic JSON Payload — Interoperability Contract](#8-diagnostic-json-payload--interoperability-contract)
9. [Component Status Matrix](#9-component-status-matrix)
10. [File-Level Inventory](#10-file-level-inventory)
11. [Specifications for Missing Components](#11-specifications-for-missing-components)
12. [Build Roadmap](#12-build-roadmap)
13. [Validation Strategy](#13-validation-strategy)
14. [Risk Register](#14-risk-register)
15. [Glossary](#15-glossary)

---

## 1. Executive Summary

The KAA is the diagnostic engine of a wider multi-agent tutoring platform. It synthesises three behavioural data streams — adaptive quiz performance, containerised sandbox telemetry, and longitudinal GitHub commit forensics — into a unified Mastery Profile that distinguishes genuine programming knowledge from AI-assisted dependency.

### What is already built (≈ 60 % of KAA scope)
- Full 10-step diagnostic pipeline.
- 40 / 30 / 30 weighted scoring across sandbox, forensic, and quiz dimensions.
- GitHub commit ingestion and Big-Bang detection.
- Ollama (Llama 3) inference plumbing.
- MongoDB persistence layer.
- Authentication, sessions, and audit logging via the user-service.
- Frontend dashboard layouts for all five KAA-facing pages.

### What is still missing (≈ 40 %)
- Containerised sandbox runner with telemetry hooks.
- True Item Response Theory (IRT) quiz engine.
- PII redaction layer for outbound LLM calls.
- WebSocket emitter for live frontend updates.
- KAA-internal dispatcher (replacing the originally planned n8n).
- Frontend wiring — the dashboard pages currently render mock data.
- Empirical validation harnesses (Cohen's κ, F1, load test).

### Localhost feasibility
The full research lifecycle including the N=60 pilot can run on a single laptop. Cloud language in the proposal is aspirational scaling, not a hard requirement.

---

## 2. Status Legend

| Symbol | Meaning |
|---|---|
| ✅ | Done — implemented and wired |
| 🟡 | Partial — exists but is stub, mock, or placeholder |
| 🔨 | To build — planned, scoped, not yet started |
| ❌ | Missing — required by proposal, no implementation |
| ⚪ | Not yours — teammate's stream within R26-SE-30 |

---

## 3. Project Context

### 3.1 Real-world problem
Generative AI tools (Copilot, ChatGPT, Claude) have eroded process-oriented programming education. Students produce syntactically perfect code without internalising the underlying logic — the "illusion of competence". Existing LMS platforms grade outputs (pass/fail) and miss the coding lifecycle entirely.

### 3.2 KAA's role
A behavioural forensic engine that triangulates:
1. **Adaptive Assessment** — LLM-driven IRT quizzes that pivot on detected misconceptions.
2. **Sandbox Telemetry** — compile frequency, error-correction latency, keystroke dynamics.
3. **GitHub Forensics** — commit volatility, diff granularity, refactor velocity, Big-Bang detection.

The output is a multi-dimensional Mastery Profile mapped to SWEBOK competency nodes, plus a Forensic Confidence Score quantifying AI-dependency probability.

### 3.3 Six specific objectives (proposal §2.2)
| # | Objective | Mapped artefact |
|---|---|---|
| 1 | LLM-driven adaptive assessment engine | `services/quiz_engine.py` + IRT module |
| 2 | Containerised sandbox + process telemetry | `services/sandbox-runner/` (new service) |
| 3 | Behavioural forensic module for GitHub | `services/github_analyzer.py` + `github_fetcher.py` |
| 4 | Multi-source synthesis algorithm | `services/pipeline.py` step7 + step8 |
| 5 | Agentic orchestration and JSON schema | `services/dispatcher.py` + `models/payload.py` |
| 6 | Empirical validation of diagnostic precision | `tests/validation/` harness |

### 3.4 Success thresholds
| Dimension | Metric | Target |
|---|---|---|
| Accuracy | Cohen's κ | > 0.80 |
| Integrity | AI-detection F1 | > 0.82 |
| Pedagogy | Mastery gain (pre/post) | +25 % over control |
| Performance | P95 latency | < 5 s |
| Usability | SUS score | > 75 |

---

## 4. Master System Architecture

```
╔═══════════════════════════════════════════════════════════════════════════╗
║                       CLIENT LAYER — Browser                               ║
║         mentora-frontend  (Next 16 + React 19 + Tailwind 4)  :3002         ║
╠═══════════════════════════════════════════════════════════════════════════╣
║  ✅ /login    /signup    /forgot-password                                  ║
║  ✅ DashboardLayout      sidebar, top-nav, auth context                    ║
║  ─────────────────────────────────────────────────────────────────         ║
║  🟡 /knowledge-assist              overview — mock metrics                 ║
║  🟡 /knowledge-assist/sandbox      fake live log stream                    ║
║  🟡 /knowledge-assist/forensics    hard-coded GitHub timeline              ║
║  🟡 /knowledge-assist/mastery      hard-coded topic scores                 ║
║  🟡 /knowledge-assist/assessment   static quiz mock                        ║
║  🔨 src/lib/api/kaa.ts             KAA HTTP client                         ║
║  🔨 src/hooks/useKAASocket.ts      WebSocket consumer                      ║
╚════════════════════╤═══════════════════╤══════════════════════════════════╝
                     │ HTTPS (REST)       │ WSS (live updates)
                     │                    │
┌────────────────────┴────────────────────┴───────────────────────────────┐
│                                                                           │
│  ╔═════════════════════════════════════════════════════════════════════╗ │
│  ║         KAA — Knowledge Analysis Agent  (FastAPI :8000)             ║ │
│  ║         ★ YOUR COMPONENT — also acts as orchestrator ★              ║ │
│  ║                                                                      ║ │
│  ║   ┌───────────────────────────────────────────────────────────────┐ ║ │
│  ║   │  api/                                                          │ ║ │
│  ║   │   ✅ routes.py                /analyze /quiz/generate          │ ║ │
│  ║   │   ✅ github_*_routes.py       GitHub fetch + analyze           │ ║ │
│  ║   │   🔨 telemetry.py             POST /telemetry  (from sandbox) │ ║ │
│  ║   │   🔨 ws.py                    WS  /ws/student/{id}            │ ║ │
│  ║   └───────────────────────────────────────────────────────────────┘ ║ │
│  ║                              │                                       ║ │
│  ║                              ▼                                       ║ │
│  ║   ┌───────────────────────────────────────────────────────────────┐ ║ │
│  ║   │  services/pipeline.py  ✅                                      │ ║ │
│  ║   │  ↳ 10-step pipeline (ingest → ... → output)                    │ ║ │
│  ║   │  ↳ all steps implemented, tests pass                           │ ║ │
│  ║   └───────────────────────────────────────────────────────────────┘ ║ │
│  ║                              │                                       ║ │
│  ║                              ▼                                       ║ │
│  ║   ┌───────────────────────────────────────────────────────────────┐ ║ │
│  ║   │  services/dispatcher.py  🔨 (replaces n8n)                    │ ║ │
│  ║   │   ↳ FastAPI BackgroundTasks                                    │ ║ │
│  ║   │   ↳ POST payload to Content Agent URL                          │ ║ │
│  ║   │   ↳ POST payload to Peer Agent URL                             │ ║ │
│  ║   │   ↳ broadcast payload via WebSocket to frontend                │ ║ │
│  ║   │   ↳ persist payload to Mongo for history                       │ ║ │
│  ║   └───────────────────────────────────────────────────────────────┘ ║ │
│  ║                                                                      ║ │
│  ║   supporting modules                                                 ║ │
│  ║   ✅ quiz_engine        🟡 add real IRT (girth)                    ║ │
│  ║   ✅ github_analyzer    Big-Bang, volatility                        ║ │
│  ║   ✅ github_fetcher     REST via PAT                                ║ │
│  ║   ✅ ollama_client      🔨 wrap with PII redactor                  ║ │
│  ║   ✅ ai_prompt          chain-of-thought prompts                    ║ │
│  ║   🔨 utils/pii.py       redact before LLM call                     ║ │
│  ║   🔨 models/payload.py  Diagnostic JSON schema                      ║ │
│  ╚══════════════════════════════════════════════════════════════════════╝ │
│       ▲                              │                                    │
│       │ telemetry webhook            │ async fan-out                      │
│       │                              │                                    │
└───────┼──────────────────────────────┼────────────────────────────────────┘
        │                              │
        │                              ├──► ⚪ Content Agent  (teammate)
        │                              │      stub if not ready
        │                              │
        │                              └──► ⚪ Peer Agent     (teammate)
        │                                     stub if not ready
        │
┌───────┴───────────────────────────────┐
│  sandbox-runner  (FastAPI :8010)      │  🔨 NEW SERVICE
│  ─────────────────────────────────    │
│  POST /run                             │
│   ↳ spawn ephemeral Docker container   │
│   ↳ exec student code, 5 s timeout     │
│   ↳ no network egress (NFR-01)         │
│   ↳ capture stdout/stderr, attempts,   │
│     keystrokes, error-correction time  │
│   ↳ POST TelemetryEvent → KAA          │
└────────────────────────────────────────┘

   ┌────────────────────────────────┐    ┌────────────────────────┐
   │  MongoDB :27017                │    │  Ollama (host) :11434  │
   │  ✅ mentora_users               │    │  ✅ Llama 3            │
   │  ✅ knowledge_analysis          │    └────────────────────────┘
   │   🔨 diagnostic_payloads        │
   └────────────────────────────────┘    ┌────────────────────────┐
                                          │  GitHub REST API       │
   ┌────────────────────────────────┐    │  ✅ outbound polling   │
   │  user-service :3001 ✅          │    └────────────────────────┘
   │  Auth, JWT, audit (reused)     │
   └────────────────────────────────┘

   Removed from original plan:
   ❌ n8n container, workflows, env config, public webhook tunnels
```

---

## 5. KAA Internal Architecture

```
╔════════════════════════════════════════════════════════════════════════════╗
║   services/knowledge-analysis/app/                                          ║
║   ─────────────────────────────────                                         ║
║                                                                             ║
║   main.py  ✅                                                                ║
║      │                                                                      ║
║      ▼                                                                      ║
║   api/                                                                      ║
║      ✅ routes.py                                                           ║
║      ✅ github_analysis_routes.py                                           ║
║      ✅ github_fetch_analyze_routes.py                                      ║
║      🔨 telemetry.py        (sandbox webhook ingress)                       ║
║      🔨 ws.py               (WebSocket for live UI)                         ║
║                                                                             ║
║      │                                                                      ║
║      ▼                                                                      ║
║   services/pipeline.py  ✅  (10-step orchestrator)                          ║
║      │                                                                      ║
║      ▼                                                                      ║
║   ┌────────────────────────────────────────────────────────────────┐      ║
║   │  STEP-BY-STEP PIPELINE  (services/steps/)                       │      ║
║   │                                                                  │      ║
║   │   ✅ step1_ingest        validate LearnerInput                   │      ║
║   │   ✅ step2_preprocess    normalise quiz / sandbox metrics        │      ║
║   │   ✅ step3_features      derive error-rate features              │      ║
║   │   ✅ step4_analysis      flag issues per topic                   │      ║
║   │   ✅ step5_mode          full vs reduced (no GitHub) mode        │      ║
║   │   ✅ step6_cluster       misconception clustering                │      ║
║   │   ✅ step7_scoring       40 % sandbox + 30 % forensic + 30 % quiz│      ║
║   │   ✅ step8_profile       weak / medium / strong + AI flag        │      ║
║   │   ✅ step9_validation    sanity checks                           │      ║
║   │   ✅ step10_output       Diagnostic JSON Payload                 │      ║
║   └────────────────────────────────────────────────────────────────┘      ║
║      │                                                                      ║
║      │ uses ↓                                                               ║
║      ▼                                                                      ║
║   services/                                                                 ║
║   ┌────────────────────┐  ┌──────────────────────┐  ┌──────────────────┐  ║
║   │  quiz_engine.py    │  │  github_analyzer.py  │  │  ollama_client.py│  ║
║   │ 🟡 small quiz bank │  │ ✅ Big-Bang detect   │  │ ✅ Llama 3 calls │  ║
║   │ 🟡 difficulty proxy│  │ ✅ avg time gap      │  │ 🔨 PII strip wrap│  ║
║   │ 🔨 real θ/b IRT    │  │ ✅ message quality   │  │ 🔨 caching       │  ║
║   │ 🔨 graph link       │  │ ✅ commit volatility │  │                  │  ║
║   │                    │  │ 🟡 refactor velocity │  │                  │  ║
║   └────────────────────┘  └──────────────────────┘  └──────────────────┘  ║
║                                                                             ║
║   ┌────────────────────┐  ┌──────────────────────┐                         ║
║   │ github_fetcher.py  │  │  prompt_builder.py   │                         ║
║   │ ✅ REST via PAT    │  │  ✅                  │                         ║
║   │ 🔨 OAuth2 (FR-01)  │  │                      │                         ║
║   └────────────────────┘  └──────────────────────┘                         ║
║                                                                             ║
║   db/                                core/                                  ║
║   ┌────────────────────┐  ┌──────────────────────┐                         ║
║   │ database.py  ✅    │  │ config.py   ✅       │                         ║
║   │ models.py    ✅    │  │ constants.py ✅      │                         ║
║   └────────────────────┘  └──────────────────────┘                         ║
║                                                                             ║
║   utils/                                                                    ║
║   ┌────────────────────┐                                                   ║
║   │ helpers.py    ✅   │     🔨 pii.py          (NFR-02 PII redactor)     ║
║   │ validators.py ✅   │     🔨 ws_manager.py   (WebSocket connections)   ║
║   └────────────────────┘                                                   ║
║                                                                             ║
║   🔨 services/sandbox/                  (NEW SUBMODULE)                    ║
║      🔨 docker_runner.py                                                    ║
║      🔨 telemetry_collector.py                                              ║
║      🔨 keystroke_capture.py                                                ║
║      🔨 error_correction_tracker.py                                         ║
║                                                                             ║
║   🔨 services/knowledge_graph/          (NEW SUBMODULE)                    ║
║      🔨 swebok_schema.json                                                  ║
║      🔨 graph_loader.py                                                     ║
║                                                                             ║
║   🔨 services/dispatcher.py             (replaces n8n role)                ║
║   🔨 models/payload.py                  (formal Diagnostic JSON schema)    ║
║                                                                             ║
║   tests/                                                                    ║
║   ┌────────────────────┐                                                   ║
║   │ test_pipeline.py 🟡│  basic happy-path                                 ║
║   │ test_ai_prompt 🟡  │                                                   ║
║   │ 🔨 test_github_    │  forensics module proof                           ║
║   │    analyzer.py     │                                                   ║
║   │ 🔨 test_irt.py     │                                                   ║
║   │ 🔨 validation/     │  Cohen's κ, F1, load test harnesses               ║
║   └────────────────────┘                                                   ║
╚════════════════════════════════════════════════════════════════════════════╝
```

---

## 6. Request Flow — End-to-End

The user-facing scenario: a student writes code, hits run, and the dashboard updates with a new mastery diagnosis.

```
  [Student in browser]
        │
        │ ① opens /knowledge-assist/sandbox  ──►  WebSocket connects to KAA /ws
        │
        │ ② submits code  ──►  POST /run on sandbox-runner :8010
        ▼
  ┌──────────────────────────┐
  │  sandbox-runner  🔨      │
  │  spins ephemeral Docker  │
  │  captures telemetry      │
  └────────────┬─────────────┘
               │
               │ ③ POST /telemetry  (TelemetryEvent JSON)
               ▼
  ┌──────────────────────────┐
  │  KAA  ✅                 │
  │   pipeline runs 10 steps │
  │   builds Mastery Profile │
  └────────────┬─────────────┘
               │
               │ ④ generate Diagnostic JSON Payload
               ▼
  ┌──────────────────────────┐
  │  dispatcher.py  🔨        │
  │  (BackgroundTasks)       │
  └────┬────┬────┬────┬──────┘
       │    │    │    │
       │    │    │    └─► ⑤a Mongo: persist payload (history)
       │    │    │
       │    │    └──────► ⑤b WS broadcast → frontend live update
       │    │
       │    └───────────► ⑤c POST → Content Agent (teammate)
       │
       └────────────────► ⑤d POST → Peer Agent    (teammate)
```

Five hops, all under your direct control. Latency budget: pipeline (≈1.5 s) + dispatcher fan-out (≈0.3 s) + WS push (≈0.1 s) ≈ **2 s P95**, comfortably under the 5 s NFR-03 target.

---

## 7. n8n Removal Decision

### Why drop n8n
The proposal named n8n as the orchestrator, but careful reading of Objective 5 shows the **research artefact is the standardised JSON payload contract** — not the tool that delivers it. n8n adds:
- A second orchestration runtime to learn and document
- A self-hosted container with its own auth and persistence
- A network hop adding ~150–300 ms per dispatch
- A single point of failure separate from KAA

### What replaces it
KAA itself becomes the orchestrator using FastAPI's native `BackgroundTasks` for asynchronous fan-out. Three small modules:

1. **`app/services/dispatcher.py`** — fans out to teammate agents via async HTTP, env-configured URLs.
2. **`app/api/ws.py`** — FastAPI WebSocket route pushing payloads to the dashboard.
3. **`app/api/telemetry.py`** — webhook ingress from the sandbox-runner.

Total replacement cost: ~180 LOC.

### Thesis-defensible language
> "We initially considered n8n for inter-agent orchestration but adopted a FastAPI-native dispatch pattern. This preserves the standardised JSON payload contract central to agentic interoperability while reducing deployment topology, eliminating a single point of failure, and improving end-to-end latency for the pilot."

### What to update in the proposal document
- §2.2 Objective 5 — replace "via n8n" with "via FastAPI-native asynchronous dispatch"
- §3.3 Tools and Platforms — remove n8n row, add `httpx` (already in stack)
- §4.1, §4.2 — "Agent Orchestration Layer" diagrams updated to show KAA-internal dispatcher
- Appendix H — rewrite as "FastAPI Dispatcher Logic and JSON Payload Contract"

---

## 8. Diagnostic JSON Payload — Interoperability Contract

This payload is the **research artefact** for Objective 5 and the contract consumed by the Content Agent (LMG), Peer Agent, frontend WebSocket, and Mongo history.

> **⚠️ Contract authority.** The single source of truth is the Pydantic model **`CanonicalMasteryOutput` in `app/models/schemas.py`**, built by `build_canonical_mastery_output()` in `app/services/profile_contract.py`. This document mirrors that model — if the two ever disagree, the model wins and this section is stale (fix it). The earlier `schema_version: "1.0"` shape (flat `topic_scores` map, `ai_dependency`, `remediation_hints`, `swebok_nodes`) was **superseded**; that data now lives under `raw_analysis_payload` for back-compat (see migration note below).

Current schema version: **`kaa-lmg-v1.0`** (constant `MASTERY_PROFILE_SCHEMA_VERSION` in `core/constants.py`).

```json
{
  "schema_version": "kaa-lmg-v1.0",
  "student_id": "STU-2026-0428",
  "session_id": "uuid-v4-or-null",
  "analysis_timestamp": "2026-05-04T10:14:22Z",
  "data_sources": {
    "github": "available",
    "sandbox": "available",
    "quizzes": "available"
  },
  "mastery_profile": {
    "overall_mastery_score": 58.0,
    "knowledge_gaps": [
      {
        "topic": "Recursion",
        "topic_id": "CS101-REC",
        "gap_type": "FUNDAMENTAL_GAP",
        "confidence": 0.95,
        "mastery_score": 41.0,
        "weak_subskills": [
          {
            "subskill": "base case identification",
            "subskill_id": "CS101-REC-BASE",
            "status": "weak",
            "evidence": "quiz score is 20.0; sandbox score is 0.0; observed logical errors",
            "recommended_content_focus": "Practice spotting the terminating condition before writing the recursive step."
          }
        ],
        "known_subskills": [],
        "misconceptions": ["base case identification", "stack frame management"],
        "observed_error_patterns": {
          "github": ["authorship-risk signal from commit or editing pattern"],
          "sandbox": ["logical errors during implementation", "runtime failures during execution"],
          "quizzes": ["low quiz correctness for this topic", "major conceptual misunderstanding signal"]
        },
        "evidence_summary": "Recursion mastery is 41.0/100. Quiz signal 20.0/100. Sandbox signal 0.0/100. GitHub forensic signal 30.0/100. Authorship-risk indicators require live verification before treating submitted code as mastery.",
        "prerequisite_topics": ["Loops", "Functions", "Call Stack"],
        "related_topics": ["Tree Traversal", "Divide and Conquer"],
        "suggested_intervention": {
          "primary": "interactive_tutorial",
          "secondary": ["step_by_step_practice", "debugging_exercise"],
          "difficulty_level": "beginner",
          "estimated_time_minutes": 90,
          "learning_objectives": ["Improve base case identification through traceable examples and independent practice."]
        }
      }
    ],
    "strengths": [
      {
        "topic": "Loops",
        "topic_id": "CS101-LOOP",
        "confidence": 0.96,
        "mastery_score": 95.0,
        "mastery_level": "advanced",
        "evidence_summary": "Loops is currently a strength with mastery 95.0/100. Quiz signal 95.0/100 and sandbox signal 90.0/100. GitHub forensic signal 80.0/100.",
        "known_subskills": [],
        "can_teach_others": true
      }
    ]
  },
  "recommendations": {
    "priority_order": ["Recursion"],
    "general_advice": "Generate learning materials from weak_subskills before broad topic summaries.",
    "for_instructor": "Verify the highest-priority gap with a short live task before marking mastery. Use high-confidence strengths for peer-learning matching where can_teach_others is true."
  },
  "overall_mastery_score": 58.0,
  "knowledge_gaps": ["… same objects as mastery_profile.knowledge_gaps (top-level mirror) …"],
  "strengths": ["… same objects as mastery_profile.strengths (top-level mirror) …"],
  "gap_topic_ids": ["CS101-REC"],
  "raw_analysis_payload": {
    "mode": "full",
    "topic_scores": { "Recursion": { "mastery_score": 0.41, "quiz_score": 0.2, "sandbox_score": 0.5, "forensic_score": 0.6 } },
    "weak_topics": ["Recursion"],
    "medium_topics": ["OOP"],
    "strong_topics": ["Loops"],
    "misconception_clusters": { "AI_Dependency": ["Recursion"] },
    "error_frequency": { "Recursion": { "logical": 0.8, "runtime": 0.3 } },
    "validation": { "data_quality": "high", "confidence": 0.85, "warnings": [] }
  }
}
```

When `data_sources.github == "unavailable"` (Mode B / sandbox-only), the shape is **identical**; only `data_sources.github` flips, `observed_error_patterns.github` is `[]`, `evidence_summary` omits the GitHub line, and `confidence` is scaled down (two of three sources available — see `_confidence()`). Downstream consumers must not branch on key presence; the keys are always present.

### Key contract guarantees
- `schema_version` — string `"kaa-lmg-v1.0"`. Consumers pin and migrate on change. **This is not the old `"1.0"`** — a consumer hard-checking `== "1.0"` will (correctly, loudly) reject the current payload.
- Both `mastery_profile.{overall_mastery_score,knowledge_gaps,strengths}` **and** their top-level mirrors (`overall_mastery_score`, `knowledge_gaps`, `strengths`, `gap_topic_ids`) are emitted. Read either; they reference the same data.
- All mastery/score fields are **0–100 floats** (`overall_mastery_score`, `mastery_score`). The only **0–1 float** is per-item `confidence`. Do not mix the scales.
- `gap_type` ∈ `{FUNDAMENTAL_GAP (<50), PARTIAL_GAP (<75), SURFACE_GAP (<85)}`; thresholds in `profile_contract._gap_type()`.
- `topic_id` / `subskill_id` are stable IDs from `TOPIC_CATALOG` in `core/constants.py` (e.g. `CS101-REC`). These replaced the old `swebok_nodes`.
- `weak_subskills` is the field LMG should drive content from — it pinpoints *which part* of a topic the student fails ("knows loops, but can't do the off-by-one boundary"), not just the topic.
- `data_sources`, `observed_error_patterns.{github,sandbox,quizzes}`, and the top-level mirrors are **always present** even when empty — never key-test, default-read.

#### Migration note — old `schema_version: "1.0"` consumers
The legacy fields were not deleted, only relocated. Map old → new:

| Old `1.0` top-level field | Where it lives now |
|---|---|
| `generated_at` | `analysis_timestamp` |
| `mode` | `raw_analysis_payload.mode` |
| `mastery_profile.overall` (0–1) | `overall_mastery_score` (0–100) — rescale ×100 |
| `mastery_profile.topic_scores` | `raw_analysis_payload.topic_scores` |
| `weak_topics` / `medium_topics` / `strong_topics` | `raw_analysis_payload.*` |
| `misconception_clusters` | `raw_analysis_payload.misconception_clusters` |
| `ai_dependency.{flag,confidence_score,evidence}` | folded into per-gap `observed_error_patterns.github` + `misconceptions`; raw signal in `raw_analysis_payload.misconception_clusters.AI_Dependency` |
| `remediation_hints[]` | `recommendations` + per-gap `suggested_intervention` |
| `swebok_nodes[]` | per-item `topic_id` / `subskill_id` |
| `validation` | `raw_analysis_payload.validation` |

A teammate still coded against `1.0` either re-points to the table above or reads everything from `raw_analysis_payload`, which preserves the old signal verbatim.

### 8.1 `diagnostic_report` companion — rich forensic/telemetry view ✅

The canonical contract above is deliberately lean (topic/subskill diagnosis only). For dashboards and instructor review, `/analyze` now **also** builds a richer companion object — `diagnostic_report` — and embeds it in the **same `mastery_profiles` document** (additive; the canonical fields are untouched).

- Built by `build_diagnostic_report(data, final_output)` in `app/services/diagnostic_report.py` (pure reshaping; no LLM, no pipeline-step changes). Its own `schema_version` is `kaa-forensic-report-v1.0`.
- Sections: `github_forensics` (commit-pattern classification/breakdown, commit-size analysis, refactoring velocity, topic-level `authorship_risk`), `sandbox_telemetry` (per-session success ratio, error patterns, keystroke-burst/paste-in flags), `adaptive_quiz_results` (per-topic scores), `synthesized_mastery_profile` (reuses the canonical `knowledge_gaps`/`strengths` verbatim so the two can never diverge), and `recommendations`.
- **Persisted** via the optional `diagnostic_report=` arg threaded through `save_mastery_profile()` → `build_mastery_profile_document()`; **exposed** in the `POST /analyze` response and inside `GET /api/v1/mastery-profiles/{id}/latest` (`data.diagnostic_report`).
- Tests: `tests/test_diagnostic_report.py` (full suite 20 passing). Reference instances + a regenerator live in `docs/examples/`.

**Honest scope (do not overstate to teammates):**
- GitHub metrics are derived from `LearnerInput.github_commits` passed in the request body. `total_commits` is reported as `commits_sampled` + `is_partial_history: true` — a lower bound, since only ~10 recent commits per repo are fetched.
- **No file-level AI-probability** is produced; authorship risk is a topic-level signal only.
- **Not yet bridged to `repo_review_jobs`.** The real repo-review forensics (java level, per-repo findings) live in their own collection and do **not** flow into `diagnostic_report.github_forensics` today — that bridge is unbuilt. See §9.

---

## 9. Component Status Matrix

### Frontend
| Item | Status | Notes |
|---|---|---|
| Auth pages (login/signup/forgot) | ✅ | |
| DashboardLayout | ✅ | Sidebar + nav |
| `/knowledge-assist` overview | 🟡 | Mock metrics, hard-coded cards |
| `/knowledge-assist/sandbox` | 🟡 | Fake log feed, fake integrity score |
| `/knowledge-assist/forensics` | 🟡 | Hard-coded GitHub timeline |
| `/knowledge-assist/mastery` | 🟡 | Reads **real** saved profile via `GET /api/v1/mastery-profiles/{id}/latest` (free-form student-ID lookup); renders gaps/strengths. `diagnostic_report` arrives in the response but has **no render panel yet** |
| `/knowledge-assist/assessment` | 🟡 | Static quiz mock |
| KAA HTTP client | 🔨 | `src/lib/api/kaa.ts` |
| WebSocket hook | 🔨 | `src/hooks/useKAASocket.ts` |

### KAA Backend
| Module | Status | Notes |
|---|---|---|
| FastAPI app entry (`main.py`) | ✅ | |
| Routes (`api/routes.py`) | ✅ | `/analyze` (now also builds + returns `diagnostic_report`), `/quiz/generate`, `/health`, `/demo` |
| Canonical contract (`profile_contract.py` / `CanonicalMasteryOutput`) | ✅ | Saved to `mastery_profiles`; see §8 |
| `diagnostic_report` builder (`services/diagnostic_report.py`) | ✅ | Rich forensic/telemetry/quiz companion; embedded in `mastery_profiles`; exposed via `/analyze` + `/…/latest`; see §8.1 |
| Mastery-profile store (`mastery_profile_store.py`) | ✅ | `save_mastery_profile` / `get_latest_mastery_profile`; `mastery_profiles` collection + indexes |
| Repo-review → mastery-profile bridge | 🔨 | **Unbuilt.** `repo_review_jobs` forensics do not feed `diagnostic_report.github_forensics` yet (uses request-body commits) |
| Internal-key auth on KAA read endpoints | 🔨 | KAA *sends* `X-Internal-Key` to user-service but does **not** enforce it on its own routes; `/analyze` + `/…/latest` are open |
| GitHub routes | ✅ | Fetch + analyse; repo review persists to `repo_review_jobs` |
| Telemetry route | 🔨 | `api/telemetry.py` |
| WebSocket route | 🔨 | `api/ws.py` |
| 10-step pipeline | ✅ | All steps implemented |
| `quiz_engine.py` (real IRT) | 🟡 | Replace placeholder with `girth` 2-PL |
| `github_analyzer.py` | ✅ | Big-Bang, volatility, message quality |
| `github_fetcher.py` (PAT) | ✅ | OAuth2 still 🔨 |
| `ollama_client.py` | ✅ | Async + sync, health check |
| `prompt_builder.py` / `ai_prompt.py` | ✅ | |
| Mongo persistence | ✅ | |
| Dispatcher | 🔨 | `services/dispatcher.py` |
| Diagnostic payload schema | 🔨 | `models/payload.py` |
| PII redactor | 🔨 | `utils/pii.py` |
| WebSocket manager | 🔨 | `utils/ws_manager.py` |
| Sandbox runner service | 🔨 | New `services/sandbox-runner/` |
| SWEBOK Knowledge Graph | 🔨 | New `services/knowledge_graph/` |

### Validation
| Item | Status | Notes |
|---|---|---|
| Pipeline tests | 🟡 | Happy path only |
| AI prompt tests | 🟡 | |
| GitHub analyzer tests | 🔨 | |
| IRT tests | 🔨 | |
| Cohen's κ harness | 🔨 | |
| F1 / Precision / Recall harness | 🔨 | |
| Load test (50 concurrent) | 🔨 | Locust or k6 |
| SUS survey instrument | 🟡 | In proposal Appendix A |

### Group dependencies
| Service | Status | Owner |
|---|---|---|
| `gateway` | ⚪ README only | Teammate |
| `assessment-agent` | ⚪ README only | Teammate |
| `peer-learning` | ⚪ README only | Teammate |
| `learning-generator` | ⚪ README only | Teammate |
| `user-service` | ✅ Full Node.js implementation | Reused as-is |

---

## 10. File-Level Inventory

Current state of `services/knowledge-analysis/`:

```
knowledge-analysis/
├── Dockerfile                   ✅
├── requirements.txt             ✅
├── README.md                    ✅
├── KAA_BACKEND_DEVELOPMENT_GUIDE.md  ✅
├── app/
│   ├── main.py                  ✅
│   ├── api/
│   │   ├── routes.py            ✅
│   │   ├── github_analysis_routes.py        ✅
│   │   ├── github_fetch_analyze_routes.py   ✅
│   │   ├── telemetry.py         🔨 NEW
│   │   └── ws.py                🔨 NEW
│   ├── core/
│   │   ├── config.py            ✅
│   │   ├── constants.py         ✅
│   │   └── github_analysis_config.py        ✅
│   ├── db/
│   │   ├── database.py          ✅
│   │   └── models.py            ✅
│   ├── models/
│   │   ├── schemas.py           ✅
│   │   └── payload.py           🔨 NEW
│   ├── services/
│   │   ├── pipeline.py          ✅
│   │   ├── quiz_engine.py       🟡 needs IRT
│   │   ├── github_analyzer.py   ✅
│   │   ├── github_fetcher.py    ✅
│   │   ├── ollama_client.py     ✅
│   │   ├── prompt_builder.py    ✅
│   │   ├── ai_prompt.py         ✅
│   │   ├── integration_example.py           ✅
│   │   ├── dispatcher.py        🔨 NEW
│   │   ├── sandbox/             🔨 NEW SUBMODULE
│   │   │   ├── docker_runner.py
│   │   │   ├── telemetry_collector.py
│   │   │   ├── keystroke_capture.py
│   │   │   └── error_correction_tracker.py
│   │   ├── knowledge_graph/     🔨 NEW SUBMODULE
│   │   │   ├── swebok_schema.json
│   │   │   └── graph_loader.py
│   │   └── steps/
│   │       ├── step1_ingest.py        ✅
│   │       ├── step2_preprocess.py    ✅
│   │       ├── step3_features.py      ✅
│   │       ├── step4_analysis.py      ✅
│   │       ├── step5_mode.py          ✅
│   │       ├── step6_cluster.py       ✅
│   │       ├── step7_scoring.py       ✅
│   │       ├── step8_profile.py       ✅
│   │       ├── step9_validation.py    ✅
│   │       └── step10_output.py       ✅
│   └── utils/
│       ├── helpers.py           ✅
│       ├── validators.py        ✅
│       ├── pii.py               🔨 NEW
│       └── ws_manager.py        🔨 NEW
└── tests/
    ├── conftest.py              ✅
    ├── test_pipeline.py         🟡
    ├── test_ai_prompt.py        🟡
    ├── test_github_analyzer.py  🔨 NEW
    ├── test_irt.py              🔨 NEW
    └── validation/              🔨 NEW
        ├── kappa_harness.py
        ├── f1_harness.py
        └── load_test.py
```

---

## 11. Specifications for Missing Components

### 11.1 sandbox-runner service
**Location:** `services/sandbox-runner/`
**Tech:** FastAPI + Docker SDK for Python
**Purpose:** Execute student code in an isolated container, collect process telemetry, emit a `TelemetryEvent` to KAA.

**Endpoints:**
- `POST /run` — body: `{language, source, student_id, session_id, keystroke_log}`
- `GET /health`

**Container constraints (NFR-01):**
- 5 s CPU timeout
- 256 MB memory cap
- `network_mode: none` — no egress
- ephemeral, removed after run
- run as non-root user
- read-only filesystem except `/tmp`

**TelemetryEvent emitted to KAA:**
```json
{
  "session_id": "...",
  "student_id": "...",
  "topic": "Recursion",
  "compile_attempts": 12,
  "runtime_errors": 5,
  "syntax_errors": 8,
  "logical_errors": 4,
  "time_to_success_seconds": 320,
  "error_correction_latency": 2.1,
  "keystroke_burst_score": 0.82,
  "lines_of_code": 45,
  "stdout_sample": "...",
  "stderr_sample": "..."
}
```

### 11.2 dispatcher.py
**Location:** `app/services/dispatcher.py`
**Purpose:** Async fan-out of Diagnostic JSON Payload.

**Public API:**
```python
async def dispatch(payload: DiagnosticPayload) -> None:
    """Fan-out: persist + WS broadcast + downstream agents."""
```

**Behaviour:**
1. Persist to Mongo `diagnostic_payloads` collection.
2. Broadcast via `ws_manager` to all connected sockets for `student_id`.
3. POST to `CONTENT_AGENT_URL` (env), `PEER_AGENT_URL` (env) — best-effort, log failures.
4. All steps run concurrently via `asyncio.gather` with timeout.

**Env vars:**
- `CONTENT_AGENT_URL` (optional, default `""` = skip)
- `PEER_AGENT_URL` (optional, default `""` = skip)
- `DISPATCHER_TIMEOUT_SECONDS` (default 5)

### 11.3 pii.py
**Location:** `app/utils/pii.py`
**Purpose:** Strip PII before any outbound LLM call (NFR-02).

**Public API:**
```python
def redact(text: str) -> str:
    """Redact student IDs, emails, names, phone numbers, repo URLs."""
```

**Patterns:**
- Student IDs (`ITxxxxxxxx`, `ENxxxxxxxx` etc.)
- Emails (RFC 5322 simplified)
- Phone numbers (international + Sri Lankan)
- GitHub repo URLs (replace with `<repo>`)
- Common name lists (optional, false positives risky)

**Used in:** `ollama_client.generate()` wrapper.

### 11.4 IRT quiz engine
**Location:** `app/services/quiz_engine.py`
**Library:** `girth` (2-PL model)
**Purpose:** Replace placeholder difficulty calculation with proper IRT.

**Concepts:**
- `θ` (theta) — student ability, updated per response.
- `b` (item difficulty) — calibrated per question.
- `a` (item discrimination) — calibrated per question.
- `P(correct | θ, a, b) = 1 / (1 + e^(-a(θ-b)))`

**Public API:**
```python
def generate_quiz(topic: str, theta: float) -> Quiz:
    """Pick item with b closest to current theta."""

def update_theta(theta: float, item: Quiz, correct: bool) -> float:
    """MLE update of student ability after response."""
```

### 11.5 Knowledge Graph schema
**Location:** `app/services/knowledge_graph/swebok_schema.json`
**Purpose:** Map topic IDs to SWEBOK competency nodes (Appendix G).

**Format:**
```json
{
  "nodes": [
    {"id": "KA-CS-Loops", "name": "Loop Structures", "parent": "KA-CS-Iteration"},
    {"id": "KA-DS-Recursion", "name": "Recursion", "parent": "KA-DS-Algorithms"}
  ],
  "edges": [
    {"from": "KA-CS-Loops", "to": "KA-DS-Recursion", "type": "prerequisite"}
  ]
}
```

A flat JSON file is sufficient for the pilot; Neo4j is over-engineering for N=60.

---

## 12. Build Roadmap

Project month numbering follows proposal §8.2. Today is approximately **end of M2** (project started March 2026).

### Phase 1 — Requirements baseline (M1–M2) — done
- Tech stack lockdown
- Initial pipeline scaffold
- Auth + dashboard layout
- GitHub fetcher + analyzer

### Phase 2 — MVP development (M3–M6) — current focus
| Sprint | Weeks | Deliverable |
|---|---|---|
| 1 | 2 | sandbox-runner service skeleton; `/run` endpoint with Docker SDK |
| 2 | 1 | Sandbox telemetry capture (compile, errors, latency, keystroke burst) |
| 3 | 1 | `app/api/telemetry.py` ingress + integration test |
| 4 | 1 | `app/utils/pii.py` + wrap into `ollama_client` |
| 5 | 1 | `app/models/payload.py` + `app/services/dispatcher.py` |
| 6 | 1 | `app/api/ws.py` + `utils/ws_manager.py` |
| 7 | 1 | Real IRT quiz engine using `girth` |
| 8 | 2 | Frontend wiring — replace mocks on all 5 dashboard pages |
| 9 | 1 | Frontend WebSocket hook + live mastery map |
| 10 | 1 | End-to-end smoke test on localhost |

### Phase 3 — System integration (M7–M9)
- Coordinate with teammates' Content / Peer agents (provide stub HTTP servers if late)
- Diagnostic payload contract finalised and published
- SWEBOK schema integrated into pipeline output
- Frontend cohort dashboard for instructors (optional, distinction-tier)
- Performance tuning to hit P95 < 5 s

### Phase 4 — Validation (M10–M12)
- Recruit pilot cohort (N = 60, A/B split)
- Run 8-week curriculum with treatment vs control
- Compute Cohen's κ vs expert audits
- Compute F1 / Precision / Recall for AI-dependency detection
- Run load test (50 concurrent users, Locust on localhost)
- Conduct SUS survey (Appendix A instrument)
- Write thesis chapters 4–6 (results, discussion, conclusion)

---

## 13. Validation Strategy

### 13.1 Diagnostic accuracy — Cohen's κ
- Cohort: N = 40 students stratified by year and prior performance
- Two senior lecturers blind-review repositories and sandbox sessions
- Compute κ between AI verdict and human consensus
- Target: κ > 0.80

### 13.2 AI-dependency detection — Precision / Recall / F1
- Synthetic ground truth: students who self-report AI usage in surveys
- Plus: instructor-flagged Big-Bang commits during cohort observation
- Targets: Precision > 0.85, Recall > 0.80, F1 > 0.82

### 13.3 Comparative learning outcomes — A/B test
- N = 60, randomised
- Control (n=30): standard pass/fail feedback (HackerRank-style)
- Treatment (n=30): full KAA with personalised remediation
- 8-week programming curriculum
- Pre / post concept inventory test (SWEBOK-derived)
- Targets: +25 % gain in post-test, –30 % time-to-mastery on Recursion / BST

### 13.4 Performance
- Locust on localhost, ramp to 50 concurrent virtual users
- Measure P95, P99 latency for `/analyze`
- Target: P95 < 5 s

### 13.5 Usability — SUS
- Standard SUS questionnaire administered at end of pilot
- Plus 5 domain-specific questions (Appendix A)
- Target: SUS > 75

---

## 14. Risk Register

| ID | Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|---|
| R-01 | LLM API downtime | High | Low | Local Ollama Llama 3 — already chosen, no external API dependency |
| R-02 | GitHub rate limits | Medium | Medium | Aggressive metadata caching; polling rather than per-request fetch |
| R-03 | Student resistance ("surveillance") | Medium | Medium | Frame as supportive scaffolding; explicit opt-in; non-punitive policy |
| R-04 | PII leakage to LLM | Critical | Low | `utils/pii.py` mandatory wrapper; localhost-only LLM eliminates external exposure |
| R-05 | Teammate agents not delivered on time | High | Medium | KAA emits payload independent of consumers; stub agents for demo |
| R-06 | Pilot recruitment shortfall | High | Medium | Engage instructors early; offer participation incentives (proposal §7.2) |
| R-07 | Sandbox container security escape | Critical | Low | `network_mode: none`, read-only FS, non-root, resource caps |
| R-08 | LLM hallucination in diagnosis | Medium | Medium | Multi-factor evidence rule: only flag gap if sandbox AND quiz both fail |
| R-09 | Performance ceiling on laptop hardware | Medium | Medium | Document hardware envelope honestly in §3.7; degrade to sequential mode if needed |
| R-10 | Schema drift between agents | Medium | Low | `schema_version` field + compatibility tests in `tests/validation/` |

---

## 15. Glossary

| Term | Definition |
|---|---|
| KAA | Knowledge Analysis Agent — this component |
| MATS | Multi-Agent Tutoring System — the wider R26-SE-30 project |
| ITS | Intelligent Tutoring System (the prior art class) |
| IRT | Item Response Theory — psychometric model for adaptive testing |
| SWEBOK | Software Engineering Body of Knowledge — competency taxonomy |
| Big-Bang commit | A massive, polished commit lacking incremental history; suspect AI-generated |
| Commit Volatility | Multi-faceted metric: frequency, granularity, temporal distribution |
| Forensic Confidence Score | Continuous 0–1 score quantifying AI-dependency probability |
| Diagnostic JSON Payload | The standardised inter-agent contract; KAA's primary research artefact |
| TelemetryEvent | Sandbox-emitted event capturing one student execution session |
| Mastery Profile | Topic-level mastery scores plus weak/medium/strong classification |
| Productive Struggle | Pedagogical concept: difficulty necessary for neural encoding |
| Cognitive Offloading | Delegating mental work to AI tools; the core problem this project addresses |
| Illusion of Competence | Student mistakes AI fluency for own skill — metacognitive failure |
| DSR | Design Science Research — the methodology used (proposal §3.1) |

---

## Document maintenance

This document is the single source of truth for KAA architecture and progress. Update the status legend symbols inline as components move from 🔨 to ✅. Re-version the document on major architectural changes (e.g. if a teammate adds another agent that consumes the Diagnostic JSON Payload).

**Last updated:** 2026-05-04
