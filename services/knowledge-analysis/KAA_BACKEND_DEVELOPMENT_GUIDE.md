# KAA Backend Development Guide

This guide shows how to implement your **Knowledge Analysis Agent (KAA)** backend cleanly using the structure you already created.

## 1) Target Architecture

Use your folders as follows:

- `app/main.py` -> FastAPI app setup and router registration
- `app/api/routes.py` -> `/analyze`, `/quiz/generate`, `/health`, `/demo`
- `app/models/schemas.py` -> all Pydantic request/response models
- `app/core/constants.py` -> `JAVA_TOPICS`, default `WEIGHTS`, static configs
- `app/core/config.py` -> env and app settings
- `app/services/pipeline.py` -> orchestrates step 1 to step 10
- `app/services/steps/*.py` -> one function per pipeline step
- `app/services/quiz_engine.py` -> adaptive quiz generator logic
- `app/utils/helpers.py`, `app/utils/validators.py` -> shared utility and validation logic
- `app/db/database.py`, `app/db/models.py` -> DB connection and persistence models
- `tests/test_pipeline.py` -> unit tests for pipeline behavior

## 2) Setup Project Environment

From `services/knowledge-analysis`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install fastapi uvicorn pydantic python-dotenv pytest httpx
pip freeze > requirements.txt
```

## 3) Add Base Dependencies

At minimum keep:

- `fastapi`
- `uvicorn[standard]`
- `pydantic`
- `python-dotenv`
- `pytest`
- `httpx`

If adding DB later:

- `sqlalchemy` + `psycopg2-binary` (PostgreSQL) or
- `motor` / `pymongo` (MongoDB)

## 4) Implement Config and Constants First

### `app/core/constants.py`

Define:

- `JAVA_TOPICS` list
- `WEIGHTS = {"sandbox": 0.40, "forensic": 0.30, "quiz": 0.30}`

### `app/core/config.py`

Create settings class for:

- `APP_NAME`
- `APP_VERSION`
- `CORS_ORIGINS`
- optional DB URL

Load from `.env` (using `python-dotenv` or Pydantic settings).

## 5) Build Data Schemas

In `app/models/schemas.py`, move all models from your script:

- `QuizPerformance`
- `SandboxSession`
- `GitHubCommit`
- `LearnerInput`

Add response models for better API contracts:

- `AnalyzeResponse`
- `QuizGenerateResponse`
- `HealthResponse`

## 6) Split the 10 Steps into Step Modules

Move each function into its own file:

- `step1_ingest.py` -> `step1_ingest(data: LearnerInput) -> dict`
- `step2_preprocess.py` -> `step2_preprocess(data: LearnerInput) -> dict`
- ...
- `step10_output.py` -> `step10_output(profile: dict, validation: dict) -> dict`

Rules:

- Keep each step pure (no FastAPI imports)
- Keep function names consistent
- Accept typed input where possible
- Return predictable dictionary keys

## 7) Create Pipeline Orchestrator

In `app/services/pipeline.py`:

- import all step functions
- implement `run_full_pipeline(data: LearnerInput) -> dict`
- run steps in order
- return both `pipeline` details and `final_output`

This file should contain no endpoint decorators; only orchestration logic.

## 8) Create Quiz Engine Service

In `app/services/quiz_engine.py`:

- move quiz bank and adaptive difficulty logic
- expose `generate_quiz(topic: str, mastery_score: float = 0.5) -> dict`
- keep deterministic structure in response

Optional improvement:

- validate topic against `JAVA_TOPICS`
- fallback to a default bank if topic unknown

## 9) Build API Routes Layer

In `app/api/routes.py`:

- create `APIRouter()`
- define:
  - `POST /analyze`
  - `POST /quiz/generate`
  - `GET /health`
  - `GET /demo`
- call service layer (`pipeline.py`, `quiz_engine.py`), not step files directly

This keeps API thin and business logic centralized.

## 10) Wire FastAPI App Entry Point

In `app/main.py`:

- initialize `FastAPI(title=..., version=...)`
- add `CORSMiddleware`
- include router from `app/api/routes.py`
- add root endpoint if needed (`GET /`)

Run app:

```bash
uvicorn app.main:app --reload --port 8000
```

## 11) Add Input Validation and Error Handling

In `app/utils/validators.py`:

- topic validity checks
- numerical range checks (e.g., `0 <= burst_score <= 1`)
- safe fallback helpers

In routes:

- raise `HTTPException(400)` for bad input
- return structured errors

## 12) Add Tests Early

In `tests/test_pipeline.py`:

- test valid payload goes through all 10 steps
- test reduced mode (no GitHub commits)
- test scoring shape (`mastery_score`, `priority_rank`)
- test output contains `pipeline_steps_completed == 10`

Add API tests later using `TestClient`.

Run:

```bash
pytest -q
```

## 13) Suggested Implementation Order (Fastest Path)

1. `schemas.py`
2. `constants.py` + `config.py`
3. steps `1-4`
4. steps `5-7`
5. steps `8-10`
6. `pipeline.py`
7. `quiz_engine.py`
8. `routes.py`
9. `main.py`
10. tests + cleanup

## 14) Quality Checklist Before Completion

- All routes return JSON with stable keys
- Full mode and reduced mode both work
- No step crashes with missing optional GitHub data
- `priority_rank` assigned for all topics
- Warning and confidence logic in validation is tested
- Lint/test pass

## 15) Production Hardening (Next Step)

After MVP works, add:

- persistent storage for outputs
- auth for endpoints
- request logging and tracing
- stricter schema responses
- Docker healthcheck and CI pipeline

## 16) Minimal `.env` Template

```env
APP_NAME=KAA - Knowledge Analysis Agent
APP_VERSION=1.0.0
ENV=dev
PORT=8000
```

## 17) Optional Refactor Tip

Your original single-file code is a great prototype. For maintainability:

- keep math and decision logic in step files
- keep endpoint functions very small
- avoid duplicated constants across files

---

If you want, next I can generate the actual starter code in each file (`main.py`, `routes.py`, `schemas.py`, `pipeline.py`, and all 10 step files) so your service runs immediately.
