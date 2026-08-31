# mentora-backend

Agentic AI-Driven Multi-Agent Tutoring System for Personalized Learning and Mastery Assessment (R26-SE-030).

Microservices backend for the **Mentora** adaptive Java-learning platform: six independently containerised services orchestrated via Docker Compose, with real-time GitHub forensics, an adaptive quiz engine, concept-graph-driven mastery profiling, and a sandboxed Java code-execution engine.

- **Architecture:** [`ARCHITECTURE.md`](ARCHITECTURE.md) (KAA deep-dive) · [`docs/DEPLOYMENT_REPORT.md`](docs/DEPLOYMENT_REPORT.md) (full deployment report)
- **Frontend:** deployed separately in `mentora-frontend`

---

## Services

| # | Service | Language / Framework | Internal Port | Health | Purpose |
|---|---------|----------------------|:---:|:---:|---------|
| 1 | **user-service** | Node.js · Express | 3001 | `GET /health` | Auth (JWT), student accounts, GitHub OAuth, profiles |
| 2 | **lmg-service** (learning-generator) | Node.js · Express | 3002 | `GET /health` | Learning material generation, n8n job queueing, structured materials (lessons/quiz/flashcards) |
| 3 | **assessment-agent (AME)** | Node.js · Express | 5002 | `GET /health` | Assessment & Mastery Evaluation, RAG concept coverage, n8n triggers |
| 4 | **peer-learning** | Python · FastAPI | 8000 | — | Collaborative peer-learning features |
| 5 | **knowledge-analysis (KAA)** | Python · FastAPI | 8000 → host **5007** | `GET /health` | GitHub repo analysis, **adaptive quiz engine**, mastery profiling, concept-graph diagnostics, Gemini + Ollama LLM routing |
| 6 | **ai-engine** | Python · FastAPI | 5010 | `GET /health` | Sandboxed Java compile/run for the Code Sandbox |

### Inter-service dependencies

```
lmg-service         ──► user-service
assessment-agent    ──► user-service
knowledge-analysis  ──► user-service, ai-engine
```

All Python services authenticate internal calls via a shared `INTERNAL_SERVICE_KEY`; user-service is the central identity provider.

---

## Repository layout

```
mentora-backend/
├── services/
│   ├── user service/            # user-service (Node.js)
│   ├── learning-generator/      # lmg-service + ai-engine source (Node.js)
│   ├── assessment-agent/        # assessment-agent (Node.js)
│   ├── peer-learning/           # peer-learning (Python)
│   └── knowledge-analysis/      # KAA (Python) — quiz engine, concept graph, mastery profile
├── ai-engine/learning-generator/ # ai-engine (Python) — sandboxed Java runner
├── shared/                      # shared config/docs across services
├── scripts/                     # helper scripts
├── test/                        # central CI test suites (unit/integration/performance)
├── docs/                        # deployment report (MD + interactive HTML)
├── .github/workflows/ci.yml     # CI/CD pipeline
├── docker-compose.yml           # local dev (builds from source)
└── docker-compose.prod.yml      # production (pulls pre-built images from GHCR)
```

---

## Quick start (local development)

External dependencies (MongoDB, Ollama, n8n) run on the host:

```bash
mongod --dbpath ./data/db &
ollama serve &
docker run -d -p 5678:5678 n8nio/n8n &

cd mentora-backend
docker compose up --build -d

curl http://localhost:3001/health   # user-service
curl http://localhost:5012/health   # lmg-service
curl http://localhost:5007/health   # knowledge-analysis
curl http://localhost:5010/health   # ai-engine
```

The frontend runs separately on :3000 (see `mentora-frontend`).

---

## Knowledge Analysis Agent (KAA) highlights

The KAA is the diagnostic engine: it synthesises **adaptive quiz performance**, **sandbox telemetry**, and **longitudinal GitHub commit forensics** into a unified **Mastery Profile** (`CanonicalMasteryOutput`, schema `kaa-lmg-v1.0`) that distinguishes genuine programming knowledge from AI-assisted dependency. Full contract and pipeline detail live in [`ARCHITECTURE.md`](ARCHITECTURE.md).

Key modules under `services/knowledge-analysis/app/`:

- `api/routes.py` — `/analyze/auto`, `/quiz/*`, `/health`, `/demo`; `POST /api/v1/quiz/sets` listing + read-only set views
- `api/quiz_routes.py` — adaptive quiz + **34-topic assessment generation** (`GET/POST /api/v1/quiz/...`, `GET /sets`, `GET /sets/{id}`)
- `services/quiz_generator.py` — `build_assessment_pool` (LLM batches + seed fallback, difficulty mapped from concept-graph levels)
- `services/quiz_store.py` — session persistence, `list_sets`, read-only `get_set_view` (answer keys stripped)
- `services/concept_graph.py` — 33-node Java concept graph (`difficulty`, `week_area`, `concepts`)
- `services/pipeline.py` — 10-step diagnostic orchestrator
- `services/diagnostic_report.py` — rich forensic/telemetry/quiz companion report
- `services/profile_contract.py` — canonical mastery output contract

`sandbox/page.tsx` triggers `/analyze/auto` (always bridges to the mastery profile); the assessment lives on the assessment page with regenerate + persistent previous-set review.

---

## Testing

Central suites live in [`test/`](test/README.md) and are split into `unit/`, `integration/`, and `performance/` layers for each service. All are self-contained (no live DB, LLM, or network required).

```bash
# Node suites (run from test/)
cd mentora-backend/test
npm install
npm test                       # user-service · assessment-agent · learning-generator

# Python suites (run from repo root — one process per service)
python3 -m pytest test/knowledge-analysis -q
python3 -m pytest test/peer-learning       -q
python3 -m pytest test/ai-engine           -q
```

The KAA also ships its own standalone suite at `services/knowledge-analysis/tests/`.

---

## CI/CD

`.github/workflows/ci.yml` runs on push/PR to `main`:

```
test-node (Jest + node:test)  ─┐
                               ├─► changes (paths-filter) ─► build & push changed services to GHCR
test-python (pytest)          ─┘          (latest + <commit-sha> tags)
```

Images are published to GitHub Container Registry (`ghcr.io/<owner>/<repo>/<service>`).

---

## Production deployment

```bash
git clone https://github.com/<owner>/mentora-backend.git
cd mentora-backend
# configure each services/*/.env (see .env.example templates)
docker compose -f docker-compose.prod.yml up -d
```

See [`docs/DEPLOYMENT_REPORT.md`](docs/DEPLOYMENT_REPORT.md) for the full architecture, port map, infra sizing, cost comparison, and known limitations.

---

## Project

- **Course:** R26-SE-030 — Agentic AI-Driven Multi-Agent Tutoring System
- **Cluster:** COEAI (Centre of Excellence for AI), SLIIT
