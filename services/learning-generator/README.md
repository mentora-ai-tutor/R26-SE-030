# MENTORA - Learning Material Generator (LMG) Service

**Author:** Jayarathna S.K.N.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Technology Stack](#technology-stack)
- [Scenario & Workflow](#scenario--workflow)
- [Backend Service](#backend-service)
  - [Project Structure](#project-structure)
  - [API Endpoints](#api-endpoints)
  - [Database Models](#database-models)
  - [Services & Business Logic](#services--business-logic)
  - [Middleware](#middleware)
  - [Environment Configuration](#environment-configuration)
  - [Docker Setup](#docker-setup)
- [Frontend Application](#frontend-application)
  - [Pages & Routes](#pages--routes)
  - [Components](#components)
  - [API Clients](#api-clients)
- [Integration Architecture](#integration-architecture)
- [API Testing](#api-testing)

---

## Overview

The **Learning Material Generator (LMG)** is a core microservice within the MENTORA AI-powered personalized learning platform. It provides an end-to-end pipeline for generating, delivering, and tracking adaptive learning materials tailored to individual student knowledge gaps identified through mastery profiling.

The system uses an **Agentic AI pipeline** orchestrated by n8n, powered by local LLM inference (Ollama + `qwen2.5-coder:7b`), to autonomously generate structured lesson content, assessments, and interactive exercises. Two AI agents evaluate and validate each generated material before delivery.

Before the pipeline is triggered, a **Concept-Graph Coverage-and-Prerequisite Layer** preprocesses every submitted mastery profile. It resolves free-text knowledge gaps to canonical Java concept-graph nodes, walks the prerequisite closure to surface implicit (blocking) prerequisites, tracks per-student concept coverage, and enriches the n8n payload with the augmented gap list.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        FRONTEND (Next.js)                        │
│              Port 3000 · React 19 · TypeScript · Tailwind        │
│                                                                  │
│  ┌──────────┐ ┌──────────────┐ ┌──────────┐ ┌────────────────┐  │
│  │ Overview  │ │Knowledge Gaps│ │ Materials │ │ Code Workspace │  │
│  │ Dashboard │ │   Analysis   │ │  Gallery  │ │  (Sandbox +AI) │  │
│  └─────┬────┘ └──────┬───────┘ └─────┬────┘ └───────┬────────┘  │
│        └──────────────┴───────────────┴──────────────┘           │
└──────────────────────────────┬───────────────────────────────────┘
                               │ HTTP (JWT Auth)
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                    LMG SERVICE (Express.js)                       │
│                   Port 5012 · Node.js 20+                        │
│                                                                  │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐           │
│  │ Profile  │ │Material  │ │  Agent   │ │ Progress │           │
│  │Controller│ │Controller│ │Controller│ │Controller│           │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘           │
│       │             │            │             │                  │
│  ┌────┴─────┐ ┌────┴─────┐ ┌───┴──────┐ ┌───┴──────┐          │
│  │ n8n Svc  │ │Material  │ │JobTracker│ │ UserSvc  │          │
│  │          │ │  Service  │ │ Service  │ │  Client  │          │
│  └────┬─────┘ └──────────┘ └────┬─────┘ └────┬─────┘          │
│       │                         │              │                │
│  ┌────┴─────────┐               │              │                │
│  │ ConceptGraph │               │              │                │
│  │  Service     │               │              │                │
│  │ (resolve/    │               │              │                │
│  │  close/      │               │              │                │
│  │  coverage/   │               │              │                │
│  │  augment)    │               │              │                │
│  └──────────────┘               │              │                │
└───────┼─────────────────────────┼──────────────┼────────────────┘
        │                         │              │
        ▼                         │              ▼
┌───────────────┐                 │     ┌─────────────────┐
│  n8n Engine   │                 │     │  User Service    │
│  Port 5678    │                 │     │  Port 3001       │
│  (Workflows)  │                 │     │  (Auth/Students) │
└───────┬───────┘                 │     └─────────────────┘
        │ (HTTP)                  │
        ▼                         │
┌───────────────┐                 │
│    Ollama     │                 │
│  Port 11434   │                 │
│  qwen2.5-     │                 │
│  coder:7b     │                 │
└───────┬───────┘                 │
        │                         │
        ▼                         ▼
┌──────────────────────────────────────────────────────────────────┐
│                    MongoDB Atlas (Cloud)                          │
│                   Database: mentora_lmg                           │
│                                                                  │
│  mastery_profiles │ generation_jobs │ learning_materials          │
│  student_progress │ model_comparison_logs │ concept_graph_nodes     │
└──────────────────────────────────────────────────────────────────┘
```

---

## Technology Stack

### Backend

| Category | Technology | Purpose |
|----------|-----------|---------|
| **Runtime** | Node.js 20+ | Server runtime environment |
| **Framework** | Express.js 4.18 | HTTP server & routing |
| **Database** | MongoDB Atlas + Mongoose 8 | Cloud database & ODM |
| **Validation** | Joi 17 | Request validation |
| **Auth** | JWT (via User Service) | Token-based authentication |
| **Security** | Helmet 7, CORS, Rate Limiting | HTTP security |
| **Logging** | Winston 3, Morgan 1 | Structured & HTTP logging |
| **HTTP Client** | Axios 1.6 | Inter-service communication |
| **Workflow** | n8n | AI pipeline orchestration |
| **LLM** | Ollama + qwen2.5-coder:7b | Local LLM inference |
| **Embeddings** | Ollama + nomic-embed-text | Concept-graph description embeddings (768-dim) |
| **Container** | Docker (Alpine) | Containerization |
| **Linting** | ESLint 8 | Code quality |

### Frontend

| Category | Technology | Purpose |
|----------|-----------|---------|
| **Framework** | Next.js 16 (App Router) | React meta-framework |
| **UI Library** | React 19 | Component framework |
| **Language** | TypeScript | Type safety |
| **Styling** | Tailwind CSS | Utility-first styling |
| **Components** | shadcn/ui | Pre-built UI components |
| **Code Editor** | Custom textarea-based editor | In-browser code editing |
| **State** | React hooks + sessionStorage | Client-side state persistence |

---

## Scenario & Workflow

### End-to-End Learning Generation Flow

```
1. STUDENT ASSESSMENT
   Student completes a quiz/assessment → System analyzes performance
              │
              ▼
2. MASTERY PROFILE SUBMISSION
   Frontend calls POST /api/mastery/submit with knowledge gaps
   ├── Gap types: FUNDAMENTAL_GAP | PARTIAL_GAP | SURFACE_GAP
   ├── Each gap includes: topic, confidence, misconceptions, error patterns
   └── Backend saves MasteryProfile → Creates GenerationJob (status: queued)
              │
              ▼
2b. CONCEPT-GRAPH GATE (preprocessing, fail-open)
    Before triggering n8n, the service:
    ├── Resolves each gap to a canonical concept-graph node
    │   (Tier 1 exact/alias → Tier 2 embedding → Tier 3 LLM)
    ├── Walks the prerequisite closure of resolved gaps
    │   (MASTERED stops, GAP keeps walking, UNKNOWN → unverified)
    ├── Computes per-student concept coverage (totalNodes/coveredNodes/coveragePct)
    ├── Calls augmentGaps() ONCE to produce the augmented gap list:
    │   ├── Injects implicit (blocking) prerequisites into the list
    │   └── The same effectiveGaps list is reused for BOTH the n8n payload
    │       AND the GenerationJob counters (gaps_total/gaps_queued) — no drift
    └── Persists resolution + augmented_profile (fail-open: on error, proceeds
        with the original gaps untouched)
              │
              ▼
3. n8n WORKFLOW TRIGGER
   LMG Service POSTs to n8n webhook /webhook/learner-profile
   └── Sends profile data + job metadata + webhook secret
       (knowledge_gaps now the augmented list from the concept-graph gate;
        the job also persists gap_topic_ids so completion tracking matches)
              │
              ▼
4. AGENTIC AI PIPELINE (n8n)
   ┌─────────────────────────────────────────────┐
   │  a) LLM generates lesson content per gap     │
   │     (Introduction, Concepts, Guide, Examples,│
   │      Common Mistakes, Debugging Exercise)     │
   │                                               │
   │  b) LLM generates assessment per gap          │
   │     (Quiz, Practice Challenge, Self-Check)    │
   │                                               │
   │  c) Quality Review Agent (10 checks, 0-100)  │
   │     Auto-retry/patch if score < threshold     │
   │                                               │
   │  d) Content Validation Agent (7 checks)       │
   │     Auto-patch identified issues              │
   └─────────────────────────────────────────────┘
              │
              ▼
5. MATERIAL DELIVERY
   n8n calls back to LMG webhooks:
   ├── POST /api/webhooks/n8n/material     (single material)
   ├── POST /api/webhooks/n8n/material/batch (batch delivery)
   └── POST /api/webhooks/n8n/complete      (workflow done)
              │
              ▼
6. JOB TRACKING (Real-time)
   JobTrackerService uses MongoDB Change Streams + polling
   └── Auto-syncs job counters → transitions: processing → completed
              │
              ▼
7. STUDENT LEARNING EXPERIENCE
   Frontend renders structured material:
   ├── Step-by-step guided learning path
   ├── Interactive code editor with execution
   ├── AI-powered insights ("Explain Simpler", "Real-life Analogy")
   ├── Quiz with scoring and mastery achievement
   └── Progress tracking (persisted to backend)
              │
              ▼
8. CODE SANDBOX (Optional)
   Standalone Java workspace with:
   ├── Code execution + AI feedback
   ├── Inline code explanation (select text)
   ├── Error fixing with AI suggestions
   ├── Code review with annotations
   ├── Concept flashcard generation
   └── JUnit test generation
```

### Gap Types

| Type | Description |
|------|-------------|
| `FUNDAMENTAL_GAP` | Missing core concepts that prerequisites depend on |
| `PARTIAL_GAP` | Partially understood topics with specific weak areas |
| `SURFACE_GAP` | Superficial understanding needing deeper practice |

---

## Backend Service

### Project Structure

```
learning-generator/
├── server.js                          # Entry point: bootstraps app, graceful shutdown
├── src/
│   ├── app.js                         # Express app: middleware, routes, error handlers
│   ├── config/
│   │   ├── db.js                      # MongoDB connection manager
│   │   └── env.js                     # Centralized environment config
│   ├── controllers/
│   │   ├── profile.controller.js      # Mastery profile submission & retrieval
│   │   ├── material.controller.js     # Learning material CRUD & stats
│   │   ├── agent.controller.js        # Job management, health checks, retry
│   │   ├── progress.controller.js     # Student progress tracking
│   │   ├── conceptGraph.controller.js # Concept coverage & seed endpoints
│   │   └── webhook.controller.js      # n8n callback handlers
│   ├── services/
│   │   ├── n8n.service.js             # HTTP client for n8n orchestration
│   │   ├── material.service.js        # Material query building & analytics
│   │   ├── conceptGraph.service.js    # Concept-graph resolution, closure, coverage
│   │   ├── userService.client.js      # HTTP client for User Service (auth)
│   │   └── jobTracker.service.js      # Background job sync (Change Streams)
│   ├── middleware/
│   │   ├── auth.middleware.js          # JWT verification via User Service
│   │   ├── error.middleware.js         # Global error handler
│   │   ├── validate.middleware.js      # Joi request validation
│   │   └── webhook.middleware.js       # Webhook secret validation
│   ├── models/
│   │   ├── MasteryProfile.js          # Student mastery analysis
│   │   ├── GenerationJob.js           # Async job tracking
│   │   ├── LearningMaterial.js        # Generated content
│   │   ├── ConceptGraphNode.js        # Concept-graph nodes (§3.1 schema)
│   │   ├── StudentProgress.js         # Step-by-step progress
│   │   └── AgentLog.js                # Model comparison logs
│   ├── routes/
│   │   ├── profile.routes.js          # /api/mastery/*
│   │   ├── material.routes.js         # /api/materials/*
│   │   ├── agent.routes.js            # /api/agent/*
│   │   ├── progress.routes.js         # /api/progress/*
│   │   ├── conceptGraph.routes.js     # /api/concept-graph/*
│   │   └── webhook.routes.js          # /api/webhooks/n8n/*
│   └── utils/
│       ├── apiResponse.js             # Standardized JSON responses
│       ├── logger.js                  # Winston logger
│       ├── ServiceError.js            # Custom error class
│       └── validationSchemas.js       # Joi schemas for all endpoints
├── scripts/
│   └── seedConceptGraph.js            # Seeds 42 nodes + embeddings via Ollama
├── seed/
│   └── java_oop_graph.json            # 42-node Java OOP concept graph (spec §3/§4)
├── test/
│   ├── conceptGraph.service.test.js   # Unit tests: resolution tiers, closure, BFS
│   ├── conceptGraph.integration.test.js # Fail-open flow, escalation, empty graph
│   ├── seedCycleDetection.test.js     # Seed acyclicity + validation rejection cases
│   └── profileJobCounting.test.js     # Augmented gap counting → GenerationJob counters
├── docs/
│   ├── N8N_WORKFLOW_API.md            # n8n integration docs
│   └── postman.json                   # Full Postman collection
├── postman/
│   ├── LMG_Service.postman_collection.json
│   ├── LMG_Service.postman_environment.json
│   ├── Concept_Graph_Seed.postman_collection.json  # Seeds 42 nodes via API
│   └── N8N_Integration.postman_collection.json
├── n8n/
│   ├── LMG_PP1-v19-fixed.json        # n8n workflow definition (V19)
│   └── LMG_PP2_test_01_concept_graph_enriched.json # V2 enriched workflow (concept-graph
│                                                   #  layer: generation_source, concept_context,
│                                                   #  resolution_method, prerequisite_reason)
├── Dockerfile
├── package.json
├── .env.example
└── .eslintrc.json
```

### API Endpoints

#### Health Check (Public)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Service health status |

#### Mastery Profile Routes (`/api/mastery`) — Protected

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/mastery/submit` | Submit mastery profile. Creates job + triggers n8n. Returns `202` with `job_id` |
| `GET` | `/api/mastery/:studentId` | Get latest mastery profile |
| `GET` | `/api/mastery/:studentId/history` | Paginated profile history (`?page=&limit=`) |

#### Learning Material Routes (`/api/materials`) — Protected

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/materials/:studentId` | List materials with filters (`?topic=&gap_type=&status=&page=&limit=&sort=&order=`) |
| `GET` | `/api/materials/:studentId/topics` | Distinct topics with counts & avg quality scores |
| `GET` | `/api/materials/:studentId/stats` | Material statistics (gap distribution, quality scores) |
| `GET` | `/api/materials/:studentId/topic/:topicId` | Materials for a specific topic |
| `GET` | `/api/materials/item/:materialId` | Single material (supports ObjectId & `material_id`) |
| `DELETE` | `/api/materials/item/:materialId` | Soft-delete (sets `quality_flags.deleted`) |

#### Agent Routes (`/api/agent`) — Protected

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/agent/logs/:studentId` | Paginated agent scoring logs |
| `GET` | `/api/agent/jobs/:jobId` | Generation job status |
| `PATCH` | `/api/agent/jobs/:jobId` | Manually update job status |
| `POST` | `/api/agent/jobs/:jobId/complete` | Force-complete job (checks actual materials) |
| `GET` | `/api/agent/jobs/student/:studentId` | Last 10 jobs for a student |
| `GET` | `/api/agent/stats/global` | Global agent statistics |
| `GET` | `/api/agent/health` | Full dependency health (MongoDB, User Service, n8n, Ollama) |
| `POST` | `/api/agent/retry/:materialId` | Re-trigger n8n for a failed material |

#### Progress Routes (`/api/progress`) — Protected

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/progress/student/:studentId` | All progress records with topic info |
| `GET` | `/api/progress/student/:studentId/stats` | Completion %, avg quiz score |
| `GET` | `/api/progress/material/:materialId` | Progress for specific material |
| `PUT` | `/api/progress/material/:materialId` | Update step completion, quiz score, active step |

#### Concept Graph Routes (`/api/concept-graph`) — Protected

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/concept-graph/coverage/:studentId` | Concept coverage (`?category=OOP`). Returns `{ totalNodes, coveredNodes, coveragePct, implicitGapsCount, unverifiedCount }` |
| `POST` | `/api/concept-graph/seed` | Seed the concept graph from a body array of nodes. Validates acyclicity, computes embeddings via Ollama, idempotent upsert. Returns `{ nodeCount, upserted, modified, matched }` |

#### Webhook Routes (`/api/webhooks/n8n`) — Protected by Webhook Secret

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/webhooks/n8n/material` | Receive single material from n8n |
| `POST` | `/api/webhooks/n8n/material/batch` | Receive batch of materials |
| `POST` | `/api/webhooks/n8n/job/status` | Receive job status update |
| `POST` | `/api/webhooks/n8n/profile` | Receive mastery profile callback |
| `POST` | `/api/webhooks/n8n/complete` | Workflow completion signal |

### Database Models

#### `mastery_profiles` Collection

```javascript
{
  student_id: ObjectId,           // indexed
  analysis_timestamp: Date,
  overall_mastery_score: Number,  // 0-100
  knowledge_gaps: [{
    topic: String,
    topic_id: String,
    gap_type: Enum ["FUNDAMENTAL_GAP", "PARTIAL_GAP", "SURFACE_GAP"],
    confidence: Number,
    misconceptions: [String],
    error_patterns: [String],
    evidence: [String],
    prerequisites: [String],
    related_topics: [String],
    suggested_intervention: String,
    // Concept-graph resolution (populated by the gate):
    resolved_concept_id: String,          // matched concept-graph node
    resolution_method: Enum [
      "exact", "alias", "embedding", "llm",
      "llm_no_match", "unresolved", "implicit"
    ],
    resolution_confidence: Number,
    concept_context: Mixed,               // built node snapshot (id, name, description,
                                          // bloom_level, prerequisite_names,
                                          // related_topic_names); null when unresolved
  }],
  strengths: [Object],
  recommendations: [Object],
  augmented_profile: {
    implicit_gaps: [{              // blocking prerequisites injected for n8n
      concept_id: String,
      injected: Boolean,           // default true
      reason: String
    }],
    unverified_prerequisites: [{   // UNKNOWN-state closure results (§5.1)
      concept_id: String,
      blocks: String               // the resolved gap this prereq blocks
    }],
    coverage_snapshot: {           // computed at submission time
      totalNodes: Number,
      coveredNodes: Number,
      coveragePct: Number
    }
  },
  n8n_triggered: Boolean,
  submitted_at: Date
}
```

#### `concept_graph_nodes` Collection

```javascript
{
  concept_id: String,             // unique, required, e.g. "java.oop.inheritance"
  name: String,                   // required
  category: String,               // indexed, required (Fundamentals/Control Flow/...)
  subcategory: String,
  bloom_level: Enum ["remember", "understand", "apply", "analyze", "evaluate", "create"],
  description: String,            // required
  description_embedding: [Number],// 768-dim vector (nomic-embed-text), set at seed time
  aliases: [String],
  prerequisites: [String],        // indexed, one-directional concept_id refs (§3.2)
  related_topics: [String],
  source: String,                 // default "OCJP_objectives"
  version: Number,
  createdAt: Date,
  updatedAt: Date
}
```

#### `generation_jobs` Collection

```javascript
{
  job_id: String,            // unique, format "JOB_{timestamp}"
  student_id: ObjectId,      // indexed
  profile_id: ObjectId,      // ref → mastery_profiles
  status: Enum ["queued", "processing", "completed", "failed", "partial", "closed"],
  gaps_total: Number,        // = length of the AUGMENTED gap list (incl. implicit prereqs)
  gaps_queued: Number,
  gaps_completed: Number,
  gaps_failed: Number,
  gap_topic_ids: [String],   // topic_id of every gap in the augmented list (default [])
                             // persists so completion tracking matches the n8n payload
  n8n_workflow_id: String,
  n8n_execution_id: String,
  materials_generated: Number,
  materials_failed: Number,
  created_at: Date,
  completed_at: Date
}
```

#### `learning_materials` Collection

```javascript
{
  structured_material: {
    material_id: String,          // unique
    student_id: ObjectId,         // indexed
    topic: String,
    topic_id: String,
    gap_type: Enum,
    difficulty_level: String,
    generated_at: Date,           // indexed
    generation_models: { llm: String, slm: String },
    // Concept-Graph Coverage-and-Prerequisite Layer (written by the enriched
    // n8n workflow; absent on pre-enrichment materials):
    generation_source: Enum ["explicit_gap", "implicit_prerequisite"],
    resolution_method: Enum ["exact", "alias", "embedding", "llm",
                             "llm_no_match", "unresolved", "implicit"],
    lesson: {
      page_title: String,
      introduction: String,
      concept_explained: String,
      syntax_reference: String,
      examples: [Object],
      step_by_step_guide: [Object],
      common_mistakes: [String],
      debugging_exercise: Object,
      quick_reference: String,
      connections: [String]
    },
    assessment: {
      quiz: [Object],
      concept_summary: String,
      practice_challenge: String,
      self_check: [String]
    },
    personalisation: {
      concept_context: Object,      // resolved concept-graph node (id, name, category, bloom_level)
      prerequisite_reason: String,  // why an implicit prerequisite was injected (blocks: <topic>)
    },
    study_plan: Object,
    agentic_metadata: {
      quality_score: Number,
      validation_score: Number,
      retry_count: Number,
      agent_notes: String
    },
    quality_flags: {
      deleted: Boolean,
      flagged: Boolean
    }
  }
}
```

#### `student_progress` Collection

```javascript
{
  student_id: ObjectId,        // indexed
  material_id: String,         // ref → learning_materials
  topic_id: String,
  total_steps: Number,
  completed_steps: [Number],
  quiz_score: Number,
  started_at: Date,
  completed_at: Date,
  last_active_step: Number
}
```

#### `model_comparison_logs` Collection

```javascript
{
  log_id: String,              // unique
  student_id: ObjectId,        // indexed
  topic: String,
  llm_model: String,
  slm_model: String,
  agent_quality_score: Number,
  content_validation_score: Number,
  agent_retry_count: Number,
  llm_parse_error: Boolean,
  slm_parse_error: Boolean,
  timestamp: Date              // indexed
}
```

### Services & Business Logic

#### `n8n.service.js`
HTTP client for triggering and communicating with the n8n workflow engine. Handles:
- Triggering material generation via POST to n8n webhook
- Fetching materials from n8n's material endpoint
- Health checks against n8n and Ollama
- 10-minute timeout for long-running AI generation
- Graceful handling of n8n offline/timeout scenarios

#### `conceptGraph.service.js`
Core of the Concept-Graph Coverage-and-Prerequisite Layer. Implements:
- **Embedding utilities** — `embed` / `embedMany` via Ollama `nomic-embed-text`, `generate` via `qwen2.5-coder:7b` (temperature 0, `num_predict` 64), with `embedder` / `ollamaClient` singleton abstractions for testability
- **Defensive LLM parsing** — `stripFences`, `findOutermostObject`, `extractField`, `parseConceptIdResponse` (fenced ids, JSON `concept_id`, bare `java.*` id regex with trailing `[._]+` trimmed, `NO_MATCH` → `null`), mirroring the n8n workflow's parsing
- **Three-tier resolution (§4)** — `resolveGap`: Tier 1 exact/alias match → Tier 2 embedding (cosine similarity, threshold 0.75, escalate on top-2 ambiguity ≤ 0.05) → Tier 3 LLM (`llm_no_match` on no-match/LLM failure). Fail-open: empty graph short-circuits to `unresolved` without calling Ollama
- **Prerequisite closure (§5)** — `classify` (MASTERED/GAP/UNKNOWN) + `closePrerequisites` BFS: MASTERED stops the branch, GAP keeps walking, UNKNOWN is flagged `{ concept_id, blocks }` (conservative — never auto-injected)
- **Gap augmentation** — `augmentGaps(knowledgeGaps, strengths, graph, embedder, ollamaClient)` returns `{ resolvedGaps, injectedGaps, effectiveGaps, closure }` in a single pass. **Every gap** carries a `concept_context` built from its resolved ConceptGraphNode via `buildConceptContext(node, graph)` (`{ concept_id, id, name, description, bloom_level, category, prerequisite_names, related_topic_names }` — prerequisite/related ids are mapped to node names). Injected gaps additionally carry `topic` (node name), `topic_id` (concept_id), `gap_type: FUNDAMENTAL_GAP`, `difficulty_level` (from Bloom level), `resolution_method: "implicit"` and `reason: "prerequisite_of:<blocks>"`. Unresolved gaps (`unresolved`/`llm_no_match`) get `concept_context: null`. `effectiveGaps` is the single source reused for both the n8n payload and the GenerationJob counters — so the workflow's Prompt Construction Module renders `CANONICAL SCOPE`/`COGNITIVE LEVEL` for explicit gaps too, not just injected ones.
- **Coverage (§7.1)** — `computeCoverage`: counts category nodes and distinct `structured_material.topic_id` covered per student → `coveragePct`
- **Seeding** — `validateGraphAcyclic` (duplicate ids, self-loops, unknown prereq refs, cycle detection via topological sort) + `seedGraph` (validates → embeds → idempotent `bulkWrite` upsert keyed on `concept_id`)
- **Helper** — `bloomToDifficulty` maps Bloom level to beginner/intermediate/advanced

#### `userService.client.js`
HTTP client for the separate User Service. Handles:
- JWT token verification (every protected request)
- Student data fetching
- Fire-and-forget stats updates
- Health checks

#### `material.service.js`
Business logic for materials:
- Dynamic query building with filters (topic, gap_type, status)
- Material statistics aggregation (gap distribution, quality scores)
- Global agent statistics across all students
- MongoDB aggregation pipelines for topic analysis

#### `jobTracker.service.js`
Background service for real-time job monitoring:
- **MongoDB Change Streams** watching `learning_materials` collection for inserts
- **Polling interval** every 10 seconds for missed events
- Auto-syncs job counters (gaps_completed, materials_generated)
- Auto-transitions `processing → completed` when all gaps are covered
- Recovers failed jobs if materials eventually arrive

### Concept-Graph Coverage-and-Prerequisite Layer

#### Overview

A preprocessing gate wired into `POST /api/mastery/submit` (before the n8n trigger). It resolves free-text knowledge gaps to canonical Java concept-graph nodes, surfaces implicit prerequisites, and tracks concept coverage — all **fail-open** (§4.4): if anything in the gate fails, the original gaps are forwarded unchanged and the request proceeds normally.

#### Resolution Pipeline (§4)

```
knowledge gap (topic) ──► Tier 1: exact/alias match on concept_id & aliases
                              │ hit → resolved (confidence 1.0)
                              ▼ miss
                         Tier 2: embedding similarity (nomic-embed-text, 768-dim)
                              │ ≥ 0.75 cosine & unambiguous → resolved (embedding)
                              │ (top-2 within 0.05 → escalate)
                              ▼ miss / ambiguous / no vectors
                         Tier 3: LLM (qwen2.5-coder:7b) maps to ONE concept_id
                              │ → resolved (llm) / NO_MATCH (llm_no_match)
                              ▼
                         unresolved (never blocks generation)
```

Each gap stores `resolved_concept_id`, `resolution_method`, and `resolution_confidence`.

#### Prerequisite Closure (§5)

Three-state BFS from each resolved gap over `prerequisites` edges:

| State | Behavior |
|-------|----------|
| `MASTERED` (in strengths) | Stop walking this branch — prerequisite already covered |
| `GAP` (another known gap) | Keep walking — also unresolved, surface its own prereqs |
| `UNKNOWN` (not seen) | Flag as `{ concept_id, blocks }` under `unverified_prerequisites` — **never auto-injected** |

Implicit (blocking) prerequisites are added to the n8n payload as `knowledge_gaps` entries (`gap_type: FUNDAMENTAL_GAP`, `resolution_method: implicit`) so the generator produces them too. They persist only as `augmented_profile.implicit_gaps` concept_ids — they are not written back into `knowledge_gaps`.

**Job counters match the augmented list.** `profile.controller.js` calls `augmentGaps` **once** per submission and reuses the returned `effectiveGaps` for both the n8n trigger payload and the `GenerationJob` document: `gaps_total`/`gaps_queued` count the augmented list (explicit + injected implicit prerequisites), and `gap_topic_ids` persists every `topic_id` in that list. On completion, `agent.controller.js` `completeJob` matches materials against `job.gap_topic_ids` (falling back to `profile.knowledge_gaps` only when the job has no topic list) — so progress/completion never drifts from what n8n actually generated. The gate is fail-open: when the graph is empty or the gate throws, the raw gap list is used and `gaps_total`/`gaps_queued` are still set (previously left unset).

**Enriched materials.** The V2 n8n workflow (`n8n/LMG_PP2_test_01_concept_graph_enriched.json` — import into n8n before testing) stamps each material with `structured_material.generation_source` (`explicit_gap` | `implicit_prerequisite`), `resolution_method`, and `personalisation.concept_context` / `personalisation.prerequisite_reason`. The workflow's "MongoDB — Store Learning Material" node writes `=structured_material` directly into `learning_materials`, so these fields persist without any schema migration.

#### Seeding

The graph lives in the `concept_graph_nodes` collection. Two equivalent ways to seed it:

```bash
# 1) Via the seed script (reads seed/java_oop_graph.json, computes embeddings)
npm run seed:concept-graph
#   (Ollama must be reachable at $OLLAMA_BASE_URL and have nomic-embed-text)

# 2) Via the API endpoint (Postman)
#    POST /api/concept-graph/seed   Authorization: Bearer <JWT>
#    Body: the 42-node array from seed/java_oop_graph.json
#    (collection: postman/Concept_Graph_Seed.postman_collection.json)
```

Seed prerequisites:
- Start Ollama: `ollama serve` (or `brew services start ollama`)
- Pull the embedding model: `ollama pull nomic-embed-text`
- The seed data is exactly the 42 nodes from the spec §3/§4 (Fundamentals → Control Flow → Arrays → Methods → OOP → Exceptions → Collections), verified acyclic by `validateGraphAcyclic`.

The seed is idempotent (`upsert` keyed on `concept_id`) and re-computes embeddings on every run.

#### Coverage (§7.1)

`GET /api/concept-graph/coverage/:studentId?category=OOP` reports how many concepts a student has generated materials for:

```
totalNodes   = concept_graph_nodes count in category
coveredNodes = distinct structured_material.topic_id (student's materials) ∈ category
coveragePct  = coveredNodes / totalNodes * 100
```

### Middleware

| Middleware | Purpose |
|-----------|---------|
| `auth.middleware.js` | Extracts Bearer token → calls User Service `verifyToken` → populates `req.student` |
| `error.middleware.js` | Global error handler for ServiceError, Mongoose validation, CastError, duplicate keys |
| `validate.middleware.js` | Generic Joi validation for body/query/params with field-level error details |
| `webhook.middleware.js` | Validates `X-Webhook-Secret` header for n8n callback security |

### Environment Configuration

| Variable | Example Value | Description |
|----------|--------------|-------------|
| `PORT` | `5012` | Server listen port |
| `NODE_ENV` | `development` | Environment mode |
| `SERVICE_NAME` | `lmg-service` | Service identifier for logs |
| `MONGODB_URI` | `mongodb+srv://...` | MongoDB Atlas connection string |
| `USER_SERVICE_URL` | `http://user-service:3001` | User Service internal URL |
| `INTERNAL_SERVICE_KEY` | `7a9c3e1d...` | Inter-service authentication key |
| `N8N_BASE_URL` | `http://n8n-container:5678` | n8n workflow engine URL |
| `N8N_WEBHOOK_LEARNER_PROFILE` | `http://n8n-container:5678/webhook/learner-profile` | n8n trigger webhook |
| `N8N_WEBHOOK_GET_MATERIALS` | `http://n8n-container:5678/webhook/materials` | n8n materials endpoint |
| `N8N_WEBHOOK_SECRET` | `7a9c3e1d...` | Shared secret for webhook auth |
| `N8N_TIMEOUT_MS` | `600000` | 10-minute timeout for n8n |
| `OLLAMA_BASE_URL` | `http://host.docker.internal:11434` | Local Ollama server (embeddings + LLM) |
| `CORS_ORIGIN` | `http://localhost:3000` | Frontend origin |

### Docker Setup

```dockerfile
# Dockerfile (node:20-alpine)
FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .
EXPOSE 3002
CMD ["node", "server.js"]
```

```bash
# Build & Run
docker build -t lmg-service .
docker run -p 5012:3002 --env-file .env lmg-service

# Or via docker compose (from the repo root)
docker compose up -d --build lmg-service

# Seed the concept graph inside the container
# (requires Ollama running on the host at $OLLAMA_BASE_URL with nomic-embed-text)
docker compose exec lmg-service node scripts/seedConceptGraph.js
```

---

## Frontend Application

**Path:** `mentora-frontend/src/`

### Pages & Routes

| Route | Page | Description |
|-------|------|-------------|
| `/learning-generator` | Overview Dashboard | Hero card with gap/material counts, active generation jobs with live 5s polling, progress stats, knowledge gap cards, sidebar with quick actions/**concept-coverage panel**/module progress/score history/strengths, submit-profile dialog |
| `/learning-generator/knowledge-gaps` | Knowledge Gaps | Detailed gap analysis with summary cards (total/fundamental/partial/surface), filter buttons, expandable cards with evidence, misconceptions, error patterns, prerequisites, interventions |
| `/learning-generator/materials` | Materials Gallery | Searchable/filterable grid of generated materials with gap type counts, topic search, MaterialCard components linking to workspaces |
| `/learning-generator/materials/[materialId]` | Material Workspace | Step-by-step guided learning with: learning path sidebar, content renderer (intro → concepts → guide → examples → mistakes → practice → debugging), code editor with execution, AI insight panels, quiz section, progress tracking. Implicit-prerequisite materials show a blue contextual banner (concept name + `prerequisite_reason`) |
| `/learning-generator/workspace` | Code Sandbox | Standalone Java workspace with: code editor, execution, AI feedback, inline code explanation (select text), error fixing, code review with annotations, concept flashcards, JUnit test generation, execution timeline |

### Components (24 Total)

#### Dashboard Components

| Component | File | Description |
|-----------|------|-------------|
| `JobCard` | `JobCard.tsx` | Active generation job with status badge, progress bar, material count. Exports `ActiveJobsList` |
| `ProgressStats` | `ProgressStats.tsx` | 4 stat cards (progress %, completed, in-progress, avg quiz score) + learning bar |
| `KnowledgeGapCard` | `KnowledgeGapCard.tsx` | Single gap card with topic, type badge, evidence, misconceptions, confidence, link |
| `SubmitProfileDialog` | `SubmitProfileDialog.tsx` | Modal to submit mastery profile and trigger generation |
| `OverviewSidebar` | `OverviewSidebar.tsx` | QuickActions, **ConceptCoverage** (coverage %, node counts, implicit-gap tile, unresolved note), ModuleProgressList, ScoreHistory, StrengthsList |

#### Knowledge Gap Components

| Component | File | Description |
|-----------|------|-------------|
| `GapSummaryCards` | `GapSummaryCards.tsx` | 4 summary cards (total/fundamental/partial/surface gaps) |
| `GapFilters` | `GapFilters.tsx` | Filter buttons with counts. Exports `getGapCounts`, `getFilteredGaps`, `getGapColors` |
| `ExpandableGapCard` | `ExpandableGapCard.tsx` | Accordion card with evidence, misconceptions, error patterns, prerequisites, interventions |

#### Materials Components

| Component | File | Description |
|-----------|------|-------------|
| `MaterialCard` | `MaterialCard.tsx` | Material card with topic, gap type, difficulty, content types, date, model, workspace link. Shows a neutral-blue **Prerequisite** badge when `generation_source === "implicit_prerequisite"` |
| `SearchFilterBar` | `SearchFilterBar.tsx` | Search input + gap-type filter buttons |

#### Learning Experience Components

| Component | File | Description |
|-----------|------|-------------|
| `LearningPathSidebar` | `LearningPathSidebar.tsx` | Left sidebar: topic, difficulty, progress bar, step list (completed/active/locked) |
| `ContentRenderer` | `ContentRenderer.tsx` | Renders content by step type. Includes "Explain Simpler" + "Real-life Analogy" AI buttons + InsightPanel |
| `InsightPanel` | `InsightPanel.tsx` | Displays AI-generated insights with loading state and formatted text |
| `QuizSection` | `QuizSection.tsx` | Multiple-choice quiz, answer tracking, scoring, mastery achievement display |
| `CodeEditorPanel` | `CodeEditorPanel.tsx` | Embedded code editor with run button, output tab, AI feedback tab |
| `BottomNav` | `BottomNav.tsx` | Previous/Next navigation for step progression |

#### Code Sandbox Components

| Component | File | Description |
|-----------|------|-------------|
| `WorkspaceTopBar` | `WorkspaceTopBar.tsx` | Toolbar: stdin toggle, flashcards, JUnit, timeline, review, reset, run |
| `WorkspaceEditor` | `WorkspaceEditor.tsx` | Code editor with review annotation overlays (color-coded severity) + inline AI explanation popup |
| `WorkspaceTabs` | `WorkspaceTabs.tsx` | Right panel: Output, AI Feedback, Review Annotations, Fix Suggestions tabs |
| `StdinBar` | `StdinBar.tsx` | Standard input bar for Java programs |
| `FlashcardsPanel` | `FlashcardsPanel.tsx` | AI-generated concept flashcards with difficulty badges |
| `TestsPanel` | `TestsPanel.tsx` | AI-generated JUnit test code with explanation and copy |
| `ExecutionTimeline` | `ExecutionTimeline.tsx` | Horizontal bar chart for method-level execution timing |

### API Clients

#### Learning Generator API (`src/lib/api/learningGenerator.ts`)

- **Base URL:** `http://localhost:5012` (`NEXT_PUBLIC_LMG_API_URL`)
- **Type:** Fully typed TypeScript class `LearningGeneratorApi`
- **Endpoints:** All LMG Service endpoints (mastery, materials, agent, progress, concept coverage)
- **Concept-graph types:** `ConceptContext` (resolved node: id/name/category/bloom_level), `ConceptCoverage` (`{ totalNodes, coveredNodes, coveragePct, implicitGapsCount, unverifiedCount }`), typed `generation_source`/`resolution_method`/`personalisation` on `LearningMaterial.structured_material`
- **Coverage fetch:** `getConceptCoverage(studentId, category?)` → `GET /api/concept-graph/coverage/:studentId`

#### AI Engine API (`src/lib/api/aiEngine.ts`)

- **Base URL:** `http://localhost:5010` (`NEXT_PUBLIC_AI_ENGINE_API_URL`)
- **Endpoints:**

| Endpoint | Purpose |
|----------|---------|
| `POST /api/execute` | Execute Java code |
| `POST /api/feedback` | AI feedback on code |
| `POST /api/run-with-feedback` | Execute + feedback in one call |
| `POST /api/explain-simpler` | Simplified explanation |
| `POST /api/analogy` | Real-life analogy |
| `POST /api/explain-code` | Explain selected code |
| `POST /api/fix-error` | AI error fixing |
| `POST /api/code-review` | Code review with annotations |
| `POST /api/flashcards` | Generate concept flashcards |
| `POST /api/generate-tests` | Generate JUnit tests |

#### Custom Hook (`src/hooks/useWorkspaceSession.ts`)

Manages code sandbox session state with `sessionStorage` persistence: code, output, AI feedback, flashcards, tests, code review, fix suggestions, highlighted code, execution timeline.

### Frontend Navigation

The sidebar (`src/components/dashboard/Sidebar.tsx`) includes a **Material Generator** section:
- Overview → `/learning-generator`
- Knowledge Gaps → `/learning-generator/knowledge-gaps`
- Materials → `/learning-generator/materials`
- Learn Code → `/learning-generator/workspace`

---

## Integration Architecture

### Service Communication

| From | To | Protocol | Auth | Purpose |
|------|----|----------|------|---------|
| Frontend | LMG Service | HTTP REST | JWT (Bearer) | All user-facing API calls |
| Frontend | AI Engine | HTTP REST | None (local) | Code execution, AI features |
| LMG Service | User Service | HTTP REST | X-Internal-Key | JWT verification, student data, stats |
| LMG Service | n8n | HTTP REST | X-Webhook-Secret | Trigger generation, fetch materials |
| n8n | LMG Service | HTTP Webhooks | X-Webhook-Secret | Material delivery, job updates, completion |
| n8n | Ollama | HTTP REST | None (local) | LLM inference (qwen2.5-coder:7b) |
| LMG Service | Ollama | HTTP REST | None (local) | Embeddings (nomic-embed-text) + LLM gap resolution |
| LMG Service | MongoDB Atlas | Mongoose | Connection string | Data persistence (incl. concept_graph_nodes) |
| n8n | MongoDB Atlas | Direct | Connection string | Write materials + logs |

### Data Flow Summary

1. **Profile Submission:** Frontend → LMG Service → MongoDB (save profile) → Concept-graph gate (resolve gaps, close prerequisites, compute coverage) → n8n (trigger pipeline with augmented gaps)
2. **Concept Seeding:** `POST /api/concept-graph/seed` (or `npm run seed:concept-graph`) → validate → Ollama embeddings → upsert into `concept_graph_nodes`
3. **Material Generation:** n8n → Ollama (LLM inference) → n8n agents (quality review) → LMG webhooks (delivery)
4. **Job Tracking:** MongoDB Change Streams + polling → JobTrackerService → auto-complete jobs
5. **Learning Experience:** Frontend → LMG Service (get materials/progress) → AI Engine (code execution/AI features)
6. **Progress Updates:** Frontend → LMG Service → MongoDB (persist step completion + quiz scores)

---

## API Testing

### Postman Collections

| Collection | Requests | Description |
|-----------|----------|-------------|
| `LMG_Service.postman_collection.json` | 20 | Full API testing: health, mastery profiles, materials, agent/jobs, progress |
| `N8N_Integration.postman_collection.json` | 10 | n8n webhook tests + LMG-to-n8n integration + health checks |
| `Concept_Graph_Seed.postman_collection.json` | 1 | Seeds the 42-node concept graph via `POST /api/concept-graph/seed` |
| `docs/postman.json` | — | Complete API collection including webhook endpoints |

### Tests

```bash
# Unit + integration tests (Node's built-in test runner, no extra deps) — 32 passing
npm test
# Concept-graph unit tests (resolution tiers, closure/BFS, parsing)
# Integration tests (fail-open flow, LLM escalation, empty graph)
# Seed cycle-detection tests (real seed acyclic + rejection cases)
# profileJobCounting tests (augmented list → GenerationJob counters, gap_topic_ids,
#   implicit-gap fields, fail-open counter behaviour)
```

### Health Check

```bash
# Basic health
curl http://localhost:5012/health

# Full dependency check (MongoDB, User Service, n8n, Ollama)
curl http://localhost:5012/api/agent/health \
  -H "Authorization: Bearer <jwt_token>"
```

### Quick Start

```bash
# Install dependencies
npm install

# Set up environment
cp .env.example .env
# Edit .env with your configuration

# Development (with hot-reload)
npm run dev

# Production
npm start

# Seed the concept graph (requires Ollama + nomic-embed-text)
npm run seed:concept-graph

# Tests
npm test

# Lint
npm run lint
```
