# Mentora Full System Setup Guide

Last updated: 2026-05-08

This guide documents the files, private configuration, setup commands, and pull request workflow needed to run this repository from the currently used backend branch.

Current backend repository:

```text
Repository: mentora-ai-tutor/R26-SE-030
Branch:     knowledge-analysis/kalana
Remote:     https://github.com/mentora-ai-tutor/R26-SE-030.git
```

Use the frontend repository only when running the full browser demo:

```text
Repository folder: mentora-frontend
Branch:            feature/kalana
```

## 1. Expected Folder Structure

For the full demo stack, keep the backend and frontend repositories in the same parent folder:

```text
SLIIT Work/
  docker-compose.yml              # parent full-stack compose file, local setup file
  mentora-frontend/               # frontend repo on feature/kalana
  R26-SE-030/                     # backend repo on knowledge-analysis/kalana
```

The parent `docker-compose.yml` is outside this backend repo. It is required for the full demo because it starts MongoDB, frontend, user service, knowledge-analysis, and ai-engine together.

The repo-local `R26-SE-030/docker-compose.yml` is different: it starts only `user-service`, `lmg-service`, and `ai-engine`. It does not start MongoDB, frontend, or knowledge-analysis.

## 2. Required Tools

Install these before setup:

```text
Git
Docker Desktop with Docker Compose v2
Node.js 20+ and npm
Python 3.11+
MongoDB Compass or mongosh, optional but useful
Ollama, required for local AI engine fallback
Google Cloud service account JSON, required for Gemini/Vertex knowledge-analysis
GitHub account with access to mentora-ai-tutor/R26-SE-030
```

Useful Ollama models for this branch:

```bash
ollama pull llama3:8b
ollama pull qwen2.5-coder:7b
```

## 3. Branch Setup

Clone the backend branch:

```bash
git clone -b knowledge-analysis/kalana https://github.com/mentora-ai-tutor/R26-SE-030.git
```

If the backend repo already exists:

```bash
cd "R26-SE-030"
git fetch origin
git checkout knowledge-analysis/kalana
git pull --ff-only origin knowledge-analysis/kalana
```

For the full UI demo, also clone or update the frontend branch beside this repo:

```bash
git clone -b feature/kalana <frontend-repo-url> mentora-frontend
```

If the frontend repo already exists:

```bash
cd "mentora-frontend"
git fetch origin
git checkout feature/kalana
git pull --ff-only origin feature/kalana
```

## 4. Required Setup Files And Docs

Use this inventory when preparing a clean machine or reviewing whether the repo has everything needed.

| Path | Purpose | Commit to Git? |
|---|---|---|
| `README.md` | Backend repository overview. | Yes |
| `ARCHITECTURE.md` | Knowledge Analysis Agent architecture and roadmap. | Yes |
| `docs/FULL_SYSTEM_SETUP.md` | This full setup and PR workflow guide. | Yes |
| `docs/INTEGRATION_PLAN.md` | GitHub OAuth, Gemini review, and Java sandbox integration plan. | Yes |
| `.github/workflows/ci.yml` | PR/push CI that builds `ai-engine`, `user-service`, and `lmg-service`. | Yes |
| `.gitignore` | Keeps env files, secrets, logs, builds, and local overrides out of Git. | Yes |
| `docker-compose.yml` | Repo-local backend subset compose file. | Yes |
| `docker-compose.prod.yml` | GHCR image-based production compose template. | Yes |
| `../docker-compose.yml` | Parent full-stack local compose file for frontend + backend demo. | No, local parent setup |
| `services/user service/.env.example` | Template for user-service runtime config. | Yes |
| `services/user service/.env` | Local user-service secrets and connection values. | No |
| `services/user service/README.md` | User-service endpoints and service setup notes. | Yes |
| `services/user service/API_DOCS.md` | User-service API documentation. | Yes |
| `services/user service/docs/postman.json` | User-service Postman collection. | Yes |
| `services/user service/package.json` | User-service dependencies and scripts. | Yes |
| `services/user service/package-lock.json` | Locked user-service npm dependencies. | Yes |
| `services/user service/Dockerfile` | User-service image build file. | Yes |
| `services/knowledge-analysis/.env` | Local knowledge-analysis runtime config. | No |
| `services/knowledge-analysis/secrets/gcp-sa.json` | Google Cloud service account key for Vertex/Gemini. | No |
| `services/knowledge-analysis/requirements.txt` | Knowledge-analysis Python dependencies. | Yes |
| `services/knowledge-analysis/Dockerfile` | Knowledge-analysis image build file. | Yes |
| `services/knowledge-analysis/KAA_BACKEND_DEVELOPMENT_GUIDE.md` | KAA development guide and module structure. | Yes |
| `services/knowledge-analysis/scripts/smoke_test_llm.py` | LLM provider smoke test. | Yes |
| `services/knowledge-analysis/tests/` | KAA test suite. | Yes |
| `services/learning-generator/.env.example` | LMG service runtime config template. | Yes |
| `services/learning-generator/.env` | Local LMG runtime config. | No |
| `services/learning-generator/package.json` | LMG dependencies and scripts. | Yes |
| `services/learning-generator/package-lock.json` | Locked LMG npm dependencies. | Yes |
| `services/learning-generator/Dockerfile` | LMG image build file. | Yes |
| `services/learning-generator/docs/` | LMG and n8n API docs. | Yes |
| `services/learning-generator/postman/` | LMG Postman collections and environment. | Yes |
| `services/learning-generator/n8n/` | LMG n8n workflow export. | Yes |
| `ai-engine/learning-generator/requirements.txt` | AI engine Python dependencies. | Yes |
| `ai-engine/learning-generator/Dockerfile` | AI engine image build file. | Yes |
| `ai-engine/learning-generator/app/` | AI engine FastAPI app for Java execution and Ollama feedback. | Yes |
| `services/peer-learning/.env.example` | Peer-learning config template. | Yes |
| `services/peer-learning/.env` | Local peer-learning config. | No |
| `services/peer-learning/README.md` | Peer-learning setup, endpoints, and test flow. | Yes |
| `services/peer-learning/docker-compose.yml` | Standalone peer-learning compose file. | Yes |
| `services/peer-learning/PeerLearning.postman_collection.json` | Peer-learning Postman collection. | Yes |
| `services/assessment-agent/.env.example` | Assessment agent config template. | Yes |
| `services/assessment-agent/.env` | Local assessment agent config. | No |
| `services/assessment-agent/package.json` | Assessment agent dependencies and scripts. | Yes |

Never commit `.env`, `.env.local`, service account JSON files, generated logs, `node_modules`, virtual environments, or local compose override files.

## 5. Private Configuration Files

Create these files locally before running the system.

### 5.1 User Service

Create:

```text
R26-SE-030/services/user service/.env
```

Start from the template:

```bash
cp "services/user service/.env.example" "services/user service/.env"
```

Required values:

```env
PORT=3001
NODE_ENV=development
SERVICE_NAME=user-service
MONGODB_URI=mongodb://localhost:27017/mentora_users
JWT_SECRET=replace-with-a-long-dev-secret
JWT_EXPIRES_IN=1h
JWT_REFRESH_SECRET=replace-with-a-different-long-dev-secret
JWT_REFRESH_EXPIRES_IN=7d
BCRYPT_SALT_ROUNDS=12
INTERNAL_SERVICE_KEY=replace-with-shared-internal-service-key
CORS_ORIGIN=http://localhost:3000,http://localhost:3002,http://localhost:5173
ENABLE_EMAIL_VERIFICATION=false
ENABLE_ACCOUNT_LOCKOUT=true
ENABLE_AUDIT_LOGGING=true
GH_CLIENT_ID=replace-with-github-oauth-client-id
GH_CLIENT_SECRET=replace-with-github-oauth-client-secret
GH_OAUTH_SCOPE=repo
GH_OAUTH_CALLBACK_URL=http://localhost:3001/api/github/oauth/callback
FRONTEND_ORIGIN=http://localhost:3002
```

Use dummy non-empty GitHub OAuth values only for login/signup demos that do not test GitHub linking. Use real OAuth values for repository review.

### 5.2 Knowledge Analysis

Create:

```text
R26-SE-030/services/knowledge-analysis/.env
R26-SE-030/services/knowledge-analysis/secrets/gcp-sa.json
```

Example `.env`:

```env
APP_NAME=KAA - Knowledge Analysis Agent
APP_VERSION=1.0.0
CORS_ORIGINS=http://localhost:3000,http://localhost:3002,http://localhost:5173
MONGODB_URL=mongodb://localhost:27017
MONGODB_DB=knowledge_analysis
USER_SERVICE_INTERNAL_URL=http://localhost:3001
INTERNAL_SERVICE_KEY=replace-with-same-value-used-by-user-service
GITHUB_API_URL=https://api.github.com
GITHUB_PAT=

LLM_PROVIDER=gemini
GCP_PROJECT=replace-with-gcp-project-id
GCP_LOCATION=us-central1
GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/R26-SE-030/services/knowledge-analysis/secrets/gcp-sa.json
GEMINI_MODEL_PRIMARY=gemini-2.5-pro
GEMINI_MODEL_TOOLS=gemini-2.5-pro
GEMINI_MODEL_GA=gemini-2.5-pro
GEMINI_MODEL_FAST=gemini-2.5-flash

OLLAMA_URL=http://localhost:11434
OLLAMA_MODEL=llama3
```

For Docker full-stack setup, the parent compose file mounts the key at:

```text
/run/secrets/gcp-sa.json
```

### 5.3 Learning Generator

Create this file if running `lmg-service`:

```text
R26-SE-030/services/learning-generator/.env
```

Start from the template:

```bash
cp "services/learning-generator/.env.example" "services/learning-generator/.env"
```

Make sure `INTERNAL_SERVICE_KEY` matches the user-service value.

### 5.4 Frontend

When running the frontend manually instead of through the parent compose file, create:

```text
mentora-frontend/.env.local
```

Recommended values:

```env
NEXT_PUBLIC_API_URL=http://localhost:3001
NEXT_PUBLIC_KNOWLEDGE_API_URL=http://localhost:5007
NEXT_PUBLIC_AI_ENGINE_API_URL=http://localhost:5010
NEXT_TELEMETRY_DISABLED=1
```

## 6. Full Demo Setup With Parent Docker Compose

Use this path when testing the integrated frontend, auth, GitHub linking, knowledge-analysis, MongoDB, and AI engine.

Run from the parent `SLIIT Work/` folder:

```bash
docker compose up --build
```

Expected services:

| Service | URL |
|---|---|
| Frontend | `http://localhost:3002` |
| User service | `http://localhost:3001` |
| Knowledge-analysis | `http://localhost:5007` |
| AI engine | `http://localhost:5010` |
| MongoDB | `mongodb://localhost:27017` |

Health checks:

```text
Frontend:
http://localhost:3002

User service:
http://localhost:3001/health

Knowledge-analysis:
http://localhost:5007/health
http://localhost:5007/docs

AI engine:
http://localhost:5010/health
```

MongoDB Compass connection:

```text
mongodb://localhost:27017
```

Expected databases after using the app:

```text
mentora_users
knowledge_analysis
```

Stop the system:

```bash
docker compose down
```

Use this to remove containers and volumes only when you intentionally want to delete local MongoDB data:

```bash
docker compose down -v
```

## 7. Repo-Local Docker Compose Setup

Use this path only for the backend subset in this repo.

From `R26-SE-030/`:

```bash
docker compose up --build
```

This repo-local compose starts:

| Service | URL |
|---|---|
| User service | `http://localhost:3001` |
| Learning generator service | `http://localhost:5012` |
| AI engine | `http://localhost:5010` |

Important: this compose file does not start MongoDB. Before using it, either:

```text
1. Run MongoDB separately and point service `.env` files at it.
2. Use the parent full-stack compose instead.
3. Add a local `docker-compose.override.yml` with a MongoDB service. Do not commit that override unless the team agrees.
```

If a service runs inside Docker and MongoDB runs on the host machine, use `host.docker.internal` in the service `.env` file:

```env
MONGODB_URI=mongodb://host.docker.internal:27017/mentora_users
```

## 8. Manual Service Setup

Use manual setup when developing one service at a time.

### 8.1 User Service

```bash
cd "services/user service"
npm install
npm run dev
```

Health check:

```text
http://localhost:3001/health
```

### 8.2 Knowledge Analysis

```bash
cd "services/knowledge-analysis"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 5007
```

Health and docs:

```text
http://localhost:5007/health
http://localhost:5007/docs
```

Run tests:

```bash
pytest -q
```

Optional LLM smoke test:

```bash
python scripts/smoke_test_llm.py
```

### 8.3 AI Engine

```bash
cd "ai-engine/learning-generator"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 5010
```

Health check:

```text
http://localhost:5010/health
```

### 8.4 Learning Generator

```bash
cd "services/learning-generator"
npm install
npm run dev
```

Health check:

```text
http://localhost:3002/health
```

When published through repo-local Docker, use:

```text
http://localhost:5012/health
```

### 8.5 Peer Learning

```bash
cd "services/peer-learning"
cp .env.example .env
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Health and docs:

```text
http://localhost:8000/health
http://localhost:8000/docs
```

### 8.6 Assessment Agent

```bash
cd "services/assessment-agent"
cp .env.example .env
npm install
npm run dev
```

Health check:

```text
http://localhost:3001/health
```

If user-service is already using port `3001`, change the assessment agent `PORT` value before starting it.

## 9. End-To-End Demo Checklist

Use this order for a full demo:

```text
1. Confirm backend branch is knowledge-analysis/kalana.
2. Confirm frontend branch is feature/kalana.
3. Create all required `.env` files.
4. Add `services/knowledge-analysis/secrets/gcp-sa.json` if Gemini review is required.
5. Start Ollama if the AI engine fallback is required.
6. Run `docker compose up --build` from the parent folder.
7. Open `http://localhost:3002`.
8. Sign up as a new student.
9. Login and confirm user records appear in `mentora_users`.
10. Test GitHub linking only when real GitHub OAuth credentials are configured.
11. Test repository review only when GitHub OAuth and GCP credentials are configured.
12. Check `http://localhost:5007/docs` for knowledge-analysis endpoints.
```

## 10. Validation Before Opening A PR

Run the checks that match the files you changed.

Knowledge-analysis:

```bash
cd "services/knowledge-analysis"
source .venv/bin/activate
pytest -q
```

User service:

```bash
cd "services/user service"
npm install
npm test
```

Learning generator:

```bash
cd "services/learning-generator"
npm install
npm run lint
```

Docker build sanity check from the repo root:

```bash
docker compose build
```

Full-stack sanity check from the parent folder:

```bash
docker compose up --build
```

## 11. Merge `knowledge-analysis/kalana` To `main` Using A Pull Request

Do not push directly to `main`. Merge this branch through a GitHub pull request.

Prepare the branch:

```bash
cd "R26-SE-030"
git status --short
git fetch origin
git checkout knowledge-analysis/kalana
git pull --ff-only origin knowledge-analysis/kalana
git merge origin/main
```

Resolve conflicts if any, then run the relevant validation checks from section 10.

Push the branch:

```bash
git push origin knowledge-analysis/kalana
```

Create the PR in GitHub:

```text
Base branch:    main
Compare branch: knowledge-analysis/kalana
Title:          Merge knowledge-analysis setup and integration work
```

Include in the PR description:

```text
Summary:
- What changed
- Which services are affected
- Which setup files/docs were updated

Validation:
- Commands run locally
- Docker services tested
- Any checks not run and why

Secrets:
- Confirm no `.env`, service account JSON, OAuth secret, or token was committed
```

The repository CI runs on pull requests targeting `main`. The current workflow builds:

```text
ai-engine
user-service
lmg-service
```

Merge only after:

```text
1. CI checks pass.
2. Required reviewers approve.
3. The PR contains no private secrets.
4. Any merge conflicts with `main` are resolved.
```

After the PR is merged, sync local `main`:

```bash
git fetch origin
git checkout main
git pull --ff-only origin main
```

Delete the feature branch only if the team is finished with it:

```bash
git branch -d knowledge-analysis/kalana
git push origin --delete knowledge-analysis/kalana
```

## 12. Common Problems

MongoDB connection fails in repo-local Docker:

```text
The repo-local compose file does not start MongoDB. Use the parent compose file or point `.env` files to a reachable MongoDB instance.
```

GitHub OAuth popup links but frontend does not update:

```text
Check `FRONTEND_ORIGIN`. For parent Docker setup it should be `http://localhost:3002`.
```

Gemini review fails:

```text
Check `GOOGLE_APPLICATION_CREDENTIALS`, `GCP_PROJECT`, `GCP_LOCATION`, and service account permissions. Use `services/knowledge-analysis/scripts/smoke_test_llm.py` to test provider access.
```

AI engine feedback fails:

```text
Confirm Ollama is running and the configured models are pulled.
```
