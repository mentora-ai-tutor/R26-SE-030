# Mentora — GitHub OAuth + Gemini Review + Java Sandbox Integration Plan

| Field | Value |
|---|---|
| Document version | 1.1 |
| Date | 2026-05-05 |
| Status | Approved for implementation |
| Scope | `mentora-frontend/`, `services/user service/`, `services/knowledge-analysis/`, new `services/code-sandbox/` |
| Out of scope | n8n, redesign of frontend visual language, replacing existing JWT auth |

---

## 1. Executive summary

This document specifies the end-to-end design for three new capabilities on top of the existing Mentora codebase:

1. **GitHub OAuth integration** (Authorization Code Flow) so a logged-in student can link their GitHub account separately from their app login.
2. **Repo review pipeline** that picks five repos at random from the student's public + private repos and reviews them through the Vertex AI LLM router. The router keeps Gemini 3.1 Pro Preview as tier 0 for future preview access, but current development accepts Gemini 2.5 Pro as the effective primary because `chapmanvoice` does not have preview-model access yet.
3. **Java sandbox** that runs in parallel to the repo review — a five-question ladder (MCQ, predict-output, short-code) with paste-blocked Monaco editor and a Docker-isolated Java runner for the executable questions.

The frontend visual language is preserved. All new work fits under existing dashboard pages or adds sibling pages that reuse the established Tailwind palette.

---

## 2. Current state of the codebase (what already works)

| Layer | Path | Stack | Reused as-is |
|---|---|---|---|
| Frontend | `mentora-frontend/` | Next.js (custom build — see `AGENTS.md`), Tailwind, shadcn UI | Auth pages, dashboard shell, `knowledge-assist/sandbox/` mock telemetry view |
| User auth | `services/user service/` | Node + Express + Mongo + JWT | `/api/auth/{register,login,refresh,logout}`, `Student` model, lockout, refresh-token rotation |
| Knowledge analysis | `services/knowledge-analysis/` | FastAPI + httpx | `GitHubFetcher`, `BehaviorAnalysisService`, 10-step analysis pipeline (currently Ollama/llama3) |
| Orchestration | `docker-compose.yml` | Compose v2 | mongo + user-service + knowledge-analysis + frontend |

We are **extending**, not rewriting. The Ollama path stays as a last-resort fallback.

---

## 3. Target state (what we are adding)

```
                            +--------------------------+
                            |  mentora-frontend (3000) |
                            |  - login / signup        |
                            |  - GH onboarding card    |
                            |  - forensics page (real) |
                            |  - sandbox-live page     |
                            +-----+-------+------------+
                                  |       |
                JWT auth          |       |   WS + REST
                                  v       v
   +----------------------+  +-------------------+  +-----------------------+
   | user-service (3001)  |  | knowledge-anlys   |  | code-sandbox (5008)   |
   | - email/pwd auth     |  | (5007)            |  | - WS Java REPL        |
   | - GH OAuth (Method1) |  | - select-repos    |  | - Docker per-session  |
   | - GithubCredential   |  | - review-top-5    |  | - run + grade         |
   |   (encrypted token)  |  | - LLM router      |  | - integrity scoring   |
   +-----+----------------+  +---------+---------+  +-----------+-----------+
         |                             |                        |
         |         +-------------------+------------------------+
         |         |                   |                        |
         v         v                   v                        v
   +-----------+  +--------------------------+  +---------------------------+
   | MongoDB   |  | Vertex AI                |  | Docker daemon (host)      |
   | (27017)   |  |   gemini-3.1-pro-preview |  | mentora/java-runner:21    |
   |           |  |   gemini-2.5-pro (GA)    |  | (one container per        |
   |           |  |   gemini-2.5-flash (GA)  |  |  sandbox session, killed  |
   |           |  | + Ollama llama3 (local)  |  |  on disconnect)           |
   +-----------+  +--------------------------+  +---------------------------+
```

### 3.1 End-to-end flow

```
Login (email/password)
      |
      v
JWT issued, AuthContext populated
      |
      v
(dashboard)/layout.tsx checks user.github.linked
      |
      | not linked
      v
Onboarding card -> "Connect GitHub" CTA opens popup
      |
      v
Popup -> /api/github/oauth/start -> GitHub consent (Method 1)
      |
      v
GitHub redirects -> /api/github/oauth/callback -> token exchange
      |
      v
postMessage('gh-linked') -> popup closes
      |
      v
Forensics page mounts. Two parallel asyncio tasks fire:

   Track A (heavy)                       Track B (light, paints first)
   ---------------                       -----------------------------
   1. select_random_repos(5)             1. read student.profile.java_level
   2. fetch source bundle per repo       2. generate Q1 with thinking=low
   3. create Vertex context cache        3. show Q1 in sandbox-live page
   4. review with thinking=high          4. spawn warm Java container only
   5. infer java_level + signals            when student opens a short_code
   6. stream RepoReview cards to UI         question
   7. finished -> regenerate Q2..Q5
      with refined java_level signals
```

Track A failure does not kill Track B. Track B's first paint target is < 3 seconds.

---

## 4. Module specifications

### 4.1 GitHub OAuth (Method 1 — Authorization Code Flow)

**OAuth App registration (one-time, manual):**

1. https://github.com/settings/developers -> OAuth Apps -> New OAuth App
2. Application name: `Mentora Dev`
3. Homepage URL: `http://localhost:3000`
4. Authorization callback URL: `http://localhost:3001/api/github/oauth/callback`
5. Register, copy `Client ID` and generate `Client Secret` (shown once).
6. Place in `services/user service/.env` — never commit:

```
GH_CLIENT_ID=Iv1.xxxxxxxxxxxxxxxx
GH_CLIENT_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
GH_OAUTH_SCOPE=repo
GH_OAUTH_CALLBACK_URL=http://localhost:3001/api/github/oauth/callback
GH_TOKEN_KEK=<32-byte hex; derived from JWT_REFRESH_SECRET via HKDF at boot>
```

**Routes (new, on user-service):**

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/api/github/oauth/start` | JWT | Returns `{ url, state }`. `state` = HMAC(student_id, server_nonce, ts) so callback can verify which student is linking. |
| GET | `/api/github/oauth/callback` | none | GitHub-initiated. Verifies `state`, exchanges `code` for `access_token`, encrypts and stores. Returns a small HTML page that does `window.opener.postMessage({type:'gh-linked', login}, ORIGIN); window.close();`. |
| POST | `/api/github/unlink` | JWT | Revokes token (`DELETE /applications/{client_id}/grant`), removes credential. |
| GET | `/api/github/status` | JWT | Returns `{ linked, gh_login, scopes, linked_at }` — used by the dashboard layout gate. |

**Token storage:**

- Tokens encrypted with AES-256-GCM. Key = `GH_TOKEN_KEK` (32 bytes), IV per record (12 bytes), AAD = `student_id`.
- Stored in a separate collection `GithubCredential` so we can rotate without touching the student doc:

```js
{
  _id, student_id (ref Student), gh_user_id, gh_login,
  scopes, ciphertext, iv, tag, linked_at, last_used_at
}
```

- `Student.github` becomes a small projection: `{ linked: bool, gh_login, linked_at, credential_ref }`.

**Frontend integration:**

- `src/components/onboarding/GithubLinkCard.tsx` — re-uses `AuthCard`, `AuthButton`, and the same Tailwind palette as `auth/`. No new design tokens.
- Mounted from `(dashboard)/layout.tsx` as a non-dismissible overlay when `useAuth().user.github.linked !== true`.
- CTA opens a popup: `window.open(url, 'gh-oauth', 'width=720,height=820,popup=yes')`.
- Listens for `message` event with `type === 'gh-linked'`, then calls `refreshUser()` and removes the overlay.

### 4.2 LLM provider layer with fallback chain

**New module:** `services/knowledge-analysis/app/services/llm/`

```
llm/
  __init__.py        # public: get_router()
  base.py            # LLMClient ABC (generate_json, generate_with_tools)
  router.py          # tiered fallback, dead-tier caching, retry policy
  gemini_provider.py # google-genai SDK; vertexai=True client
  ollama_provider.py # wraps existing OllamaClient
```

**Provider tiers (in order of attempt):**

| Tier | Model | Source | Use cases |
|---|---|---|---|
| 0 | `gemini-3.1-pro-preview` | Vertex AI, preview | Repo review (thinking=high), agentic tool calls |
| 0t | `gemini-3.1-pro-preview-customtools` | Vertex AI, preview | Sandbox grader (when `tools=` passed) |
| 1 | `gemini-2.5-pro` | Vertex AI, GA | All tier-0 tasks on demotion |
| 2 | `gemini-2.5-flash` | Vertex AI, GA | Question generation, MCQ-rubric, cheap classification |
| 3 | `ollama:llama3` | local Ollama | Last-resort offline fallback |

**Tier-0 decision, 2026-05-05:** preview access is **not currently available** on `chapmanvoice`. The smoke test reaches Vertex AI, receives `404 NOT_FOUND` for `gemini-3.1-pro-preview` and `gemini-3.1-pro-preview-customtools`, then succeeds with HTTP 200 on `gemini-2.5-pro` and `gemini-2.5-flash`. Tier 1 is therefore the accepted repo-review primary for this implementation phase. Tier 0 stays configured so the system upgrades automatically after preview access is granted.

**Per-task primary tier (do not start at tier 0 for cheap work):**

| Task | Primary | thinking policy |
|---|---|---|
| Repo error review | tier 0, demotes to accepted tier 1 today | high |
| Java level inference | tier 0, demotes to accepted tier 1 today | medium |
| Question ladder generation | **tier 2** | low |
| MCQ grading | none (deterministic compare) | n/a |
| Predict-output grading | none (deterministic compare) | n/a |
| Short-code grading | tier 1 | medium |
| Agentic short-code runner | tier 0t | high |

**Retry policy:**

```python
RETRY_ON  = {429, 500, 503}                 # transient -> retry once at same tier
DEMOTE_ON = {404, "PERMISSION_DENIED",      # permanent -> next tier
             "NOT_FOUND", "INVALID_ARGUMENT"}
HARD_FAIL = {401, 403}                      # SA misconfig -> bubble up, don't mask
```

- Backoff: `min(2^attempt, 8)` seconds.
- Dead-tier cache: when a tier returns `NOT_FOUND` (preview not enabled, etc.), mark it dead for 600s in-process so we skip it immediately.
- Schema validation failure: one repair pass at the same tier (`"Previous output failed schema. Errors: {...}. Return JSON only."`); if still bad, demote.

**Provider implementation (Gemini, google-genai SDK):**

```python
# llm/gemini_provider.py
from google import genai
from google.genai import types
import os, json, asyncio
from pydantic import BaseModel

class GeminiProvider:
    def __init__(self, model_id: str):
        self.model_id = model_id
        self.client = genai.Client(
            vertexai=True,
            project=os.environ["GCP_PROJECT"],     # chapmanvoice
            location=os.environ["GCP_LOCATION"],   # us-central1
        )

    def _thinking_config(self, thinking: str):
        fields = types.ThinkingConfig.model_fields
        if "thinking_level" in fields:
            return types.ThinkingConfig(thinking_level=thinking)
        if "thinking_budget" in fields:
            budget = {"minimal": 0, "low": 1024, "medium": 4096, "high": 8192}[thinking]
            return types.ThinkingConfig(thinking_budget=budget)
        return None

    async def generate_json(self, *, prompt: str, schema: type[BaseModel],
                            thinking: str = "medium",
                            cached_content: str | None = None,
                            tools: list | None = None) -> dict:
        thinking_config = self._thinking_config(thinking)
        cfg = types.GenerateContentConfig(
            thinking_config=thinking_config,
            response_mime_type="application/json",
            response_schema=schema.model_json_schema(),
            temperature=0.4,
            cached_content=cached_content,
            tools=tools,
        )
        resp = await self.client.aio.models.generate_content(
            model=self.model_id, contents=prompt, config=cfg,
        )
        return json.loads(resp.text)
```

**Context caching for repo review:**

- For each repo, build a single `repo_bundle` (metadata + truncated tree + selected source files).
- If `len(bundle) >= MIN_CACHE_BYTES` (start at 32 KB, tune in dev), create a Vertex cache with TTL 900s.
- Issue 2-3 calls against the same `cached_content` (review, java_signals, question seeds) — major cost saving.
- For tiny repos, fall back to inline content.

**Authentication:**

- Service account JSON at `services/knowledge-analysis/secrets/gcp-sa.json`.
- `secrets/` added to `services/knowledge-analysis/.dockerignore` and `R26-SE-030/.gitignore`.
- Container env: `GOOGLE_APPLICATION_CREDENTIALS=/run/secrets/gcp-sa.json`, mounted read-only.
- SA must have `roles/aiplatform.user` on project `chapmanvoice`.

### 4.3 Repo review pipeline

**Endpoints (new file `app/api/github_review_routes.py`):**

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/github-review/select-repos` | Returns the 5 chosen repos for a student (deterministic by seed). |
| POST | `/api/v1/github-review/review-top-5` | Kicks off the review job; returns a `job_id`. Streams results via Server-Sent Events. |
| GET | `/api/v1/github-review/status/{job_id}` | Polls progress (used as SSE fallback). |
| POST | `/api/v1/github-review/re-review` | Re-runs review for a single repo; used by "I fixed this" button. |

**Selection algorithm (stratified random, public + private):**

```python
async def pick_5(gh_token: str, student_id: str) -> list[Repo]:
    repos = await gh.list_user_repos(per_page=100, visibility="all",
                                     affiliation="owner,collaborator")
    repos = [r for r in repos
             if not r["fork"] and not r["archived"] and r["size"] > 0]
    if not repos:
        return []
    by_lang = group_by(repos, key=lambda r: r["language"] or "Other")
    seed   = int(hmac_sha256(student_id, b"review-v1"), 16)
    rng    = random.Random(seed)
    pick   = []
    java   = by_lang.pop("Java", [])
    others = [r for bucket in by_lang.values() for r in bucket]
    pick  += rng.sample(java,   k=min(3, len(java)))
    pick  += rng.sample(others, k=min(5 - len(pick), len(others)))
    rng.shuffle(pick)
    return pick[:5]
```

`seed` is HMAC of `(student_id, "review-v1")` so re-runs return the same five repos until the version is bumped. This makes "I fixed this" -> re-review traceable.

**Per-repo bundle construction:**

- Repo metadata: name, description, language stats, topics, last 10 commits (message + sha + ts).
- File tree truncated to top-level + first-level subdirs only.
- Source files: at most 12 files, capped at 6000 bytes each, prioritizing `.java`, then `.py`, `.js`, `.ts`. Skip `node_modules/`, `target/`, `build/`, `dist/`, `.git/`, lockfiles, binaries.
- Total bundle target: ~64 KB; hard cap 256 KB.

**Review prompt (zero-shot, JSON-schema constrained):**

```
SYSTEM: You are a strict Java/SE code reviewer for university students.
You will receive one repository's metadata and a sample of its source.
Output ONLY a JSON object validating the schema. No prose. No markdown fences.

SCHEMA: <auto-generated from RepoReview Pydantic model>

USER: <repo bundle>
```

**RepoReview Pydantic model:**

```python
class RepoError(BaseModel):
    severity: Literal["low", "medium", "high"]
    file: str
    line: int | None = None
    why: str = Field(..., max_length=240)
    fix_hint: str = Field(..., max_length=240)

class RepoReview(BaseModel):
    repo: str
    summary: str = Field(..., max_length=500)
    java_signals: dict   # {level: beginner|intermediate|advanced, evidence: str}
    errors: list[RepoError]
    suggestions: list[str]
```

**Concurrency model:**

- `asyncio.gather` over 5 repos with `Semaphore(3)` to avoid GitHub secondary rate limits.
- Each repo: 60s timeout. On timeout return `status:"partial"` and stream what we have.
- Per-repo SHA cache in Mongo with TTL 24h to avoid re-bundling unchanged repos.

### 4.4 Sandbox service (new microservice `services/code-sandbox/`)

**Responsibility:** spin up disposable Docker containers, stream a Java REPL over WebSocket, run hidden tests, grade with Gemini.

**Dockerfile.orchestrator (FastAPI, talks to host Docker daemon):**

```Dockerfile
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends docker-cli \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Dockerfile.runner (the throwaway image; built once, reused):**

```Dockerfile
FROM eclipse-temurin:21-jdk-jammy
RUN useradd -m -u 1000 runner
WORKDIR /work
USER runner
# tiny supervisor that reads code from stdin, compiles, runs, streams output
COPY --chown=runner:runner runner_supervisor.py /usr/local/bin/runsv
CMD ["python3", "/usr/local/bin/runsv"]
```

Build target: `mentora/java-runner:21`. Pre-built once; never built per session.

**Per-session container constraints (enforced by orchestrator at `docker create`):**

| Setting | Value |
|---|---|
| `image` | `mentora/java-runner:21` |
| `network` | `none` |
| `read_only` | true |
| `tmpfs` | `/work:rw,size=64m`, `/tmp:rw,size=32m` |
| `cpus` | `0.5` |
| `memory` | `384m` |
| `pids-limit` | `128` |
| `ulimits` | `nproc=64`, `fsize=10MB` |
| `cap_drop` | `ALL` |
| `security_opt` | `no-new-privileges` |
| `user` | `1000:1000` |
| auto-remove | true |
| wall-clock per run | `180s` |

The runner image is **never** started with the host Docker socket mounted. Only the orchestrator can talk to Docker.

**Endpoints:**

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/sessions` | `{student_id, java_level, signals?}` -> `{session_id, ws_url, ladder}` |
| WS | `/api/v1/sessions/{id}/io` | bidi: `{type, payload}` for code, run, stdout, stderr, telemetry |
| POST | `/api/v1/sessions/{id}/answer` | `{qid, answer}` -> graded result |
| POST | `/api/v1/sessions/{id}/run` | `{code, stdin?}` -> `{compile_ok, stdout, stderr, runtime_ms}` |
| DELETE | `/api/v1/sessions/{id}` | tears down container |

**Lazy container start:** A container is only created when the student opens a `short_code` question. MCQ and predict-output questions never touch Docker.

### 4.5 Question taxonomy

**Ladder shape (fixed):**

| # | Type | Difficulty | Eval path |
|---|---|---|---|
| 1 | `mcq` | easy | deterministic compare |
| 2 | `predict_output` | easy | deterministic compare |
| 3 | `mcq` | medium | deterministic compare |
| 4 | `short_code` | medium | Docker run + hidden tests + Gemini rubric |
| 5 | `short_code` | hard | Docker run + hidden tests + Gemini rubric |

**Pydantic model:**

```python
class TestCase(BaseModel):
    stdin: str = ""
    expected_stdout: str

class Question(BaseModel):
    qid: str
    type: Literal["mcq", "predict_output", "short_code"]
    difficulty: Literal["easy", "medium", "hard"]
    prompt: str
    # mcq:
    options: list[str] | None = None
    correct_index: int | None = None         # NEVER serialized to client
    # predict_output:
    starter_code: str | None = None
    expected_stdout: str | None = None       # NEVER serialized to client
    # short_code:
    starter_template: str | None = None
    hidden_tests: list[TestCase] | None = None  # NEVER serialized to client
    rubric: str | None = None

class QuestionLadder(BaseModel):
    ladder: list[Question]                   # exactly 5
```

A `to_client_view()` helper strips every field marked NEVER-serialized before sending to the frontend.

**Generator prompt (zero-shot):**

```
SYSTEM: You generate a 5-question Java assessment ladder for an
undergraduate student. Strict JSON. No prose.

CONTEXT:
  java_level: <beginner|intermediate|advanced>
  signals_evidence: <one paragraph from repo review>
  topics_seen_in_repos: <list>

CONSTRAINTS:
  - Exactly 5 questions in this fixed order:
      1. mcq-easy
      2. predict_output-easy
      3. mcq-medium
      4. short_code-medium
      5. short_code-hard
  - short_code answers writable in <= 25 lines.
  - hidden_tests must compile; expected_stdout produced by an
    internally-verified reference solution.
  - Topics drawn from topics_seen_in_repos when possible.

SCHEMA: <auto from QuestionLadder>
```

Generated at tier 2 (`gemini-2.5-flash`, thinking=low) for speed and cost.

### 4.6 Anti-paste integrity

**Client side (Monaco):**

```ts
editor.onKeyDown(e => {
  const k = e.code.toLowerCase();
  if ((e.ctrlKey || e.metaKey) && (k.endsWith('keyv') || k.endsWith('keyc') || k.endsWith('keyx'))) {
    e.preventDefault(); e.stopPropagation();
  }
});
const dom = editor.getDomNode();
dom.addEventListener('paste',       e => e.preventDefault(), true);
dom.addEventListener('drop',        e => e.preventDefault(), true);
dom.addEventListener('dragover',    e => e.preventDefault(), true);
dom.addEventListener('contextmenu', e => e.preventDefault(), true);
```

**Server-side keystroke telemetry (the actual defense):**

- Frontend emits `{type:"keystroke", t: epoch_ms, n: 1}` per key.
- Server keeps a sliding window per session and computes:
  - mean inter-keystroke interval
  - variance
  - bursts > 30 chars in < 100ms (paste signature)
- If burst count > 0 in any 5-second window: `integrity_flag = "suspicious"`.
- The existing `sandbox/page.tsx` integrity widget consumes this real number (the mock value goes away).

**Honest disclosure (in README and onboarding tooltip):** client-side paste blocks are bypassable via devtools or headless browsers; the keystroke-cadence model is the actual signal.

---

## 5. Data models (Mongo)

### 5.1 New collections

**`GithubCredential`**

```js
{
  _id: ObjectId,
  student_id: ObjectId,        // ref Student
  gh_user_id: Number,
  gh_login: String,
  scopes: [String],
  ciphertext: Buffer,          // AES-256-GCM(token)
  iv: Buffer,                  // 12 bytes
  tag: Buffer,                 // 16 bytes
  linked_at: Date,
  last_used_at: Date,
}
```

**`RepoReviewJob`**

```js
{
  _id: ObjectId,
  student_id: ObjectId,
  status: "queued"|"running"|"done"|"partial"|"failed",
  seed_version: "review-v1",
  repos: [{
    full_name, status, started_at, finished_at,
    cache_id, sha, error_count, review: <RepoReview JSON>
  }],
  java_level_inferred: String,
  signals_evidence: String,
  created_at, updated_at,
}
```

**`SandboxSession`**

```js
{
  _id: ObjectId,
  student_id: ObjectId,
  ladder: [<Question>],
  answers: [{ qid, submitted_at, ok, score, integrity_flag, runtime_ms? }],
  container_id: String | null,
  started_at, ended_at,
  integrity: { mean_iki_ms, variance, paste_bursts },
}
```

### 5.2 Modifications to existing models

**`Student.js`** — add:

```js
github: {
  linked: { type: Boolean, default: false },
  gh_login: String,
  linked_at: Date,
  credential_ref: { type: ObjectId, ref: 'GithubCredential' },
}
```

No existing fields touched. Migration script: backfill `github.linked = false` on all existing students.

---

## 6. API surface (full enumeration)

### user-service (port 3001)

| Existing | New |
|---|---|
| `POST /api/auth/register` | `GET  /api/github/oauth/start` |
| `POST /api/auth/login` | `GET  /api/github/oauth/callback` |
| `POST /api/auth/refresh` | `GET  /api/github/status` |
| `POST /api/auth/logout` | `POST /api/github/unlink` |
| `GET  /api/students/me` | `GET  /api/internal/github/credential/:student_id` (internal-key gated; serves decrypted token to knowledge-analysis and code-sandbox) |

### knowledge-analysis (port 5007)

| Existing | New |
|---|---|
| `POST /api/v1/github-fetch-analyze/fetch-and-analyze` | `POST /api/v1/github-review/select-repos` |
| `POST /api/v1/github-fetch-analyze/fetch-only` | `POST /api/v1/github-review/review-top-5` |
| `GET  /api/v1/github-fetch-analyze/check-github-auth` | `GET  /api/v1/github-review/status/{job_id}` |
| | `POST /api/v1/github-review/re-review` |

### code-sandbox (port 5008, new)

| Method | Path |
|---|---|
| POST | `/api/v1/sessions` |
| WS | `/api/v1/sessions/{id}/io` |
| POST | `/api/v1/sessions/{id}/answer` |
| POST | `/api/v1/sessions/{id}/run` |
| DELETE | `/api/v1/sessions/{id}` |

---

## 7. Configuration

### 7.1 user-service `.env` additions

```
GH_CLIENT_ID=Iv1.xxxxxxxxxxxxxxxx
GH_CLIENT_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
GH_OAUTH_SCOPE=repo
GH_OAUTH_CALLBACK_URL=http://localhost:3001/api/github/oauth/callback
GH_TOKEN_KEK_HEX=<HKDF(JWT_REFRESH_SECRET, "gh-kek", 32)>
INTERNAL_SERVICE_KEY=<existing>
```

### 7.2 knowledge-analysis `.env` additions

```
LLM_PROVIDER=gemini
GCP_PROJECT=chapmanvoice
GCP_LOCATION=us-central1
GEMINI_MODEL_PRIMARY=gemini-3.1-pro-preview
GEMINI_MODEL_TOOLS=gemini-3.1-pro-preview-customtools
GEMINI_MODEL_GA=gemini-2.5-pro
GEMINI_MODEL_FAST=gemini-2.5-flash
GOOGLE_APPLICATION_CREDENTIALS=/run/secrets/gcp-sa.json
USER_SERVICE_INTERNAL_URL=http://user-service:3001
INTERNAL_SERVICE_KEY=<same as user-service>
OLLAMA_URL=http://host.docker.internal:11434     # offline fallback
OLLAMA_MODEL=llama3
```

### 7.3 code-sandbox `.env`

```
GCP_PROJECT=chapmanvoice
GCP_LOCATION=us-central1
GEMINI_MODEL_GA=gemini-2.5-pro
GEMINI_MODEL_TOOLS=gemini-3.1-pro-preview-customtools
GOOGLE_APPLICATION_CREDENTIALS=/run/secrets/gcp-sa.json
DOCKER_HOST=unix:///var/run/docker.sock
JAVA_RUNNER_IMAGE=mentora/java-runner:21
SESSION_TTL_SECONDS=1800
USER_SERVICE_INTERNAL_URL=http://user-service:3001
INTERNAL_SERVICE_KEY=<same>
```

### 7.4 docker-compose.yml additions

```yaml
knowledge-analysis:
  environment:
    LLM_PROVIDER: gemini
    GCP_PROJECT: chapmanvoice
    GCP_LOCATION: us-central1
    GEMINI_MODEL_PRIMARY: gemini-3.1-pro-preview
    GEMINI_MODEL_TOOLS: gemini-3.1-pro-preview-customtools
    GEMINI_MODEL_GA: gemini-2.5-pro
    GEMINI_MODEL_FAST: gemini-2.5-flash
    GOOGLE_APPLICATION_CREDENTIALS: /run/secrets/gcp-sa.json
    USER_SERVICE_INTERNAL_URL: http://user-service:3001
    INTERNAL_SERVICE_KEY: change-this-internal-service-key
  volumes:
    - ./R26-SE-030/services/knowledge-analysis/secrets/gcp-sa.json:/run/secrets/gcp-sa.json:ro

code-sandbox:
  build:
    context: ./R26-SE-030/services/code-sandbox
  container_name: mentora-code-sandbox
  environment:
    GCP_PROJECT: chapmanvoice
    GCP_LOCATION: us-central1
    GOOGLE_APPLICATION_CREDENTIALS: /run/secrets/gcp-sa.json
    DOCKER_HOST: unix:///var/run/docker.sock
    JAVA_RUNNER_IMAGE: mentora/java-runner:21
    USER_SERVICE_INTERNAL_URL: http://user-service:3001
    INTERNAL_SERVICE_KEY: change-this-internal-service-key
  ports:
    - "5008:8000"
  volumes:
    - ./R26-SE-030/services/code-sandbox/secrets/gcp-sa.json:/run/secrets/gcp-sa.json:ro
    - /var/run/docker.sock:/var/run/docker.sock
  depends_on:
    - user-service
```

### 7.5 .gitignore (project root and service-level)

```
secrets/
*.gcp-sa.json
.env
.env.local
```

---

## 8. Frontend changes (minimal, design-preserving)

| File | Type | Purpose |
|---|---|---|
| `src/app/(dashboard)/layout.tsx` | edit | Mounts onboarding overlay if `!user.github.linked` |
| `src/components/onboarding/GithubLinkCard.tsx` | new | Reuses `AuthCard`/`AuthButton` palette |
| `src/lib/api/github.ts` | new | `oauthStart()`, `status()`, `unlink()` wrappers |
| `src/lib/api/review.ts` | new | `selectRepos()`, `reviewTop5()`, `status()`, SSE consumer |
| `src/lib/api/sandbox.ts` | new | session lifecycle + WS wrapper |
| `src/app/(dashboard)/knowledge-assist/forensics/page.tsx` | edit | Render real review cards from SSE |
| `src/app/(dashboard)/knowledge-assist/sandbox-live/page.tsx` | new | Three render modes (mcq/predict/short_code) |

**No changes** to: `src/app/(auth)/*`, `src/components/auth/*`, `src/components/ui/*`, `globals.css`, color tokens, any existing dashboard page's visual structure.

---

## 9. Build order (5 working days, single implementer)

| Day | Step | Deliverable |
|---|---|---|
| 1 AM | Provider abstraction + Gemini smoke test | `llm/router.py` probes preview tiers, marks unavailable preview models dead for 600s, and returns valid JSON through the accepted tier-1 primary |
| 1 PM | OAuth App registration + user-service routes | `/api/github/oauth/start` -> consent -> `/callback` stores encrypted token |
| 2 AM | Onboarding card on frontend | popup flow works end-to-end, dashboard ungates after link |
| 2 PM | Stratified random `select-repos` + bundle builder | Returns deterministic 5-repo list with bundles |
| 3 | `review-top-5` + SSE + forensics page | Streamed cards rendered with real Gemini output |
| 4 AM | code-sandbox orchestrator + runner image + WS | `/sessions` -> WS -> compile/run roundtrip works |
| 4 PM | Question ladder generator (tier 2) | 5-question JSON, validated, served stripped |
| 5 AM | sandbox-live page (three render modes) | MCQ + predict + short_code all rendering correctly |
| 5 PM | Anti-paste + keystroke telemetry + customtools grader | Integrity widget shows real numbers; short-code grading produces score |

Each step lands behind a feature flag (`FEATURE_GITHUB_REVIEW`, `FEATURE_SANDBOX_LIVE`) so partial work never breaks the dev loop.

---

## 10. Risks and mitigations

| # | Risk | Mitigation |
|---|---|---|
| 1 | `gemini-3.1-pro-preview` access not granted on `chapmanvoice` | **Accepted for current phase.** Tier 1 (`gemini-2.5-pro`) is the repo-review primary until preview access is granted. Boot probe verified `NOT_FOUND` for tier 0/0t and HTTP 200 for tier 1/2 on 2026-05-05. |
| 2 | Vertex preview quota lower than expected | Fallback chain handles it; per-task primary tier already avoids preview where unnecessary. |
| 3 | GitHub secondary rate limits when fetching 5 repos in parallel | `Semaphore(3)`, per-SHA Mongo cache (24h TTL), exponential backoff. |
| 4 | Apple Silicon issues with Alpine JDK | Use `eclipse-temurin:21-jdk-jammy` (glibc) instead of Alpine. Verified ARM-friendly. |
| 5 | Schema drift between Pydantic models and prompt schema | Always derive prompt schema from `Model.model_json_schema()` — never hand-write twice. |
| 6 | Thinking traces leaked to frontend | Server logs `response.candidates[0].thought` only; client gets `response.text` (already JSON). |
| 7 | Service account JSON committed to git | `secrets/` in `.gitignore` and `.dockerignore`; CI step rejects pushes containing Google service-account private-key JSON markers. |
| 8 | Docker socket exposed = root on host | Only orchestrator gets the socket. Runner image runs as `uid 1000`, `cap_drop ALL`, `network none`, read-only fs. |
| 9 | Empty-repo student | Handle explicitly: mark `java_level` from profile, generate questions from level only, skip review. |
| 10 | Keystroke cadence false positives on slow connections | Window over 5 seconds, not 1; require >=3 burst events before flagging. |

---

## 11. Open items (need answers before step 1)

1. **OAuth App registration** — registered, `GH_CLIENT_ID` + `GH_CLIENT_SECRET` placed in user-service `.env`.
2. **`secrets/gcp-sa.json`** — placed at `services/knowledge-analysis/secrets/gcp-sa.json` and confirmed not tracked by git.
3. **SA roles on `chapmanvoice`** — confirm `roles/aiplatform.user` granted.
4. **APIs enabled** — `aiplatform.googleapis.com` and `generativelanguage.googleapis.com` enabled on `chapmanvoice`.
5. **Vertex preview access** — not granted on `chapmanvoice` as of 2026-05-05. Accepted decision: continue with tier 1 (`gemini-2.5-pro`) as primary; request preview access later only if cost/quality testing shows it is worth the change.

When all five are green, step 1 starts.

---

## 12. Non-goals (explicit)

- We are not migrating off Mongo.
- We are not introducing n8n.
- We are not redesigning auth pages, dashboard layout, or color tokens.
- We are not building an instructor-side review UI in this phase.
- We are not supporting GitHub Enterprise instances (cloud only).
- We are not multi-tenanting the sandbox (one container per session).

---

## 13. Glossary

| Term | Meaning |
|---|---|
| Tier 0 / 1 / 2 / 3 | Position in the LLM fallback chain (preview / GA-pro / GA-flash / Ollama) |
| Bundle | Per-repo input pack sent to Gemini: metadata + tree + truncated source |
| Ladder | The fixed 5-question sequence served by sandbox-live |
| Integrity flag | Server-side judgement on whether keystroke cadence is human |
| Method 1 | OAuth Authorization Code Flow (popup -> consent -> callback) |
| Customtools model | `gemini-3.1-pro-preview-customtools`, tuned for tool-calling workflows |
