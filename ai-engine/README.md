# MENTORA - AI Engine (Learning Generator)

**Author:** Jayarathna S.K.N.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Technology Stack](#technology-stack)
- [How It Fits In The Learning Generator](#how-it-fits-in-the-learning-generator)
- [Project Structure](#project-structure)
- [API Reference](#api-reference)
- [Code Execution Sandbox](#code-execution-sandbox)
- [AI Generation Engine](#ai-generation-engine)
- [Frontend Integration](#frontend-integration)
- [Scenarios & Usage Flows](#scenarios--usage-flows)
- [Configuration](#configuration)
- [Running Locally](#running-locally)
- [Docker & Deployment](#docker--deployment)

---

## Overview

The **AI Engine** is a self-contained FastAPI (Python) microservice that powers **all AI-assisted and code-execution features** of the MENTORA personalized learning platform. It runs on port `5010` and is consumed **directly by the Next.js frontend** — it does not sit behind the LMG Service and requires no authentication (it is a local, trusted service).

It provides eleven capabilities:

| Capability | Endpoint | Purpose |
|------------|----------|---------|
| Java code execution | `POST /api/execute` | Compile & run student Java code in an isolated sandbox |
| AI feedback | `POST /api/feedback` | Encouraging, tutor-style feedback on submitted code |
| Execute + feedback | `POST /api/run-with-feedback` | Run code and get feedback in a single call |
| Explain Simpler | `POST /api/explain-simpler` | Break a concept/step down for complete beginners |
| Real-life Analogy | `POST /api/analogy` | Explain a concept using a real-world comparison |
| Explain highlighted code | `POST /api/explain-code` | Explain a specific selected block of code |
| AI error fixing | `POST /api/fix-error` | Diagnose a compile/runtime error and return a fixed version |
| Code review | `POST /api/code-review` | Annotated review (line ranges, severity, score) |
| Concept flashcards | `POST /api/flashcards` | Generate revision flashcards from code |
| JUnit test generation | `POST /api/generate-tests` | Generate JUnit 5 test cases from code |
| Health check | `GET /health` | Liveness probe for the service |

All LLM generation is performed against a **local Ollama instance** (port `11434`). The service exposes an open CORS policy (`*`) so the browser-based frontend can call it directly.

> **Role boundary:** The AI Engine does **not** generate the structured learning materials (lessons, quizzes, concept graphs). That job belongs to the **n8n agentic pipeline** inside the LMG Service, which uses Ollama directly with `qwen2.5-coder:7b`. The AI Engine instead powers the *interactive learning experience* that students use **after** materials are generated — running code, getting feedback, and receiving AI tutoring within the material workspace and the standalone code sandbox.

---

## Architecture

```
┌───────────────────────────────────────────────────────────────────────┐
│                      FRONTEND (Next.js · Port 3000)                   │
│                                                                       │
│  ┌────────────────────┐    ┌─────────────────────────────────────┐    │
│  │  Material Workspace │    │      Code Sandbox (/workspace)      │    │
│  │  [materialId]/page  │    │                                     │    │
│  └─────────┬──────────┘    │  Run · Feedback · Explain · Fix      │    │
│            │               │  Review · Flashcards · JUnit Tests   │    │
│  ┌─────────▼──────────┐    └──────────────────┬──────────────────┘    │
│  │   aiEngine.ts API   │                       │                      │
│  │   (singleton client)│◄──────────────────────┘                      │
│  └─────────┬──────────┘                                               │
└────────────┼──────────────────────────────────────────────────────────┘
             │  HTTP REST (no auth) · NEXT_PUBLIC_AI_ENGINE_API_URL
             ▼
┌───────────────────────────────────────────────────────────────────────┐
│                    AI ENGINE (FastAPI · Port 5010)                     │
│                                                                       │
│  app/main.py          app bootstrap, CORS, GET /health                │
│  app/routes.py        APIRouter — all /api/* endpoints                │
│  app/models.py        Pydantic request/response schemas               │
│  app/config.py        Environment configuration                       │
│        │                                                              │
│  ┌─────▼────────────────────┐      ┌────────────────────────────┐     │
│  │ services/executor.py     │      │ services/ollama_service.py  │     │
│  │  Java sandbox (javac+java)│      │  system prompts + LLM calls  │     │
│  └──────────┬───────────────┘      │  + JSON parsing + retries    │     │
│             │                      └─────────────┬──────────────┘     │
│             │                                  │                      │
└─────────────┼──────────────────────────────────┼──────────────────────┘
              │                                  │  HTTP /api/chat
              ▼                                  ▼
┌───────────────────────────────┐  ┌───────────────────────────────┐
│   Java Runtime (JDK)          │  │        Ollama · Port 11434     │
│   sandboxed temp dirs         │  │  llama3:8b        (general)    │
│   javac / java subprocesses   │  │  qwen2.5-coder:7b (structured) │
└───────────────────────────────┘  └───────────────────────────────┘
```

**Integration with the rest of the platform**

| From | To | Protocol | Auth | Purpose |
|------|----|----------|------|---------|
| Frontend (`aiEngine.ts`) | AI Engine | HTTP REST | None (local) | Code execution + all AI features |
| AI Engine | Ollama | HTTP REST | None (local) | LLM inference (`/api/chat`) |
| AI Engine | Local JDK | Subprocess | — | Sandboxed Java compile/run |

The AI Engine is deployed alongside the LMG Service (`5012`), User Service (`3001`), and n8n (`5678`) via `docker-compose.yml`. Unlike the LMG Service, it is **not** behind JWT authentication and talks to the browser directly.

---

## Technology Stack

| Category | Technology | Purpose |
|----------|-----------|---------|
| **Runtime** | Python 3.11+ | Server runtime |
| **Framework** | FastAPI 0.115 | Async HTTP framework, OpenAPI docs |
| **Server** | Uvicorn 0.30 | ASGI server |
| **Validation** | Pydantic 2.9 | Request/response models |
| **HTTP Client** | httpx 0.27 | Async calls to Ollama |
| **LLM** | Ollama + `llama3:8b` | General tutoring / feedback model |
| **LLM (code)** | Ollama + `qwen2.5-coder:7b` | Structured output (JSON), review, tests, fixes |
| **Code Execution** | JDK (headless) | Sandboxed `javac` + `java` |
| **Container** | Docker (python:3.11-slim + default-jdk-headless) | Containerization |

---

## How It Fits In The Learning Generator

The learning-generator feature of MENTORA has **two distinct AI stages**:

```
┌────────────────────────────────────────────────────────────────────────┐
│  STAGE 1 — MATERIAL GENERATION (offline, n8n + Ollama, async jobs)     │
│                                                                        │
│  Mastery profile → Concept-graph gate → n8n agentic pipeline →          │
│  LLM generates lesson/assessment → Quality + Validation agents →        │
│  structured_material stored in MongoDB (served by LMG Service :5012)    │
│                                                                        │
│  NOT handled by the AI Engine.                                         │
└────────────────────────────────────────────────────────────────────────┘
                                │
                                ▼  student opens a generated material
┌────────────────────────────────────────────────────────────────────────┐
│  STAGE 2 — INTERACTIVE LEARNING (online, AI Engine :5010)              │
│                                                                        │
│  Material Workspace / Code Sandbox ──► aiEngine.ts ──► FastAPI ──►      │
│  Ollama (llama3:8b / qwen2.5-coder:7b)                                 │
│                                                                        │
│  THIS README documents the AI Engine (Stage 2).                        │
└────────────────────────────────────────────────────────────────────────┘
```

In short:

1. The **LMG Service** generates and stores the structured material (lessons, examples, quizzes, practice/debug code) — powered by the n8n agentic pipeline and Ollama directly.
2. The **AI Engine** brings that static content to life at learning time: the student edits code in the workspace, the frontend calls the AI Engine to **execute it**, get **AI feedback**, ask for a **simpler explanation** or **real-life analogy**, **fix errors**, **review code**, and generate **flashcards** or **JUnit tests**.

---

## Project Structure

```
ai-engine/
├── README.md                                   # This document
└── learning-generator/
    ├── Dockerfile                              # python:3.11-slim + JDK, port 5010
    ├── .dockerignore                           # Excludes __pycache__, .env, .venv
    ├── requirements.txt                        # fastapi, uvicorn, pydantic, httpx
    └── app/
        ├── __init__.py                         # Package marker
        ├── main.py                             # FastAPI app, CORS, /health, router mount
        ├── config.py                           # Environment configuration
        ├── models.py                           # Pydantic request/response schemas
        ├── routes.py                           # APIRouter with all /api/* endpoints
        └── services/
            ├── __init__.py                     # Package marker
            ├── executor.py                     # Java sandbox (extract class → javac → java)
            └── ollama_service.py               # System prompts, LLM calls, JSON parsing, retries
```

---

## API Reference

All endpoints are prefixed with `/api` (except `/health`). Requests/responses are JSON. The base URL for the frontend is `NEXT_PUBLIC_AI_ENGINE_API_URL` (default `http://localhost:5010`).

### `GET /health`

Liveness probe used by the frontend (`aiEngineApi.healthCheck()`).

```json
{ "service": "ai-engine", "status": "running" }
```

### `POST /api/execute`

Compile and run Java source code in a sandbox.

**Request**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `code` | string (1–50000) | Yes | Java source code to execute |
| `context` | string | No | Context for AI feedback (`practice`, `example`, `debug`, `sandbox`, ...) |
| `stdin` | string | No | Standard input for `Scanner` / `BufferedReader` programs |

**Response** (`CodeExecuteResponse`)

| Field | Type | Description |
|-------|------|-------------|
| `success` | boolean | Execution succeeded |
| `output` | string/null | Captured stdout |
| `error` | string/null | Compilation or runtime error message |
| `is_compilation_error` | boolean | `true` if compilation failed |
| `exit_code` | integer/null | Process exit code |

### `POST /api/feedback`

Generate tutor-style feedback on the student's code.

**Request:** `{ code, output?, error?, context? }`

**Response** (`AIFeedbackResponse`): `{ feedback: string, model: string }`

### `POST /api/run-with-feedback`

Execute the code **and** generate feedback in one round-trip.

**Response** (`CombinedResponse`): `{ execution: CodeExecuteResponse, feedback: string|null, model: string|null }`

If Ollama fails, `feedback` degrades to `"AI feedback unavailable right now."`.

### `POST /api/explain-simpler`

Explain a tutorial section or code example like the student is a complete beginner.

**Request** (`AIInsightRequest`): `{ content (1–50000), topic?, stepType? }`

`stepType` maps to a friendly label:

| stepType | Label |
|----------|-------|
| `intro` | introduction section |
| `concepts` | concept explanation |
| `guide` | step-by-step guide |
| `example` / `practice` / `debug` | treated as Java code blocks |
| `mistakes` | common mistakes section |

**Response** (`AIInsightResponse`): `{ insight: string, model: string, type: "explain_simpler" }`

### `POST /api/analogy`

Generate a creative real-world analogy for a concept.

**Request:** `AIInsightRequest` (same as above)

**Response:** `{ insight: string, model: string, type: "analogy" }`

### `POST /api/explain-code`

Explain a highlighted section of code within the full source.

**Request** (`ExplainCodeRequest`): `{ code (1–50000), highlighted_code (1–5000), question? }`

**Response** (`ExplainCodeResponse`): `{ explanation: string, model: string }`

### `POST /api/fix-error`

Diagnose a compile/runtime error and return a complete corrected version.

**Request** (`FixErrorRequest`): `{ code (1–50000), error (1–50000) }`

**Response** (`FixErrorResponse`): `{ suggested_fix: string, fixed_code: string, explanation: string, model: string }`

`fixed_code` preserves the student's original code and adds `// FIX:` comments on every changed line.

### `POST /api/code-review`

Static review of Java code with line-level annotations and a score.

**Request** (`CodeReviewRequest`): `{ code (1–50000), focus? }` — `focus`: `performance` | `readability` | `best_practices` | `all`

**Response** (`CodeReviewResponse`):

```json
{
  "annotations": [
    {
      "line_start": 5,
      "line_end": 5,
      "category": "performance",
      "severity": "medium",
      "message": "...",
      "suggestion": "..."
    }
  ],
  "summary": "2-3 sentence review",
  "overall_score": 7,
  "model": "llama3:8b"
}
```

### `POST /api/flashcards`

Generate 3–5 concept flashcards from the concepts used in the code.

**Request** (`FlashcardRequest`): `{ code (1–50000) }`

**Response** (`FlashcardResponse`): `{ flashcards: [{ concept, definition, example, difficulty }], model }`

### `POST /api/generate-tests`

Generate a complete JUnit 5 test class (normal, edge, and error cases).

**Request** (`TestGeneratorRequest`): `{ code (1–50000), class_name? }`

**Response** (`TestGeneratorResponse`): `{ test_code: string, test_explanation: string, model: string }`

---

## Code Execution Sandbox

Implemented in `app/services/executor.py`. Execution is fully **sandboxed** by creating a temporary directory per request and running `javac`/`java` as subprocesses inside it, then deleting the directory.

### Flow

```
1. extract_class_name(code)
   ├── regex: public class <Name>  → class name
   ├── regex: class <Name>         → class name
   └── fallback: "Main"

2. tempfile.mkdtemp(prefix="java-sandbox-")
   └── write <ClassName>.java

3. javac <ClassName>.java          (timeout: EXECUTION_TIMEOUT = 15s)
   ├── returncode != 0  → Compilation error response
   │                     { success:false, error: stderr, is_compilation_error:true }
   └── ok → continue

4. java -cp <tmpdir> <ClassName>   (timeout: RUN_TIMEOUT = 10s, optional stdin)
   ├── returncode != 0  → Runtime error response
   │                     { success:false, output: stdout?, error: stderr|exit code,
   │                       is_compilation_error:false }
   └── ok → { success:true, output: stdout }

5. finally: shutil.rmtree(tmp_dir)  (cleanup always runs)
```

### Guardrails

- **Compile timeout** — `EXECUTION_TIMEOUT` (default 15s), returns the `javac` stderr on failure.
- **Run timeout** — `RUN_TIMEOUT` (default 10s); infinite loops / long-running code return `"Execution timed out. Check for infinite loops or long-running operations."`
- **Isolation** — every request compiles in its own temp dir, so no two students' classes collide.
- **Error classification** — compilation vs runtime errors are distinguished (`is_compilation_error`) so the frontend can render different UI (red vs amber error styling).

---

## AI Generation Engine

Implemented in `app/services/ollama_service.py`. Every AI capability is a dedicated **system prompt** that instructs the model with strict behavior rules, then a user prompt is assembled from the request.

### System Prompts

| Feature | System prompt rule |
|---------|--------------------|
| Feedback (`SYSTEM_PROMPT`) | Concise 3–5 sentences, encouraging, hints not full solutions for practice |
| Explain Simpler (`SYSTEM_PROMPT_SIMPLE`) | Explain like the student is 12, no jargon, ≤5–6 short paragraphs |
| Analogy (`SYSTEM_PROMPT_ANALOGY`) | One clear real-world analogy, then map elements back to the code |
| Highlighted code (`SYSTEM_PROMPT_EXPLAIN`) | Explain ONLY the highlighted block, ≤3–4 paragraphs |
| Fix error (`SYSTEM_PROMPT_FIX`) | Root-cause the error, return COMPLETE code with `// FIX:` comments, JSON only |
| Code review (`SYSTEM_PROMPT_REVIEW`) | Line-numbered annotations, severity, 1–10 score, JSON only |
| Flashcards (`SYSTEM_PROMPT_FLASHCARDS`) | 3–5 concepts, definition + mini example + difficulty, JSON array |
| JUnit tests (`SYSTEM_PROMPT_TESTS`) | Full JUnit 5 class, `@Test`/`@DisplayName`/`assertEquals`/`assertThrows`, JSON only |

### LLM Call (`_call_ollama`)

- `POST {OLLAMA_BASE_URL}/api/chat` with `{ model, messages, stream: false, options: { temperature, num_predict } }`.
- Async `httpx` client with a 60s timeout.
- Graceful degradation: on timeout → `"Response is taking longer than usual. Please try again."`; on failure → `"Unable to generate response right now. Please try again."`

### Structured Output (JSON) — `_call_ollama_json`

LLMs frequently emit malformed JSON, so a 3-strategy recovery pipeline is used:

1. **Code-fence extraction** — strip ```json ... ``` fences and parse.
2. **Balanced JSON scan** (`_find_balanced_json`) — string-aware depth counter that locates the outermost balanced `{…}` or `[…]`.
3. **LLM-JSON repair** (`_fix_llm_json`) — re-escapes unescaped newlines (`\n`), tabs (`\t`), and quotes (`\"`) inside string literals.

### Model Fallback & Retry Strategy

Structured-output endpoints (fix, review, flashcards, tests) try `llama3:8b` first, then escalate:

```
Attempt 1: llama3:8b      (general model)         → validate shape
Attempt 2: qwen2.5-coder:7b (code model)           → validate shape
Attempt 3: qwen2.5-coder:7b + ultra-strict prompt  → temperature 0.1, "JSON API only"
Final:    friendly empty/error response (e.g. empty annotations list)
```

This maximizes the chance of valid JSON while guaranteeing the endpoint never crashes the UI.

---

## Frontend Integration

### API client — `src/lib/api/aiEngine.ts`

- **Base URL:** `NEXT_PUBLIC_AI_ENGINE_API_URL` (default `http://localhost:5010`).
- **Auth:** none.
- **Class:** `AIEngineApi` (exported as a singleton `aiEngineApi`); throws on non-OK responses.
- Typed interfaces mirror the AI Engine's Pydantic models: `CodeExecutionResult`, `AIFeedbackResult`, `AIInsightResult`, `CodeReviewAnnotation`, `CodeReviewResult`, `Flashcard`, `FlashcardResult`, `TestGeneratorResult`.

| Method | Endpoint | Used by |
|--------|----------|---------|
| `executeCode(code, context?, stdin?)` | `POST /api/execute` | Material workspace + Code sandbox |
| `getFeedback(code, output?, error?, context?)` | `POST /api/feedback` | Material workspace + Code sandbox |
| `runWithFeedback(code, context?, stdin?)` | `POST /api/run-with-feedback` | (available for combined runs) |
| `healthCheck()` | `GET /health` | Connectivity checks |
| `explainSimpler(content, topic?, stepType?)` | `POST /api/explain-simpler` | Material workspace "Explain Simpler" |
| `getAnalogy(content, topic?, stepType?)` | `POST /api/analogy` | Material workspace "Real-life Analogy" |
| `explainHighlightedCode(code, highlightedCode, question?)` | `POST /api/explain-code` | Sandbox inline explanation popup |
| `fixError(code, error)` | `POST /api/fix-error` | Sandbox "AI Fix This Error" |
| `codeReview(code, focus?)` | `POST /api/code-review` | Sandbox Review tab |
| `getFlashcards(code)` | `POST /api/flashcards` | Sandbox Flashcards drawer |
| `generateTests(code, className?)` | `POST /api/generate-tests` | Sandbox JUnit drawer |

### Frontend call sites

1. **Material Workspace** — `src/app/(dashboard)/learning-generator/materials/[materialId]/page.tsx`
   - `handleRunCode` → `executeCode` → on success `getFeedback`; successful practice runs auto-complete the step and call `updateProgress`.
   - `handleExplainSimpler` / `handleRealLifeAnalogy` → assemble the current step's content (`intro`, `concepts`, `guide`, `mistakes`, `example`, `practice`, `debug`) into a `content` string, pass `topic` + `stepType`, and cache the insight in `sessionStorage` (`mentora_<materialId>_<step>_<key>`).
2. **Code Sandbox** — `src/app/(dashboard)/learning-generator/workspace/page.tsx`
   - `handleRunCode` → `executeCode("sandbox")` → `getFeedback`, with JSON auto-formatting and a synthesized execution timeline.
   - `handleExplainSelected` → `explainHighlightedCode` for text selected with the mouse (5–500 chars).
   - `handleFixError` → `fixError`; "Apply Fix" replaces the editor code with `fixed_code`.
   - `handleCodeReview` → `codeReview`; annotations rendered as color-coded line overlays in the editor.
   - `handleGenerateFlashcards` → `getFlashcards`; `handleGenerateTests` → `generateTests("Main")`.

---

## Scenarios & Usage Flows

### Scenario 1 — Learning Material Workspace (guided path)

A student opens a generated material and works through the 8-step learning path.

```
Step (example) ──► student clicks "Explain Simpler"
                      │
                      ▼
   page.tsx assembles step content + topic + stepType
                      │
                      ▼
   aiEngineApi.explainSimpler(content, topic, "example")
                      │
                      ▼
   AI Engine /api/explain-simpler → Ollama llama3:8b
                      │
                      ▼
   insight cached to sessionStorage → rendered in InsightPanel

Step (practice) ──► student edits starter code in CodeEditorPanel
                      │
                      ▼
   aiEngineApi.executeCode(code, "practice")
                      │
                      ▼
   AI Engine sandbox: javac → java  →  output/error
                      │
                      ▼
   aiEngineApi.getFeedback(code, output|error, "practice")
                      │
                      ▼
   Feedback shown in AI Feedback tab
   (successful practice run → step auto-completed + progress saved)
```

### Scenario 2 — Standalone Code Sandbox (free practice)

A student opens `/learning-generator/workspace` and iterates freely.

```
1. RUN        aiEngineApi.executeCode(code, "sandbox", stdin)
              → Output tab (exit code, stdout, JSON auto-format, timeline)
              → AI Feedback tab (Mentora AI)

2. SELECT     highlight a code block → "Explain This"
              aiEngineApi.explainHighlightedCode(code, highlighted)

3. FIX        on error → WorkspaceTabs Fix tab → "AI Fix This Error"
              aiEngineApi.fixError(code, error)
              → suggested_fix + fixed_code (// FIX: comments) → "Apply Fix"

4. REVIEW     WorkspaceTabs Review tab → "Start Review"
              aiEngineApi.codeReview(code)
              → overall_score /10 + color-coded annotations overlaid on the editor

5. LEARN      Flashcards drawer → aiEngineApi.getFlashcards(code)
              → concept flashcards with difficulty badges

6. TEST       Tests drawer → aiEngineApi.generateTests(code, "Main")
              → JUnit 5 test class with explanation (copyable)
```

### Scenario 3 — Combined run (single round-trip)

Callers that only need a quick "did it work + what do I think" flow can use `POST /api/run-with-feedback` instead of chaining `execute` + `feedback`, halving the latency of two HTTP round-trips.

---

## Configuration

All configuration is read from environment variables in `app/config.py`.

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama HTTP endpoint |
| `OLLAMA_MODEL` | `llama3:8b` | General-purpose model (feedback, explanations, analogies) |
| `OLLAMA_CODE_MODEL` | `qwen2.5-coder:7b` | Code model (structured JSON, review, fixes, tests) |
| `EXECUTION_TIMEOUT` | `15` | Compile timeout in seconds |
| `RUN_TIMEOUT` | `10` | Runtime timeout in seconds |
| `JAVA_HOME` | `""` | Optional Java home override |
| `TEMP_DIR` | `/tmp/java-sandbox` | Reserved sandbox base directory |

**Prerequisites on the host:** a JDK must be installed (the Docker image includes `default-jdk-headless`), and Ollama must be running with `llama3:8b` and `qwen2.5-coder:7b` pulled:

```bash
ollama pull llama3:8b
ollama pull qwen2.5-coder:7b
```

---

## Running Locally

```bash
# 1. Start Ollama and pull the models (see above)

# 2. Install Python dependencies
cd ai-engine/learning-generator
pip install -r requirements.txt

# 3. Run the service
uvicorn app.main:app --host 0.0.0.0 --port 5010

# 4. Verify
curl http://localhost:5010/health
# Interactive API docs (Swagger UI):
#   http://localhost:5010/docs
```

---

## Docker & Deployment

### Dockerfile

- Base image `python:3.11-slim`.
- Installs `default-jdk-headless` (needed for the Java sandbox).
- Installs `requirements.txt`, copies the app, exposes `5010`.
- Runs `uvicorn app.main:app --host 0.0.0.0 --port 5010`.

### docker-compose (`docker-compose.yml`)

```yaml
ai-engine:
  build:
    context: ./ai-engine/learning-generator
  container_name: mentora-ai-engine
  ports:
    - "5010:5010"
  extra_hosts:
    - "host.docker.internal:host-gateway"
  environment:
    OLLAMA_BASE_URL: ${OLLAMA_BASE_URL:-http://host.docker.internal:11434}
    OLLAMA_MODEL: ${OLLAMA_MODEL:-llama3:8b}
    OLLAMA_CODE_MODEL: ${OLLAMA_CODE_MODEL:-qwen2.5-coder:7b}
```

The `host.docker.internal` mapping lets the container reach an Ollama instance running on the host machine.

### Production (`docker-compose.prod.yml`) & CI

- Production uses the prebuilt image `ghcr.io/${GITHUB_REPOSITORY}/ai-engine:latest` with the same port/env mapping.
- `.github/workflows/ci.yml` builds the image from `./ai-engine/learning-generator` and pushes `ai-engine:latest` + `ai-engine:<sha>` to the GitHub Container Registry.

---

## Notes & Graceful Degradation

- If Ollama is offline or times out, every AI endpoint still returns a valid (friendly) fallback so the UI never breaks.
- If the Java toolchain is missing, `execute` returns a descriptive `Execution failed: ...` error.
- Structured-output endpoints validate the returned shape and retry with stricter prompts + the code model before giving up.
- The service is intentionally **unauthenticated** and locally bound; it should never be exposed to the public internet without a reverse proxy (the browser frontend is the only intended consumer).
