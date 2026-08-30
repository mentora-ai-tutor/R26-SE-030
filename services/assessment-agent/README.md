# 🧠 Mentora — Assessment & Mastery Evaluation (AME) Agent

> A core microservice of the **Mentora AI Tutoring Platform** that manages AI-driven adaptive assessment sessions, evaluates learner mastery in real-time, and provides rich analytics for educators.

---

## 📖 Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Technology Stack](#technology-stack)
4. [Project Structure](#project-structure)
5. [Environment Configuration](#environment-configuration)
6. [Installation & Setup](#installation--setup)
7. [Running the Service](#running-the-service)
8. [API Reference](#api-reference)
9. [RAG Knowledge Base](#rag-knowledge-base)
10. [n8n Workflow Integration](#n8n-workflow-integration)
11. [Database Schema & Collections](#database-schema--collections)
12. [Analytics & Algorithms](#analytics--algorithms)
13. [Security](#security)
14. [Error Handling](#error-handling)
15. [Postman Collection](#postman-collection)
16. [Deployment](#deployment)

---

## Overview

The **AME Agent** acts as the intelligent bridge between the learner-facing frontend and the agentic [n8n](https://n8n.io/) workflows powered by Ollama (Gemma4 LLM). It manages the complete lifecycle of an adaptive assessment session:

- 🚀 **Session Initialization** — Bootstraps a new assessment based on a learner's `mastery_profile` and identified `knowledge_gaps`.
- ✅ **Answer Evaluation** — Routes submitted answers through n8n for LLM-based evaluation and state update.
- 📊 **Mastery Tracking** — Persists and queries real-time mastery updates per topic and per learner.
- 🔁 **Remediation Loops** — Detects low-mastery conditions and triggers targeted remediation question sequences.
- 📋 **Feedback Reports** — Retrieves AI-generated session completion reports with overall grades and misconception analysis.
- 📈 **Analytics Service** — Provides over 15 aggregation-based analytics functions for admin/instructor dashboards.
- 🔍 **RAG Knowledge Base** — Retrieval-Augmented Generation layer: ingests curriculum/knowledge documents, embeds them via Ollama, stores vectors in MongoDB, and enriches question generation and feedback with semantically relevant context.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      Learner Frontend                            │
└─────────────────────────────┬───────────────────────────────────┘
                              │ REST (JWT-authenticated)
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              AME Agent  (Node.js / Express)                     │
│                                                                 │
│  ┌───────────┐   ┌──────────────┐   ┌────────────────────────┐ │
│  │  Routes   │──▶│  Controller  │──▶│  n8nService            │ │
│  │           │   │              │   │  (Webhook Bridge)      │ │
│  └───────────┘   └──────────────┘   └──────────┬─────────────┘ │
│                          │                      │               │
│                          │      ┌───────────────▼──────────┐    │
│                          │      │  ragService              │    │
│                          │      │  (RAG: ingest/retrieve)  │    │
│                          │      └───────────────┬──────────┘    │
│                          │                      │               │
│                  ┌───────▼──────┐               │               │
│                  │  MongoService│               │               │
│                  │  (Analytics) │               │               │
│                  └───────┬──────┘               │               │
└──────────────────────────┼──────────────────────┼───────────────┘
                           │                      │
                           ▼                      ▼
               ┌──────────────────┐    ┌─────────────────────┐
               │     MongoDB      │    │   n8n Agentic       │
               │  (AME + RAG KB)  │    │   Workflows         │
               └──────────────────┘    │  (Ollama / Gemma4)  │
                                       └─────────────────────┘
```

### Request Flow

1. **Frontend** sends a JWT-authenticated request to the AME Agent.
2. **Auth Middleware** validates the JWT and injects `student_id` into `req.user`.
3. **Controller** validates input, builds a payload, and calls the appropriate service.
4. When **RAG is enabled**, the controller retrieves semantically relevant knowledge-base chunks for the request (gap topics on `start-session`, current question on `submit-answer`) and attaches them to the payload as `rag_context`.
5. For **write operations** (`start-session`, `submit-answer`): the `n8nService` forwards the payload (including `rag_context`) to the n8n webhook and returns the workflow response.
6. For **read operations** (`getSession`, `getSessions`, `getFeedbackReport`, `getQuestions`): the controller directly queries **MongoDB** via the native driver.

---

## Technology Stack

| Layer | Technology | Version |
|---|---|---|
| Runtime | Node.js | >= 18.0.0 |
| Framework | Express.js | ^4.18.2 |
| Database ORM/Driver | Mongoose + Native Driver | ^8.0.3 |
| Database | MongoDB Atlas | - |
| HTTP Client | Axios | ^1.6.2 |
| Authentication | JSON Web Tokens (jsonwebtoken) | ^9.0.2 |
| Security | Helmet | ^7.1.0 |
| CORS | cors | ^2.8.5 |
| Logging | Morgan | ^1.10.0 |
| Config | dotenv | ^16.3.1 |
| Dev Server | Nodemon | ^3.0.2 |
| Workflow Engine | n8n (self-hosted) | - |
| LLM | Ollama / Gemma4 | - |

---

## Project Structure

```
assessment-agent/
│
├── server.js                        # Entry point — connects DB and starts Express
│
├── src/
│   ├── app.js                       # Express app config (CORS, Helmet, Morgan, Routes)
│   │
│   ├── config/
│   │   └── database.js              # MongoDB connection via Mongoose
│   │
│   ├── routes/
│   │   ├── assessment.js            # All /api/ame/* route definitions
│   │   └── rag.js                   # RAG knowledge-base routes (/api/ame/rag/*)
│   │
│   ├── controllers/
│   │   ├── assessmentController.js  # Request handlers for all assessment operations
│   │   └── ragController.js         # Request handlers for RAG knowledge-base operations
│   │
│   ├── services/
│   │   ├── n8nService.js            # Webhook bridge: forwards payloads to n8n
│   │   ├── mongoService.js          # 15+ analytics query functions for admin dashboard
│   │   ├── ragService.js            # RAG pipeline: chunking, ingest, semantic retrieval, KB mgmt
│   │   └── embeddingService.js      # Ollama embeddings client (batch + legacy APIs)
│   │
│   ├── middleware/
│   │   ├── auth.js                  # JWT authentication & admin role guard
│   │   └── errorHandler.js          # Global error response formatter
│   │
│   └── tests/                       # (Reserved) Test suite directory
│
├── docs/
│   ├── implementation.md            # Detailed algorithm documentation
│   ├── n8n_workflow_api.md          # n8n webhook contract (request/response schemas)
│   └── rag_architecture.md          # RAG pipeline architecture & knowledge-base guide
│
├── n8n/
│   └── assessment-agent.json        # Exportable n8n workflow definition
│
├── postman/
│   └── AME_Agent_API.postman_collection.json  # Postman collection for API testing
│
├── .env                             # Local environment variables (do not commit)
├── .env.example                     # Template for environment configuration
├── package.json
└── package-lock.json
```

---

## Environment Configuration

Copy `.env.example` to `.env` and fill in all required values.

```bash
cp .env.example .env
```

| Variable | Description | Example |
|---|---|---|
| `PORT` | Port the AME Agent listens on | `5002` |
| `NODE_ENV` | Runtime environment | `development` / `production` |
| `MONGODB_URI` | Full MongoDB connection string | `mongodb+srv://user:pass@cluster.mongodb.net/ame_agent_db` |
| `N8N_BASE_URL` | Base URL of your n8n instance | `http://localhost:5678` |
| `N8N_WEBHOOK_PATH` | Webhook path prefix configured in n8n | `/webhook` |
| `OLLAMA_BASE_URL` | Ollama endpoint used for RAG embeddings | `http://localhost:11434` |
| `OLLAMA_EMBEDDING_MODEL` | Embedding model (must be pulled in Ollama) | `nomic-embed-text:cpu` |
| `OLLAMA_EMBEDDING_TIMEOUT` | Embedding request timeout in ms | `30000` |
| `RAG_ENABLED` | Master switch for RAG context enrichment | `true` / `false` |
| `RAG_TOP_K` | Default number of chunks returned by retrieval | `5` |
| `RAG_MIN_SCORE` | Minimum cosine similarity threshold | `0.25` |
| `RAG_CHUNK_SIZE` | Target knowledge chunk size (characters) | `800` |
| `RAG_CHUNK_OVERLAP` | Overlap between consecutive chunks | `120` |
| `JWT_SECRET` | Shared secret for JWT verification (must match other Mentora services) | `your-256-bit-secret` |
| `FRONTEND_URL` | Allowed origin for CORS | `http://localhost:3000` |

> **Important:** The `JWT_SECRET` must be identical to the secret used by the authentication service that issues learner tokens.

---

## Installation & Setup

### Prerequisites

- **Node.js** v18 or higher — [Download](https://nodejs.org/)
- **MongoDB** instance (local or [MongoDB Atlas](https://www.mongodb.com/cloud/atlas))
- **n8n** instance with the AME workflow imported — [Setup n8n](https://docs.n8n.io/)
- **Ollama** running locally with the Gemma4 model pulled (used by n8n workflow)

### Step 1 — Clone & Install

```bash
# Navigate to the service directory
cd services/assessment-agent

# Install Node.js dependencies
npm install
```

### Step 2 — Configure Environment

```bash
# Copy the example environment file
cp .env.example .env

# Edit .env with your actual values
```

### Step 3 — Import n8n Workflow

1. Open your n8n instance.
2. Go to **Workflows → Import from file**.
3. Select `n8n/assessment-agent.json`.
4. Activate the workflow.
5. Ensure the webhook path matches `N8N_WEBHOOK_PATH` in your `.env`.

### Step 4 — Start the Service

```bash
# Development (with auto-reload via nodemon)
npm run dev

# Production
npm start
```

### Step 5 — Verify Health

```bash
curl http://localhost:5002/health
```

**Expected Response:**
```json
{
  "status": "ok",
  "service": "AME Backend",
  "timestamp": "2026-08-12T04:00:00.000Z"
}
```

---

## Running the Service

| Script | Command | Use Case |
|---|---|---|
| Development | `npm run dev` | Local development with auto-reload (nodemon) |
| Production | `npm start` | Production server start |

The server listens on `PORT` (default `5002`). It connects to MongoDB before binding to the port; if the database connection fails, the process exits with code `1`.

---

## API Reference

All routes are prefixed with `/api/ame` and require a **Bearer JWT** in the `Authorization` header, except the health endpoint.

### Authentication Header

```
Authorization: Bearer <your_jwt_token>
```

---

### `POST /api/ame/start-session`

Initializes a new adaptive assessment session.

**Request Body:**
```json
{
  "mastery_profile": {
    "overall_mastery_score": 65,
    "knowledge_gaps": [
      {
        "topic": "Recursion",
        "gap_type": "FUNDAMENTAL_GAP",
        "misconceptions": ["Infinite recursion", "Base case missing"],
        "observed_error_patterns": {
          "sandbox": ["StackOverflowError"]
        }
      }
    ],
    "recommendations": {
      "priority_order": ["Recursion"]
    }
  }
}
```

**Validation Rules:**
- `mastery_profile` — required.
- `mastery_profile.knowledge_gaps` — required, must be a non-empty array.

**Success Response `200`:**
```json
{
  "success": true,
  "session_id": "SESSION_1715587200000_STU-123",
  "learner_id": "STU-123",
  "message": "Session started. Here is your first question.",
  "question": {
    "question_id": "Q_1715587200000_abc123",
    "question_text": "What is the primary purpose of a base case in recursion?",
    "question_type": "mcq",
    "options": {
      "A": "To call the function again",
      "B": "To stop the recursive calls",
      "C": "To increase the stack size",
      "D": "To handle multiple parameters"
    },
    "correct_answer": "B",
    "evaluation_criteria": "The learner must identify that the base case prevents infinite recursion."
  },
  "session_info": {
    "topic": "Recursion",
    "difficulty": "easy",
    "question_number": 1,
    "mastery_score": 0,
    "mastery_threshold": 85,
    "topics_remaining": 1
  }
}
```

---

### `POST /api/ame/submit-answer`

Submits a learner's answer for evaluation and retrieves the next adaptive question.

**Request Body:**
```json
{
  "session_id": "SESSION_1715587200000_STU-123",
  "question_id": "Q_1715587200000_abc123",
  "answer": "B"
}
```

**Validation Rules:**
- `session_id` — required.
- `question_id` — required.
- `answer` — required.

**Success Response `200`:**
```json
{
  "success": true,
  "session_id": "SESSION_1715587200000_STU-123",
  "evaluation": {
    "is_correct": true,
    "correctness_score": 100,
    "evaluation_summary": "Correct answer selected."
  },
  "feedback": {
    "immediate_feedback": "Well done!",
    "concept_explanation": "Recursion requires a base case to terminate execution...",
    "encouragement": "Great start, keep it up!"
  },
  "mastery_update": {
    "topic": "Recursion",
    "previous_mastery": 0,
    "current_mastery": 15,
    "topic_mastered": false,
    "session_complete": false
  },
  "next_question": {
    "question_id": "Q_1715587205000_xyz789",
    "question_text": "Complete this recursive function to calculate factorial...",
    "question_type": "code_completion",
    "difficulty": "medium",
    "code_snippet": "public int fact(int n) { if(n <= 1) return 1; return n * [?] ; }"
  },
  "session_progress": {
    "question_number": 2,
    "current_topic": "Recursion",
    "current_difficulty": "medium",
    "topics_remaining": 0,
    "overall_accuracy": 100
  }
}
```

---

### `GET /api/ame/session/:sessionId`

Retrieves the latest state of a specific session.

**Strategy:** Checks `ame_session_updates` (most recent update) first; falls back to `ame_sessions` if no updates exist yet.

**Path Parameter:**
| Parameter | Type | Description |
|---|---|---|
| `sessionId` | string | The session ID returned by `start-session` |

**Success Response `200`:**
```json
{
  "success": true,
  "data": { /* Latest session state document */ }
}
```

**Error `404`:** Session not found.

---

### `GET /api/ame/sessions`

Retrieves all sessions belonging to the authenticated learner, sorted by most recent first.

**Success Response `200`:**
```json
{
  "success": true,
  "data": [
    {
      "session_id": "SESSION_...",
      "session_status": "active",
      "session_started_at": "2026-08-12T09:00:00Z"
    }
  ]
}
```

---

### `GET /api/ame/questions`

Retrieves all questions answered by the authenticated learner, enriched with answer history. Supports optional topic filtering.

**Query Parameters:**
| Parameter | Type | Required | Description |
|---|---|---|---|
| `topic` | string | No | Filter questions by topic name |

**Success Response `200`:**
```json
{
  "success": true,
  "data": [
    {
      "id": "Q_...",
      "number": 1,
      "question": "What is the primary purpose of a base case?",
      "type": "mcq",
      "code_snippet": null,
      "options": ["To call again", "To stop calls", "To increase stack", "To handle params"],
      "learner_answer": "B",
      "correct_answer": "B",
      "is_correct": true,
      "explanation": "The base case prevents infinite recursion.",
      "topic": "Recursion",
      "difficulty": "Easy",
      "bloom_level": 1,
      "time_spent": 45,
      "timestamp": 1715587200000
    }
  ]
}
```

---

### `GET /api/ame/feedback-report/:sessionId`

Retrieves the AI-generated feedback report for a completed session.

**Ownership Enforcement:** A learner can only retrieve their own reports. Attempting to access another learner's report returns `403`.

**Path Parameter:**
| Parameter | Type | Description |
|---|---|---|
| `sessionId` | string | The session ID of the completed session |

**Success Response `200`:**
```json
{
  "success": true,
  "data": {
    "session_id": "SESSION_...",
    "learner_id": "STU-123",
    "generated_at": "2026-08-12T10:00:00Z",
    "feedback_report": {
      "overall_grade": "Good",
      "overall_mastery_percentage": 72,
      "overall_accuracy_percentage": 80,
      "topics_covered": ["Recursion"],
      "misconceptions_to_address": ["Confusing base case with recursive step"],
      "strengths": ["Good understanding of recursion flow"],
      "areas_for_improvement": ["Practice more edge cases"]
    },
    "session_summary": {
      "session_duration_minutes": 25,
      "total_questions": 10,
      "topics_covered": ["Recursion"]
    },
    "full_qa_review": [ /* Per-question breakdown */ ]
  }
}
```

**Error `404`:** Report not found.  
**Error `403`:** Unauthorized — report belongs to another learner.

---

### `POST /api/ame/rag/ingest`

Ingests (or re-ingests) a knowledge document into the RAG knowledge base. The document is split into overlapping chunks, embedded via Ollama, and stored in MongoDB. Re-ingesting the same `document_id` replaces the previous chunks.

**Request Body:**
```json
{
  "document_id": "KB_RECURSION_01",
  "title": "Recursion Fundamentals",
  "topic": "Recursion",
  "source": "curriculum/unit-04",
  "content": "Recursion is a method that calls itself...",
  "metadata": { "course": "CS101" },
  "chunk_size": 800,
  "chunk_overlap": 120
}
```

**Validation Rules:**
- `content` — required, non-empty string.

**Success Response `200`:**
```json
{
  "success": true,
  "message": "Document ingested into the knowledge base",
  "data": { "document_id": "KB_RECURSION_01", "chunk_count": 12 }
}
```

---

### `POST /api/ame/rag/retrieve`

Performs a semantic (cosine similarity) search over the knowledge base and returns the top-K most relevant chunks. Falls back to keyword search when embedding retrieval is unavailable.

**Request Body:**
```json
{
  "query": "Why does recursion need a base case?",
  "topic": "Recursion",
  "top_k": 5,
  "threshold": 0.25
}
```

**Success Response `200`:**
```json
{
  "success": true,
  "data": {
    "query": "Why does recursion need a base case?",
    "top_k": 3,
    "retrieval": "embedding",
    "chunks": [
      {
        "score": 0.71,
        "chunk_id": "KB_RECURSION_01_CHUNK_2",
        "document_id": "KB_RECURSION_01",
        "title": "Recursion Fundamentals",
        "topic": "Recursion",
        "content": "The base case terminates recursive calls...",
        "metadata": { "course": "CS101" }
      }
    ]
  }
}
```

---

### `GET /api/ame/rag/documents`

Lists all documents in the knowledge base, sorted by most recently updated. Supports `?page=` and `?limit=` (defaults `1`, `20`).

### `GET /api/ame/rag/documents/:documentId`

Retrieves a single document together with all of its chunks (embeddings excluded). Returns `404` if not found.

### `DELETE /api/ame/rag/documents/:documentId`

Deletes a document and all of its chunks. Returns `404` if not found.

### `GET /api/ame/rag/stats`

Returns knowledge-base statistics: document/chunk counts, topics, embedding dimensions, and average chunks per document.

---

### `GET /health`

Public health check endpoint. No authentication required.

**Response `200`:**
```json
{
  "status": "ok",
  "service": "AME Backend",
  "timestamp": "2026-08-12T04:00:00.000Z"
}
```

---

## RAG Knowledge Base

The AME Agent includes a **Retrieval-Augmented Generation (RAG)** layer that grounds LLM-generated questions and feedback with content from a curated knowledge base (curriculum, lecture notes, question banks).

### How It Works

1. **Ingest** — `POST /api/ame/rag/ingest` splits a document into overlapping chunks, embeds each chunk with Ollama (`OLLAMA_EMBEDDING_MODEL`), and stores text + vectors in MongoDB (`ame_knowledge_documents`, `ame_knowledge_chunks`).
2. **Retrieve** — semantic search via cosine similarity over stored embeddings; falls back to keyword search if embeddings are unavailable.
3. **Augment** — `start-session` and `submit-answer` automatically retrieve relevant chunks and attach them to the n8n payload as `rag_context`. Retrieval is **best-effort and non-breaking**: an empty knowledge base, a disabled RAG flag, or an embedding failure never fail the request.

> See [`docs/rag_architecture.md`](./docs/rag_architecture.md) for the full pipeline, collection schemas, and configuration reference.

### Getting Started

```bash
# 1. Pull the embedding model
ollama pull nomic-embed-text

# Note: on machines where Ollama's CUDA build cannot load the GPU driver,
# force the CPU build instead (create the `:cpu` variant and use it):
#   ollama create nomic-embed-text:cpu -f <(echo "FROM nomic-embed-text`nPARAMETER num_gpu 0")
#   OLLAMA_EMBEDDING_MODEL=nomic-embed-text:cpu

# 2. Enable RAG in .env
RAG_ENABLED=true
OLLAMA_BASE_URL=http://localhost:11434

# 3. Ingest knowledge documents
curl -X POST http://localhost:5002/api/ame/rag/ingest \
  -H "Authorization: Bearer <jwt>" -H "Content-Type: application/json" \
  -d '{"title":"Recursion Fundamentals","topic":"Recursion","content":"..."}'

# 4. Verify retrieval
curl -X POST http://localhost:5002/api/ame/rag/retrieve \
  -H "Authorization: Bearer <jwt>" -H "Content-Type: application/json" \
  -d '{"query":"Why does recursion need a base case?"}'
```

---

## n8n Workflow Integration

The `n8nService` is a thin, dedicated HTTP client in `src/services/n8nService.js` that bridges the Express API and n8n agentic workflows.

### Webhook Endpoints Called by AME Agent

| Action | Method | n8n URL |
|---|---|---|
| Start Session | `POST` | `{N8N_BASE_URL}{N8N_WEBHOOK_PATH}/ame/start-session` |
| Submit Answer | `POST` | `{N8N_BASE_URL}{N8N_WEBHOOK_PATH}/ame/submit-answer` |

### Key Configuration

- **Timeout:** 3,600,000 ms (1 hour) — intentionally long to accommodate complex LLM reasoning chains.
- **Content-Type:** `application/json`
- **Error Handling:** Translates n8n timeout errors (`ECONNABORTED`) and response errors into user-friendly messages.
- **RAG Context:** When `RAG_ENABLED=true`, the payloads forwarded to these webhooks include a `rag_context` object (retrieved knowledge-base chunks). The workflow ignores unknown fields, so existing deployments are unaffected. Optionally reference `body.rag_context` inside the n8n prompt-building nodes to consume it.

### n8n Workflow Logic — `ame/start-session`

1. Validates the received mastery profile.
2. Sorts topics by priority from the `recommendations` field.
3. Selects the first topic. Starting difficulty: `easy` for `FUNDAMENTAL_GAP`, `medium` for `PARTIAL_GAP`.
4. Generates the first adaptive question via Ollama (Gemma4).
5. Persists the new session to MongoDB (`ame_sessions` and `ame_questions`).

### n8n Workflow Logic — `ame/submit-answer`

1. Fetches session state and question details from MongoDB.
2. Evaluates the answer (direct comparison for MCQ; LLM-based for open-ended).
3. Recalculates mastery score using weighted difficulty and rubric scores.
4. Determines next step:
   - **Remediation** — triggered if mastery is critically low after several wrong answers.
   - **Topic Mastery** — moves to the next topic if score >= 85%.
   - **Next Question** — adjusts Bloom's taxonomy level based on answer streak.
5. Generates a personalized feedback report if the session is complete.

> See [`docs/n8n_workflow_api.md`](./docs/n8n_workflow_api.md) for complete request/response schemas.  
> Import `n8n/assessment-agent.json` into your n8n instance to deploy the workflows.

---

## Database Schema & Collections

The service uses **MongoDB** with the following collections:

### `ame_sessions`

Stores the initial session configuration when a session is started.

| Field | Type | Description |
|---|---|---|
| `session_id` | String | Unique session identifier |
| `learner_id` | String | The student's ID |
| `session_status` | String | `active` / `completed` |
| `mastery_profile` | Object | The initial mastery profile passed in |
| `all_topics` | Array | All topics to be covered in the session |
| `selected_skill_level` | String | Learner's inferred skill level |
| `session_started_at` | Date | Session start timestamp |

### `ame_questions`

Stores every question generated during a session.

| Field | Type | Description |
|---|---|---|
| `session_id` | String | Parent session ID |
| `learner_id` | String | Learner's ID |
| `current_question` | Object | Full question object (text, type, options, correct_answer, topic, difficulty, blooms_level, code_snippet) |
| `current_difficulty` | String | `easy` / `medium` / `hard` |
| `question_generated_at` | Date | Generation timestamp |

### `ame_answers`

Records every answer submitted by a learner.

| Field | Type | Description |
|---|---|---|
| `session_id` | String | Parent session ID |
| `learner_id` | String | Learner's ID |
| `question_id` | String | ID of the answered question |
| `submitted_answer` | String | The learner's answer |
| `is_correct` | Boolean | Evaluation result |
| `correctness_score` | Number | Score (0–100) |

### `ame_session_updates`

The most critical collection — stores a snapshot of session state **after every answer submission**. Used for state recovery and analytics.

| Field | Type | Description |
|---|---|---|
| `session_id` | String | Parent session ID |
| `learner_id` | String | Learner's ID |
| `current_topic_mastery` | Number | Current mastery % (0–100) |
| `topic_mastered` | Boolean | Whether the current topic is mastered |
| `session_complete` | Boolean | Whether the full session is done |
| `remediation_mode` | Boolean | Whether learner is currently in remediation |
| `remediation_entered` | Boolean | Whether remediation was ever triggered |
| `remediation_exited` | Boolean | Whether the learner successfully exited remediation |
| `updated_session` | Object | Full session state snapshot (topic, difficulty, topic_scores, session_history, etc.) |
| `mastery_calculation` | Object | Previous vs. current mastery for this update event |
| `update_timestamp` | Date | Timestamp of this state update |

### `ame_feedback_reports`

Stores the AI-generated final report when a session is completed.

| Field | Type | Description |
|---|---|---|
| `session_id` | String | Parent session ID |
| `learner_id` | String | Learner's ID |
| `generated_at` | Date | Report generation timestamp |
| `feedback_report` | Object | Grade, mastery %, accuracy %, strengths, areas for improvement, misconceptions |
| `session_summary` | Object | Duration, topics covered, total questions |
| `full_qa_review` | Array | Per-question review with correct answers and explanations |

### `ame_knowledge_documents` (RAG)

Stores metadata for every document ingested into the RAG knowledge base.

| Field | Type | Description |
|---|---|---|
| `document_id` | String | Unique document identifier |
| `title` | String/null | Document title |
| `topic` | String/null | Topic tag used for filtering |
| `source` | String/null | Origin of the content |
| `chunk_count` | Number | Number of chunks produced |
| `total_chars` | Number | Total character count |
| `metadata` | Object | Caller-provided metadata |
| `created_at` / `updated_at` | Date | Ingestion timestamps |

### `ame_knowledge_chunks` (RAG)

Stores each embedded chunk of the ingested documents.

| Field | Type | Description |
|---|---|---|
| `chunk_id` | String | Unique chunk id (`<document_id>_CHUNK_<n>`) |
| `document_id` | String | Parent document |
| `title` / `topic` / `source` | String/null | Inherited from the document |
| `chunk_index` | Number | Order within the document |
| `content` | String | The chunk text |
| `metadata` | Object | Inherited document metadata |
| `embedding` | Array | Embedding vector |
| `ingested_at` | Date | Ingestion timestamp |

---

## Analytics & Algorithms

The `src/services/mongoService.js` contains a comprehensive analytics library for admin/instructor dashboards. All functions accept the raw MongoDB `db` connection object.

| Function | Description |
|---|---|
| `getDashboardStats(db)` | KPI summary: total sessions, active sessions, learners, questions generated, avg mastery |
| `getLiveActivity(db, limit)` | Latest N session update events for a live activity feed |
| `getMasteryDistribution(db)` | Buckets all learners' mastery into 5 tiers: 0-20, 21-40, 41-60, 61-84, 85-100 |
| `getTopicPerformance(db)` | Per-topic stats: avg mastery, mastery rate (>=85%), avg questions needed, remediation count |
| `getAllLearners(db, filters, page, limit)` | Paginated learner roster with mastery, session count, and remediation status |
| `getLearnerProfile(db, learnerId)` | Full history for a single learner: sessions, questions, answers, updates, and reports |
| `getLearnerMasteryTrend(db, learnerId)` | Time-series mastery data for charting a learner's progress over time |
| `getAllSessions(db, filters, page, limit)` | Paginated session list with latest mastery and feedback report status |
| `getSessionDetail(db, sessionId)` | Full detail: session + questions + answers + state updates + feedback report |
| `getQuestionBank(db, filters, page, limit)` | Searchable, filterable, paginated question bank (by topic, difficulty, type, Bloom's level) |
| `getQuestionStats(db)` | Question bank breakdown by type, difficulty, and most-assessed topic |
| `getMasteryAnalytics(db, topic)` | Cohort mastery heatmap, topic distribution, difficulty progression, and Bloom's distribution |
| `getRemediationSummary(db)` | Total activations, success rate, avg questions in remediation, per-episode breakdown |
| `getRemediationByTopic(db)` | Per-topic remediation frequency and mastery delta (before vs. after) |
| `getAllFeedbackReports(db, filters, page, limit)` | Paginated feedback report summaries with grade, accuracy, and topic coverage |
| `getFeedbackReport(db, sessionId)` | Full feedback report document for a single session |
| `getGradeDistribution(db)` | Count of reports by grade: Excellent, Good, Satisfactory, Needs Improvement, Poor |
| `getCommonMisconceptions(db, limit)` | Ranked list of the most frequent misconceptions across all learners |

### Key Algorithm Details

**Mastery Tiers (getMasteryDistribution)**

| Tier | Range | Meaning |
|---|---|---|
| Critical Gaps | 0–20% | Fundamental misunderstanding |
| Significant Gaps | 21–40% | Major knowledge holes |
| Developing | 41–60% | Partial understanding |
| Proficient | 61–84% | Good grasp, needs refinement |
| Mastered | 85–100% | Full mastery achieved |

**Mastery Threshold:** A topic is considered "mastered" when `current_topic_mastery >= 85`.

> See [`docs/implementation.md`](./docs/implementation.md) for detailed algorithm explanations.

---

## Security

### JWT Authentication (`src/middleware/auth.js`)

All `/api/ame/*` routes are protected by JWT middleware.

- Expects `Authorization: Bearer <token>` header.
- Verifies the token using `JWT_SECRET` from environment variables.
- On success, injects the decoded payload (including `student_id`) into `req.user`.
- Returns `401 Unauthorized` if the token is missing or invalid.

### Admin Role Guard

An `adminAuth` middleware is available (reserved for future admin routes):

- Extends `auth` to also verify `req.user.role === 'admin'`.
- Returns `403 Forbidden` if the user is not an admin.

### HTTP Security Headers

[Helmet.js](https://helmetjs.github.io/) is applied globally, setting headers including:
- `Content-Security-Policy`
- `X-Content-Type-Options`
- `X-Frame-Options`
- `Strict-Transport-Security`

### CORS

Restricted to the single origin defined by `FRONTEND_URL`, with credentials enabled.

---

## Error Handling

All errors are handled by the global middleware in `src/middleware/errorHandler.js`.

**Standard Error Response Format:**
```json
{
  "success": false,
  "message": "Human-readable error message",
  "error": "Stack trace (development mode only)"
}
```

| HTTP Status | Meaning |
|---|---|
| `400` | Bad Request — missing or invalid input field |
| `401` | Unauthorized — missing or invalid JWT |
| `403` | Forbidden — insufficient permissions |
| `404` | Not Found — resource does not exist |
| `500` | Internal Server Error — unexpected failure |

Process-level error guards in `server.js` also capture `uncaughtException` and `unhandledRejection` events, logging them before controlled shutdown.

---

## Postman Collection

A ready-to-use Postman collection is located at:

```
postman/AME_Agent_API.postman_collection.json
```

**To Import:**
1. Open Postman.
2. Click **Import** → **Upload Files**.
3. Select `AME_Agent_API.postman_collection.json`.
4. Set the collection variable `base_url` to `http://localhost:5002`.
5. Add your JWT token to the **Authorization** tab of any protected request.

---

## Deployment

### Production Environment Variables

```bash
PORT=5002
NODE_ENV=production
MONGODB_URI=mongodb+srv://<user>:<pass>@cluster.mongodb.net/ame_agent_db
N8N_BASE_URL=https://your-n8n.example.com
N8N_WEBHOOK_PATH=/webhook
JWT_SECRET=<256-bit-secure-random-string>
FRONTEND_URL=https://your-frontend.example.com
```

### Start in Production

```bash
npm start
```

### Recommended Setup

- Use **PM2** for process management and clustering:
  ```bash
  pm2 start server.js --name ame-agent -i max
  ```
- Sit behind **Nginx** or **Caddy** as a reverse proxy with TLS termination.
- Use **MongoDB Atlas** for managed, scalable database hosting.
- Ensure your n8n instance is reachable from the AME Agent server.

---

## Related Services

This microservice is part of the **Mentora Backend** ecosystem:

| Service | Path | Description |
|---|---|---|
| Assessment Agent | `services/assessment-agent/` | This service — adaptive assessment & mastery evaluation |
| *(Other services)* | `services/*/` | Other Mentora microservices |

---

*Built with love by the **MENTORA Team***
