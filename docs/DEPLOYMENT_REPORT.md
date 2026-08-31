# Mentora — Deployment Report

> **Version:** 1.0  
> **Date:** August 2026  
> **Repository:** `mentora-backend`  
> **Frontend:** `mentora-frontend` (deployed separately)

---

## 1. Executive Summary

Mentora is a microservices-based adaptive Java-learning platform comprising **six backend services**, a **Next.js frontend**, and three external dependencies (MongoDB, Ollama LLMs, n8n workflow engine). Every service is containerised with Docker, orchestrated via Docker Compose, and deployed through a GitHub Actions CI/CD pipeline that builds and pushes images to **GitHub Container Registry (GHCR)** on every merge to `main`.

The architecture is designed so that the application stack can be launched on a single host with a single command, while still being decomposed into independently testable, buildable, and deployable units.

---

## 2. System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Frontend (Next.js)                           │
│                      Deployed to: Vercel                               │
│                        https://mentora.kaweesha.com                    │
└───────────┬──────────┬──────────┬──────────┬──────────┬────────────────┘
            │          │          │          │          │
   ┌────────▼───┐ ┌────▼────┐ ┌──▼───┐ ┌────▼───┐ ┌───▼────┐ ┌──────────┐
   │    User    │ │   LMG   │ │ AME  │ │  Peer  │ │  KAA   │ │ AI Engine│
   │  Service   │ │ Service │ │Agent │ │Learning│ │  Agent │ │          │
   │  :3001     │ │ :5012   │ │:5002 │ │ :8000  │ │ :5007  │ │  :5010   │
   │  Node.js   │ │ Node.js │ │Node  │ │ Python │ │ Python │ │  Python  │
   └──────┬─────┘ └────┬────┘ └──┬───┘ └────┬───┘ └───┬────┘ └────┬─────┘
          │             │         │          │         │            │
          │             │         │          │    ┌────▼─────┐     │
          │             │         │          │    │  Google  │     │
          │             │         │          │    │ Gemini   │     │
          │             │         │          │    └──────────┘     │
          └─────────────┴─────────┴──────────┴────────────────────┘
                                    │
                    ┌───────────────┼───────────────┐
                    │               │               │
              ┌─────▼─────┐  ┌─────▼─────┐  ┌─────▼─────┐
              │  MongoDB  │  │  Ollama   │  │    n8n    │
              │ (Atlas /  │  │  (local)  │  │ (local)   │
              │  self-h)  │  │ :11434    │  │ :5678     │
              └───────────┘  └───────────┘  └───────────┘
```

---

## 3. Microservices Inventory

| # | Service | Language | Framework | Internal Port | Health Endpoint | Purpose |
|---|---------|----------|-----------|--------------|-----------------|---------|
| 1 | **user-service** | Node.js 20 | Express | 3001 | `GET /health` | Authentication (JWT), student accounts, GitHub OAuth, profile management |
| 2 | **lmg-service** | Node.js 20 | Express | 3002 | `GET /health` | Learning Material Generator — receives mastery profiles, queues generation jobs via n8n, stores structured materials (lessons, quizzes, flashcards) |
| 3 | **assessment-agent (AME)** | Node.js 20 | Express | 5002 | `GET /health` | Assessment & Mastery Evaluation — RAG-based concept coverage scoring, Ollama-powered embedding and inference, n8n workflow triggers |
| 4 | **peer-learning** | Python 3.11 | FastAPI / Uvicorn | 8000 | — | Peer learning service — collaborative learning features |
| 5 | **knowledge-analysis (KAA)** | Python 3.11 | FastAPI / Uvicorn | 8000 | `GET /health` | Knowledge Analysis Agent — GitHub repo analysis, adaptive quiz engine, mastery profiling, concept-graph-driven diagnostics, Gemini + Ollama LLM routing |
| 6 | **ai-engine** | Python 3.11 | FastAPI / Uvicorn | 5010 | `GET /health` | Java code execution engine — compiles/runs Java in a sandboxed environment, powers the Code Sandbox and practice challenges |

### Inter-Service Dependencies

```
lmg-service      ──depends-on──▶  user-service
assessment-agent ──depends-on──▶  user-service
knowledge-analysis ──depends-on──▶ user-service
knowledge-analysis ──depends-on──▶ ai-engine
```

All Python services authenticate internal calls via a shared `INTERNAL_SERVICE_KEY`. The user-service is the central identity provider; every other service validates JWTs through it.

---

## 4. Containerisation Strategy

All six services are packaged as Docker images using lightweight base images. No multi-stage builds are used (build dependencies are kept minimal enough to include in the final image).

| Service | Base Image | Build Tool | Image Size (approx.) |
|---------|-----------|------------|---------------------|
| user-service | `node:20-alpine` | `npm ci --omit=dev` | ~120 MB |
| lmg-service | `node:20-alpine` | `npm ci --only=production` | ~130 MB |
| assessment-agent | `node:20-alpine` | `npm ci --omit=dev` | ~120 MB |
| peer-learning | `python:3.11-slim` | `pip install` + build-essential | ~180 MB |
| knowledge-analysis | `python:3.11-slim` | `pip install` | ~160 MB |
| ai-engine | `python:3.11-slim` | `pip install` + `default-jdk-headless` | ~450 MB |

Each service includes a `.dockerignore` file to exclude test files, documentation, `.env` secrets, and IDE configuration from the build context.

### Dockerfile Patterns

**Node.js services** (user-service, lmg-service, assessment-agent):
```dockerfile
FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --omit=dev
COPY . .
EXPOSE <port>
CMD ["npm", "start"]
```

**Python services** (knowledge-analysis, peer-learning, ai-engine):
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE <port>
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "<port>"]
```

The ai-engine additionally installs `default-jdk-headless` to compile and execute Java code submitted via the Code Sandbox.

---

## 5. CI/CD Pipeline

**File:** `.github/workflows/ci.yml`  
**Trigger:** Push to `main`, pull requests to `main`, manual `workflow_dispatch`  
**Registry:** GitHub Container Registry (`ghcr.io`)

### Pipeline Stages

```
  ┌──────────────┐     ┌──────────────┐
  │  test-node   │     │  test-python  │     ← run in parallel
  │  (Jest)      │     │  (pytest)     │
  └──────┬───────┘     └──────┬───────┘
         │                    │
         └────────┬───────────┘
                  │
         ┌────────▼────────┐
         │  changes (diff) │     ← detect which services changed
         └────────┬────────┘
                  │
    ┌──────┬──────┼──────┬──────┬──────┐
    ▼      ▼      ▼      ▼      ▼      ▼
  user   lmg    ame    peer    kaa   ai-engine   ← build & push (changed only)
  svc    svc    agent   learn   agent  engine
```

### Stage Details

| Stage | Runner | What It Does |
|-------|--------|-------------|
| **test-node** | `ubuntu-latest` | Sets up Node 22 LTS, installs test deps from `test/package-lock.json`, runs Jest on user-service, assessment-agent; runs `node --test` on learning-generator |
| **test-python** | `ubuntu-latest` | Sets up Python 3.12, installs all three Python service requirements, runs `pytest` on knowledge-analysis, peer-learning, ai-engine |
| **changes** | `ubuntu-latest` | Uses `dorny/paths-filter@v3` to detect which service directories were modified |
| **build & push** (×6) | `ubuntu-latest` | Logs into GHCR via `GITHUB_TOKEN`, builds Docker image, pushes with `:latest` and `:<commit-sha>` tags. Only runs for changed services (or manual `workflow_dispatch`). Requires both test jobs + change detection to pass first |

### Image Tagging Strategy

Each image receives two tags on push:
- **`latest`** — always points to the most recent `main` build
- **`<commit-sha>`** — immutable, enables rollback to any specific commit

Images are named: `ghcr.io/<owner>/<repo>/<service>:<tag>`

---

## 6. Docker Compose Orchestration

Two compose files exist:

| File | Purpose | Image Source |
|------|---------|-------------|
| `docker-compose.yml` | Local development | Builds from source (`build: context: ./...`) |
| `docker-compose.prod.yml` | Production deployment | Pulls pre-built images from GHCR (`image: ghcr.io/...`) |

### Development (`docker-compose.yml`)

All six services are built from local source and run with hot-reload-compatible configurations. External dependencies (MongoDB, Ollama, n8n) are expected to be running on the host machine and are reached via `host.docker.internal:host-gateway`.

### Production (`docker-compose.prod.yml`)

Pre-built images are pulled from GHCR. Key differences from dev:

- **No build contexts** — images are fetched, not built
- **Port mapping** — `knowledge-analysis` maps to host port `8001` (dev uses `5007`)
- **CORS** — production CORS only allows the deployed frontend domain (`https://mentora.kaweesha.com`)
- **Dependency on `user-service`** — removed from `lmg-service` (handled by image layering)
- **`extra_hosts`** — removed from services that don't need direct host-network access

### Service Startup Order

```
user-service          (starts first, no dependencies)
    ├── ai-engine     (starts independently)
    │     └── knowledge-analysis (depends on user-service + ai-engine)
    ├── lmg-service   (depends on user-service)
    └── assessment-agent (depends on user-service)
peer-learning         (starts independently)
```

Docker Compose handles startup ordering via the `depends_on` directive. No health-check-based wait conditions are configured (services must be resilient to transient connection failures during startup).

---

## 7. Environment Configuration

### Secrets and Configuration Files

| Service | Env File | `.env.example` Provided |
|---------|----------|------------------------|
| user-service | `services/user service/.env` | Yes |
| lmg-service | `services/learning-generator/.env` | Yes |
| assessment-agent | `services/assessment-agent/.env` | Yes |
| knowledge-analysis | `services/knowledge-analysis/.env` | Yes |
| peer-learning | `services/peer-learning/.env` | No |
| ai-engine | *(inline in compose)* | N/A — uses `${OLLAMA_*}` env vars with defaults |

### Key Configuration Categories

| Category | Services Using | Variables |
|----------|---------------|-----------|
| **MongoDB connection** | user-service, lmg-service, assessment-agent, knowledge-analysis | `MONGODB_URI` / `MONGODB_URL`, `MONGODB_DB` |
| **JWT / Auth** | user-service, assessment-agent, knowledge-analysis | `JWT_SECRET`, `JWT_REFRESH_SECRET`, `INTERNAL_SERVICE_KEY` |
| **LLM (Ollama)** | lmg-service, assessment-agent, knowledge-analysis, ai-engine | `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `OLLAMA_CODE_MODEL` |
| **LLM (Google Gemini)** | knowledge-analysis | `GOOGLE_APPLICATION_CREDENTIALS`, `GEMINI_MODEL_*` |
| **n8n workflows** | lmg-service, assessment-agent | `N8N_BASE_URL`, `N8N_WEBHOOK_*` |
| **GitHub API** | user-service | `GH_CLIENT_ID`, `GH_CLIENT_SECRET` |
| **CORS** | user-service, lmg-service | `CORS_ORIGIN` |

### Secrets Management

- `.env` files are present in the repository (not `.gitignore`d) — suitable for development only
- `.env.example` files provide templated placeholders without real credentials
- **Production:** `.env` files must be placed on the target host and referenced by `docker-compose.prod.yml`
- The GCP service account key (`gcp-sa.json`) is mounted read-only into the KAA container via Docker volumes

---

## 8. External Dependencies

### 8.1 MongoDB

All stateful services depend on MongoDB for persistent storage.

| Concern | Collection(s) |
|---------|--------------|
| User accounts & auth | Managed by user-service |
| Learning materials | Managed by lmg-service |
| Mastery profiles, quiz sessions, sandbox attempts | Managed by knowledge-analysis |
| Code execution state | Managed by ai-engine |

**Deployment option:** MongoDB Atlas (free M0 tier for development, dedicated cluster for production) or self-hosted `mongo` container (not included in compose — must be provisioned separately).

### 8.2 Ollama (Local LLM Inference)

The LLM backbone for the system. Runs locally on the host machine and is accessed via `host.docker.internal:11434`.

| Model | Used By | Purpose |
|-------|---------|---------|
| `llama3:8b` | lmg-service, assessment-agent, knowledge-analysis | Natural language generation, mastery analysis, quiz question generation |
| `qwen2.5-coder:7b` | ai-engine | Code understanding, Java execution feedback |

**Deployment option:** Runs on the host machine (requires 8–16 GB RAM depending on model sizes). For cloud deployment, Ollama can run inside a Docker container with GPU access (`nvidia/cuda` runtime) or be replaced with a managed LLM API (e.g., Google Gemini, which KAA already supports as a fallback tier).

### 8.3 n8n (Workflow Automation)

The assessment-agent triggers n8n workflows for material generation pipelines.

| Setting | Value |
|---------|-------|
| URL | `http://n8n-container:5678` |
| Protocol | HTTP webhook triggers |

**Deployment option:** Run n8n as a Docker container (`docker run -d n8nio/n8n`) or deploy n8n Cloud. For production, n8n should be added to `docker-compose.yml` or deployed as a separate stack.

---

## 9. Port Mapping

### Development

| Service | Container Port | Host Port | URL |
|---------|---------------|-----------|-----|
| user-service | 3001 | **3001** | `http://localhost:3001` |
| lmg-service | 3002 | **5012** | `http://localhost:5012` |
| assessment-agent | 5002 | **5002** | `http://localhost:5002` |
| peer-learning | 8000 | **8000** | `http://localhost:8000` |
| knowledge-analysis | 8000 | **5007** | `http://localhost:5007` |
| ai-engine | 5010 | **5010** | `http://localhost:5010` |
| Frontend (Next.js) | 3000 | **3000** | `http://localhost:3000` |

### Production

| Service | Container Port | Host Port | External URL |
|---------|---------------|-----------|-------------|
| user-service | 3001 | 3001 | `https://mentora.kaweesha.com/api/auth/*` |
| lmg-service | 3002 | 5012 | `https://mentora.kaweesha.com/api/*` |
| assessment-agent | 5002 | 5002 | `https://mentora.kaweesha.com/api/*` |
| peer-learning | 8000 | 8000 | `https://mentora.kaweesha.com/api/*` |
| knowledge-analysis | 8000 | **8001** | `https://mentora.kaweesha.com/api/*` |
| ai-engine | 5010 | 5010 | Internal only |

> **Note:** Production routing is handled by an external reverse proxy (Nginx/Caddy) that terminates TLS and forwards requests to the appropriate service port based on URL path prefix.

---

## 10. Database & Seed Data

There are no formal migration scripts. Schemas are managed implicitly by the ODM layer (Mongoose for Node.js, Motor/Beanie for Python).

| Seed Data | File | Purpose |
|-----------|------|---------|
| Java OOP concept graph | `services/learning-generator/seed/java_oop_graph.json` | Seeded via `seedConceptGraph.js` — concept prerequisites, categories, Bloom's taxonomy levels |
| Quiz question bank | `services/knowledge-analysis/app/data/seed_questions.json` | 281 lines of verified MCQ questions (Loops, Arrays, OOP, Exception Handling, Collections, Recursion) — used as deterministic fallback when LLM generation fails |
| Java concept graph | `services/knowledge-analysis/app/data/java_concept_graph.json` | 33-topic concept hierarchy with difficulty ratings, week areas, and prerequisite edges — drives the assessment coverage model and diagnostic reports |

---

## 11. Deployment Workflow

### Local Development

```bash
# 1. Start external dependencies (MongoDB, Ollama, n8n) on the host
mongod --dbpath ./data/db &
ollama serve &
docker run -d -p 5678:5678 n8nio/n8n &

# 2. Launch the full stack
cd mentora-backend
docker compose up --build -d

# 3. Verify all services
curl http://localhost:3001/health   # user-service
curl http://localhost:5012/health   # lmg-service
curl http://localhost:5007/health   # knowledge-analysis
curl http://localhost:5010/health   # ai-engine
```

### Production (via GHCR)

```bash
# 1. On the production host, clone the repo
git clone https://github.com/<owner>/mentora-backend.git
cd mentora-backend

# 2. Configure environment
cp services/user\ service/.env.example services/user\ service/.env
# ... edit each .env with production values ...

# 3. Deploy using pre-built images
docker compose -f docker-compose.prod.yml up -d

# 4. Verify
docker compose -f docker-compose.prod.yml ps
curl http://localhost:5007/health
```

### CI/CD Flow

```
Developer pushes to main
        │
        ▼
GitHub Actions triggers CI/CD pipeline
        │
        ├──▶ Run test suites (Node + Python)
        │
        ├──▶ Detect changed services (paths-filter)
        │
        └──▶ Build & push Docker images to GHCR (changed only)
                    │
                    ▼
         Production host pulls latest images
         docker compose -f docker-compose.prod.yml pull
         docker compose -f docker-compose.prod.yml up -d
```

---

## 12. Infrastructure Requirements

### Minimum (Development / Demo)

| Resource | Specification |
|----------|--------------|
| CPU | 4 cores |
| RAM | 16 GB (8 GB for Ollama models + 4 GB for services + 4 GB OS) |
| Disk | 50 GB SSD |
| OS | Ubuntu 22.04+ / macOS / Windows with Docker Desktop |
| Network | All ports accessible on localhost |

### Recommended (Production / Research Viva Demo)

| Resource | Specification |
|----------|--------------|
| CPU | 8 cores (GPU optional for Ollama) |
| RAM | 32 GB |
| Disk | 100 GB SSD |
| OS | Ubuntu 22.04 LTS |
| GPU | NVIDIA T4 or better (for faster Ollama inference; CPU-only works but is slower) |
| Network | Ports 80/443 open, reverse proxy (Nginx) for TLS termination |

### Cloud Provider Options

| Provider | Instance | Monthly Cost (est.) | Notes |
|----------|----------|-------------------|-------|
| AWS EC2 | `g4dn.xlarge` (T4 GPU, 16 GB RAM) | ~$50–70 | Best value for GPU + Ollama |
| GCP | `e2-standard-8` (no GPU) | ~$250 | CPU-only; use Gemini API instead of Ollama |
| DigitalOcean | `gpu-1x-t4` (T4 GPU, 16 GB RAM) | ~$60 | Simple pricing, good for demos |
| Hetzner | `CCX33` (8 vCPU, 32 GB) | ~$40 | CPU-only, cheapest for non-GPU |
| RunPod | `GPU Pod` (A40, 24 GB) | ~$0.40/hr | On-demand, ideal for short viva demos |

---

## 13. Known Limitations & Future Improvements

| Area | Current State | Recommended Improvement |
|------|--------------|------------------------|
| **Reverse proxy** | Not included in compose; external proxy assumed | Add Nginx/Caddy container to `docker-compose.prod.yml` with TLS termination and path-based routing |
| **MongoDB in compose** | Not included; expected to run externally | Add `mongo` service to compose for self-contained deployments, or document Atlas setup |
| **n8n in compose** | Not included; expected to run externally | Add `n8n` service to compose with persistent volume for workflow definitions |
| **Health checks** | `healthcheck` directives not configured in compose | Add `healthcheck` blocks with `curl`/`wget` and `depends_on.condition: service_healthy` for resilient startup ordering |
| **Database migrations** | No migration system; schemas are implicit | Adopt a migration tool (e.g., `migrate-mongo` for Node.js, `alembic` for Python) for version-controlled schema changes |
| **Secrets management** | `.env` files in repo | Use Docker secrets, Vault, or cloud provider secret managers (AWS SSM, GCP Secret Manager) for production |
| **Monitoring** | No observability stack | Add Prometheus metrics export + Grafana dashboards; add structured logging (e.g., ELK or Loki) |
| **Logging** | `console.log` / Python `logging` to stdout | Centralised logging via Docker log drivers or a log aggregator |
| **Rate limiting** | Not configured at the reverse proxy level | Add rate limiting at the Nginx layer to protect against abuse |
| **SSL/TLS** | External termination assumed | Automate certificate management with Let's Encrypt + Certbot inside the Nginx container |
| **Auto-scaling** | Single-host deployment only | For higher load, migrate to Kubernetes with HPA; for this project scale, single-host is sufficient |
