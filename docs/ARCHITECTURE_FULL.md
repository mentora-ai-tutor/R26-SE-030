# Mentora — Full System Architecture

> Agentic AI-Driven Multi-Agent Tutoring System for Personalized Learning and Mastery Assessment
> **Project:** R26-SE-030 · **Cluster:** COEAI (Centre of Excellence for AI), SLIIT
> **Document version:** 1.0 · **Date:** August 2026

This document describes the **entire Mentora system** — the Next.js frontend and all six backend microservices — as a single end-to-end architecture: routes, data flows, authentication, external dependencies, deployment topology, and per-service APIs.

---

## Table of Contents

1. [High-Level Overview](#1-high-level-overview)
2. [System Architecture Diagram](#2-system-architecture-diagram)
3. [Frontend Architecture](#3-frontend-architecture)
   - [Route Map](#31-route-map)
   - [Layout & Providers](#32-layout--providers)
   - [API Client Layer](#33-api-client-layer)
   - [Key Components](#34-key-components)
   - [Auth & State](#35-auth--state)
4. [Backend Microservices](#4-backend-microservices)
   - [user-service](#41-user-service-3001)
   - [lmg-service (Learning Material Generator)](#42-lmg-service--learning-material-generator-5012)
   - [assessment-agent (AME)](#43-assessment-agent--ame-5002)
   - [peer-learning](#44-peer-learning-8000)
   - [knowledge-analysis (KAA)](#45-knowledge-analysis--kaa-5007)
   - [ai-engine](#46-ai-engine-5010)
5. [Cross-Service Data Flow](#5-cross-service-data-flow)
6. [Authentication & Authorization](#6-authentication--authorization)
7. [External Dependencies](#7-external-dependencies)
8. [Deployment Topology](#8-deployment-topology)
9. [Port Mapping](#9-port-mapping)
10. [Appendix: Page → Service Matrix](#10-appendix-page--service-matrix)

---

## 1. High-Level Overview

Mentora is a **microservices-based adaptive Java-learning platform**. A single **Next.js frontend** (App Router, React 19) talks to **six independently containerised backend services**, each owning one bounded domain:

| Service | Role in the system |
|---|---|
| **user-service** | Central identity & JWT authority |
| **lmg-service** | Learning-material generation (mastery → lessons/quiz/flashcards) |
| **assessment-agent (AME)** | Interactive adaptive assessment + RAG |
| **peer-learning** | Collaborative learning, real-time pair sessions, quizzes |
| **knowledge-analysis (KAA)** | The diagnostic brain: mastery profiling, GitHub forensics, adaptive quiz, career prediction |
| **ai-engine** | Stateless Java code sandbox + AI code feedback |

The system is orchestrated with **Docker Compose**, deployed through a **GitHub Actions CI/CD** pipeline to **GHCR**, and backed by three external dependencies: **MongoDB**, **Ollama** (local LLM), and **Google Gemini (Vertex AI)**. n8n is used by the LMG/AME services for workflow triggers (and is the subject of an ongoing simplification decision — see `ARCHITECTURE.md §7`).

---

## 2. System Architecture Diagram

```
┌────────────────────────────────────────────────────────────────────────────────────┐
│                          FRONTEND — mentora-frontend                               │
│                     Next.js 16 · React 19 · Tailwind 4 · App Router                 │
│                                    :3000                                            │
│                              (AuthProvider + ActiveReviewProvider)                  │
│                                                                                     │
│   / /login /signup /forgot-password        ──  auth.ts, settings.ts              │
│   /dashboard                                ──  knowledgeProfile, learningGenerator│
│   /knowledge-assist/*                       ──  review, quiz, sandbox,             │
│                                                 knowledgeProfile, career          │
│   /assessment/*                             ──  assessment.ts                    │
│   /learning-generator/*                     ──  learningGenerator, aiEngine       │
│   /peer-learning/*                          ──  peerLearning (REST + WebSocket)   │
│   /settings /notification                   ──  settings, peerLearning            │
└──────┬──────────┬──────────┬──────────┬──────────┬──────────┬──────────┬──────────┘
       │          │          │          │          │          │          │
       │ :3001    │ :5012    │ :5002    │ :8000    │ :5007    │ :5010    │(auth)
       ▼          ▼          ▼          ▼          ▼          ▼          ▼
┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐
│ user-      │ │ lmg-       │ │ assessment │ │ peer-      │ │ knowledge- │ │ ai-engine  │
│ service    │ │ service    │ │ -agent(AME)│ │ learning   │ │ analysis   │ │            │
│ Node/Expr  │ │ Node/Expr  │ │ Node/Expr  │ │ Python/    │ │ Python/    │ │ Python/    │
│ :3001      │ │ :5012      │ │ :5002      │ │ FastAPI    │ │ FastAPI    │ │ FastAPI    │
│            │ │            │ │            │ │ :8000      │ │ :5007      │ │ :5010      │
└──┬─────────┘ └──┬─────────┘ └──┬─────────┘ └──┬─────────┘ └──┬─────────┘ └──┬─────────┘
   │              │              │              │              │              │
   │  Mongo       │  Mongo       │  Mongo       │  Mongo       │  Mongo       │
   │  Mongoose    │  Mongoose    │  Mongoose    │  pymongo     │  Motor       │ (stateless)
   │              │              │              │              │              │
   │              │              │              │              │              │
   │              │◄─────────────┼──────────────┼──────────────┼──────────────►│
   │              │              │              │              │              │
┌──▼──────────────▼──────────────▼──────────────▼──────────────▼──────────────▼───┐
│                              EXTERNAL DEPENDENCIES                                │
│                                                                                    │
│   ┌───────────────┐   ┌───────────────┐   ┌───────────────┐   ┌───────────────┐  │
│   │   MongoDB     │   │   Ollama      │   │  Gemini       │   │   OpenAI      │  │
│   │  (Atlas/self) │   │ (local)       │   │  (Vertex)     │   │  (peer-only)  │  │
│   │   :27017      │   │   :11434      │   │               │   │               │  │
│   └───────────────┘   └───────────────┘   └───────────────┘   └───────────────┘  │
│   ┌───────────────┐   ┌───────────────┐                                           │
│   │   n8n (LMG/   │   │   GitHub      │                                           │
│   │   AME) :5678  │   │   REST API    │                                           │
│   └───────────────┘   └───────────────┘                                           │
└──────────────────────────────────────────────────────────────────────────────────┘
```

**Legend — inter-service edges (dashed = internal, solid = JWT/auth):**

```
user-service ◄── JWT verify (internal HTTP) ── lmg-service, knowledge-analysis
user-service ◄── shared JWT_SECRET (local verify) ── assessment-agent, peer-learning
knowledge-analysis ──► ai-engine        (sandbox challenge verification)
lmg-service    ──► user-service        (internal student data)
knowledge-analysis ──► user-service    (internal GitHub credential fetch)
lmg-service / assessment-agent ──► n8n (workflow triggers)
```

---

## 3. Frontend Architecture

### 3.1 Route Map

App Router — **30 page routes** across three route groups. Auth pages live in the `(auth)` group (no URL prefix); dashboard pages in `(dashboard)`.

#### Public
| Route | Purpose |
|---|---|
| `/` | Landing / marketing page |
| `/login` | Sign in |
| `/signup` | Registration (name, email, password, country) |
| `/forgot-password` | Password reset request |

#### Dashboard — Auth-required
| Route | Purpose |
|---|---|
| `/dashboard` | Home: mastery score, gaps, strengths, recent materials, jobs |
| `/knowledge-assist` | Aggregated knowledge profile (reviews + sandbox + quiz + timeline) |
| `/knowledge-assist/assessment` | Skill-check quiz (`SkillCheckPanel`), question-set history, retake |
| `/knowledge-assist/sandbox` | Java coding challenges; execute via AI Engine; save attempts |
| `/knowledge-assist/forensics` | GitHub repo selection, review jobs, per-repo results |
| `/knowledge-assist/mastery` | Canonical mastery profile + career-fit card |
| `/learning-generator` | Material-generation overview, jobs, gaps, coverage |
| `/learning-generator/knowledge-gaps` | Filterable gap list |
| `/learning-generator/materials` | Material library (search/filter/delete) |
| `/learning-generator/materials/[materialId]` | Interactive material workspace (editor + quiz) |
| `/learning-generator/workspace` | Free-form code workspace |
| `/learning-generator/coverage` | Concept-graph coverage |
| `/peer-learning` | Peer-learning home, matching, AI assistant |
| `/peer-learning/pair-session` | Real-time collab (chat + Yjs editor + whiteboard) |
| `/peer-learning/quiz` | Individual 7-question quiz |
| `/assessment` | Assessment overview (→ launch) |
| `/assessment/launch` | Launch screen with mastery + topics |
| `/assessment/session` | Active assessment (MCQ + code challenges, sandbox) |
| `/assessment/questions-answers` | Q&A history |
| `/assessment/report` | Per-topic feedback report |
| `/assessment/summary` | Session summary |
| `/assessment/transition` | Post-topic transition |
| `/settings` | Profile / security / preferences / account deletion |
| `/notification` | Peer-match notifications |

> `/progress` appears in the sidebar but has **no route yet** (planned).

### 3.2 Layout & Providers

- **Root layout** (`layout.tsx`) — server component: fonts, `<Providers>` wrapper.
- **Providers** (`Providers.tsx`) — client component, nesting order:
  `AuthProvider` → `ActiveReviewProvider` → `Toaster` (sonner).
- **Auth layout** (`(auth)/layout.tsx`) — split-screen with animated branding.
- **Dashboard layout** (`(dashboard)/layout.tsx`) — auth guard; if unauthenticated redirects to `/login`; otherwise renders `DashboardLayout`.
- **DashboardLayout** (`components/layout/DashboardLayout.tsx`) — fixed `Sidebar` + `Header` + scrollable `main` + `Footer`.

### 3.3 API Client Layer

All backend access goes through typed client modules in `src/lib/api`, one per service:

| Client | Base URL (env var) | Default port | Service |
|---|---|---|---|
| `auth.ts`, `settings.ts`, `github.ts` | `NEXT_PUBLIC_API_URL` | 3001 | user-service |
| `learningGenerator.ts` | `NEXT_PUBLIC_LMG_API_URL` | 5012 | lmg-service |
| `assessment.ts` | `NEXT_PUBLIC_AME_API_URL` | 5002 | assessment-agent |
| `peerLearning.ts` | `NEXT_PUBLIC_PEER_LEARNING_API_URL` | 8000 | peer-learning |
| `review.ts`, `quiz.ts`, `sandbox.ts`, `knowledgeProfile.ts`, `career.ts` | `NEXT_PUBLIC_KNOWLEDGE_API_URL` | 5007 | knowledge-analysis |
| `aiEngine.ts` | `NEXT_PUBLIC_AI_ENGINE_API_URL` | 5010 | ai-engine |

Each client attaches `Authorization: Bearer <accessToken>` from **localStorage** (except `aiEngine.ts`, which is unauthenticated). Response envelopes differ by service (see below).

### 3.4 Key Components

- **`SkillCheckPanel`** (`components/sandbox/SkillCheckPanel.tsx`) — adaptive MCQ/predict-output quiz: `idle → starting → question → answered → completed`; supports custom starters (retake) and auto-start.
- **`CareerFitCard`** (`components/career/CareerFitCard.tsx`) — career prediction.
- **`CollaborativeOverlay`** (`components/peer-learning/`) — whiteboard (fabric.js) + remote cursors.
- **`IndividualQuiz`** (`components/peer-learning/`) — standalone quiz.
- **Learning-generator set**: `OverviewSidebar`, `ContentRenderer`, `QuizSection`, `FlashcardsPanel`, `TestsPanel`, `LearningPathSidebar`, `JobCard`, `SearchFilterBar`, etc.
- **UI primitives**: shadcn/ui `Button`, `Card`, `Input`, `Badge`, etc.

### 3.5 Auth & State

- **AuthContext** — stores `accessToken`, `refreshToken`, `user` in `localStorage`. On load, refreshes the user via `GET /api/students/me`, transparently rotating tokens via `POST /api/auth/refresh` on 401. Logout clears all keys and redirects to `/login`.
- **ActiveReviewContext** — tracks a running GitHub review job in `sessionStorage`, polls every 5 s, drives sidebar glow + sandbox redirect + completion toasts.
- **useWorkspaceSession** — persists the code workspace in `sessionStorage` across navigations.

---

## 4. Backend Microservices

### 4.1 user-service (:3001)
**Node.js / Express · MongoDB (Mongoose) · JWT authority**

Central identity provider. Issues JWT/refresh tokens, manages students, admin tooling, GitHub OAuth, and internal verification endpoints for other services.

**Endpoints**
- Health/metrics: `GET /health`, `GET /metrics`
- Auth (`/api/auth`): `register`, `login`, `refresh`, `logout`, `forgot-password`, `reset-password`, `verify-email`, `resend-verification`, `sessions`, `sessions/:sessionId`
- Students (`/api/students`): `me` (GET/PUT), `me/password`, `me/stats`, `me/summary`, `me/preferences` (GET/PUT), delete `me`
- Admin (`/api/admin`): `users`, `users/:userId` (GET/PUT/DELETE/restore/activate/deactivate), `users/bulk`, `users/:userId/audit-logs`, `stats`, `export`
- GitHub OAuth (`/api/github`): `oauth/start`, `oauth/callback`, `status`, `unlink`
- Analytics: `/analytics`, `/analytics/recent`
- **Internal** (`/internal`, `X-Internal-Key`): `auth/verify`, `students/:studentId` (GET/PATCH stats), `github/credential/:studentId`

### 4.2 lmg-service · Learning Material Generator (:5012)
**Node.js / Express · MongoDB (Mongoose) · delegates auth to user-service**

Consumes mastery profiles and generates structured learning materials (lessons, quizzes, flashcards), tracks progress/jobs, seeds the concept graph.

**Endpoints**
- `GET /health`
- Mastery (`/api/mastery`): `submit`, `profile/:profileId`, `:studentId` (latest), `:studentId/history`
- Materials (`/api/materials`): `:studentId`, `:studentId/topics`, `:studentId/stats`, `:studentId/topic/:topicId`, `item/:materialId` (GET/DELETE)
- Agent/Jobs (`/api/agent`): `logs/:studentId`, `jobs/:jobId` (GET/PATCH), `jobs/:jobId/complete`, `jobs/student/:studentId`, `stats/global`, `health`, `retry/:materialId`
- Progress (`/api/progress`): `student/:studentId`, `student/:studentId/stats`, `material/:materialId` (GET/PUT)
- Concept graph (`/api/concept-graph`): `coverage/:studentId`, `seed`
- n8n webhooks (`/api/webhooks/n8n`): `material`, `material/batch`, `job/status`, `profile`, `complete`

### 4.3 assessment-agent · AME (:5002)
**Node.js / Express · MongoDB (Mongoose) · local JWT verify (shared `JWT_SECRET`)**

Interactive adaptive assessment sessions, sandboxed Java execution, per-session feedback reports, and RAG document retrieval.

**Endpoints**
- `GET /health`
- `/api/ame`: `start-session`, `submit-answer`, `run-code`, `session/:sessionId`, `sessions`, `questions`, `feedback-report/:sessionId`
- RAG (`/api/ame/rag`): `ingest`, `retrieve`, `documents`, `documents/:documentId` (GET/DELETE), `stats`

### 4.4 peer-learning (:8000)
**Python / FastAPI + python-socketio · MongoDB (pymongo) · local JWT verify**

Collaborative learning: onboarding + 7-question diagnosis, code evaluation, strength-vs-gap peer matching, real-time collab rooms (Yjs editor / whiteboard / chat), AI moderator + support chatbot, individual quizzes, question generator, RAG recommendations, notifications, AI-teacher rooms.

**HTTP endpoints** (selected): `/api/student/*`, `/api/assessment/evaluate`, `/api/peer/*`, `/api/chat/*`, `/api/collab/*`, `/api/individual-quiz/*`, `/api/question-generator/*`, `/api/rag-content/recommend`, `/api/content/recommend`, `/api/moderator/*`, `/api/knowledge/query`.
**WebSocket**: `/api/chat/ws/:roomId/:studentId`, `/api/collab/ws/collab/:roomId`; Socket.IO at `/socket.io` (draw events).

### 4.5 knowledge-analysis · KAA (:5007)
**Python / FastAPI · MongoDB (Motor) · delegates auth to user-service**

The diagnostic brain. Fuses **quiz results + sandbox attempts + GitHub repo reviews** into a canonical **Mastery Profile** (`kaa-lmg-v1.0`), runs the 10-step analysis pipeline, generates adaptive quizzes, produces a rich forensic `diagnostic_report`, and predicts career fit.

**Endpoints**
- Core (`routes.py`): `POST /analyze`, `POST /analyze/auto` (always bridges stored data → mastery profile), `POST /quiz/generate`, `GET /health`, `GET /demo`
- Quiz (`/api/v1/quiz`): `POST session`, `POST session/{id}/answer`, `GET session/{id}`, `GET sets`, `GET sets/{id}`, `POST sets/{id}/retake`, `GET results/{student_id}/latest`, `GET results/{student_id}`
- Sandbox (`/api/v1/sandbox`): `GET challenges`
- Knowledge profile (`/api/v1/knowledge-profile`): `POST sandbox-attempts`, `GET me`
- GitHub analysis (`/api/v1/github-analysis`): `POST analyze`, `GET health`, `POST metrics-only`
- GitHub fetch & analyze (`/api/v1/github-fetch-analyze`): `POST fetch-and-analyze`, `POST fetch-only`, `GET check-github-auth`
- GitHub review (`/api/v1/github-review`): `GET llm-options`, `POST select-repos`, `POST review-top-5`, `GET status/{job_id}`, `POST re-review`
- Mastery profiles (`/api/v1/mastery-profiles`): `GET /{student_id}/latest`
- Career (`/api/v1/career`): `POST predict`, `GET /{student_id}/latest`

**Key internals**: `services/pipeline.py` (10-step orchestrator), `services/quiz_generator.py` + `quiz_store.py` (adaptive + assessment quiz, set history/retake), `services/concept_graph.py` (33-topic graph), `services/profile_contract.py` + `diagnostic_report.py`, `services/career/store.py`, `services/github_*`.

### 4.6 ai-engine (:5010)
**Python / FastAPI · stateless · no auth (internal-only)**

Sandboxed Java compile/run plus Ollama-driven AI code assistance. Accessed by the frontend (workspace/sandbox/material) and by KAA (to verify generated sandbox challenges by executing reference solutions).

**Endpoints**
- `GET /health`
- `/api`: `execute`, `feedback`, `run-with-feedback`, `explain-simpler`, `analogy`, `explain-code`, `fix-error`, `code-review`, `flashcards`, `generate-tests`

---

## 5. Cross-Service Data Flow

```
Browser
  └─► user-service      register/login/refresh (JWT)
  ├─► KAA               skill-check quiz → /analyze/auto → mastery profile
  ├─► KAA               GitHub repo review → repo_review_jobs → /analyze/auto
  ├─► KAA               sandbox attempts saved → /knowledge-profile/me
  ├─► LMG               mastery profile submitted → generate materials → n8n webhook
  ├─► AME               adaptive assessment sessions + feedback + RAG
  ├─► peer-learning      diagnosis, matching, collab rooms, quizzes, notifications
  └─► ai-engine          code execution + AI feedback

Internal:
  lmg-service ──► user-service        (POST /internal/auth/verify, students/stats)
  knowledge-analysis ──► user-service (POST /internal/auth/verify, github credential)
  knowledge-analysis ──► ai-engine    (execute reference solutions to verify challenges)
  lmg-service / assessment-agent ──► n8n  (workflow triggers + webhook callbacks)
```

---

## 6. Authentication & Authorization

Mentora uses **three** auth strategies:

| Strategy | Services | Mechanism |
|---|---|---|
| **Central verify** | lmg-service, KAA | Call `POST /internal/auth/verify` with `X-Internal-Key` |
| **Shared-secret local verify** | assessment-agent, peer-learning | `jwt.verify(token, JWT_SECRET)` locally (share user-service's secret) |
| **No auth** | ai-engine | Internal-only, never exposed to the browser directly |

- The **user-service is the sole JWT authority**; it signs with `JWT_SECRET` / `JWT_REFRESH_SECRET` and protects `/internal/*` with the `X-Internal-Key` middleware.
- The **frontend** holds JWTs in `localStorage` and attaches `Authorization: Bearer <token>` to every client except ai-engine.
- KAA and LMG *send* `X-Internal-Key` to user-service; enforcing internal-key auth on KAA's own read endpoints is a noted, tracked gap (`ARCHITECTURE.md §9`).

---

## 7. External Dependencies

| Dependency | Used by | Purpose |
|---|---|---|
| **MongoDB** | all except ai-engine | per-service databases (Mongoose / Motor / pymongo) |
| **Ollama** (local `:11434`) | ai-engine, KAA, AME | code feedback, behavioral analysis, review fallback |
| **Google Gemini (Vertex)** | KAA | repo code review, sandbox challenge generation (`gcp-sa.json`) |
| **OpenAI (gpt-4o-mini)** | peer-learning | quiz generation, evaluation, RAG, chat, summarization |
| **n8n** (`:5678`) | lmg-service, assessment-agent | workflow triggers + webhooks |
| **GitHub REST API** | KAA, user-service | commit fetching, repo review, OAuth |

---

## 8. Deployment Topology

- **Local dev**: `docker compose up --build -d` builds all six images from source; external deps (Mongo/Ollama/n8n) run on the host via `host.docker.internal:host-gateway`.
- **Production**: `docker-compose.prod.yml` pulls pre-built images from **GHCR**; KAA maps host `8001` (dev `5007`); CORS restricted to the deployed frontend domain.
- **CI/CD** (`.github/workflows/ci.yml`): on push/PR to `main` → `test-node` (Jest/node:test) + `test-python` (pytest) in parallel → `changes` (paths-filter) → build & push only changed services to GHCR with `latest` + `<commit-sha>` tags.
- **Frontend**: deployed separately to Vercel (`https://mentora.kaweesha.com`).

Startup order: `user-service` → (ai-engine, lmg-service, assessment-agent) → `knowledge-analysis` (depends on user-service + ai-engine); `peer-learning` starts independently.

---

## 9. Port Mapping

| Service | Container | Host (dev) | Host (prod) | Frontend env var |
|---|---|---|---|---|
| Frontend (Next.js) | 3000 | 3000 | (Vercel) | — |
| user-service | 3001 | 3001 | 3001 | `NEXT_PUBLIC_API_URL` |
| lmg-service | 3002 | 5012 | 5012 | `NEXT_PUBLIC_LMG_API_URL` |
| assessment-agent | 5002 | 5002 | 5002 | `NEXT_PUBLIC_AME_API_URL` |
| peer-learning | 8000 | 8000 | 8000 | `NEXT_PUBLIC_PEER_LEARNING_API_URL` |
| knowledge-analysis | 8000 | 5007 | 8001 | `NEXT_PUBLIC_KNOWLEDGE_API_URL` |
| ai-engine | 5010 | 5010 | 5010 | `NEXT_PUBLIC_AI_ENGINE_API_URL` |

---

## 10. Appendix: Page → Service Matrix

| Page | Service(s) | Ports |
|---|---|---|
| `/login /signup /forgot-password` | user-service | 3001 |
| `/settings` | user-service | 3001 |
| `/dashboard` | KAA · lmg-service | 5007 · 5012 |
| `/knowledge-assist` | KAA | 5007 |
| `/knowledge-assist/assessment` | KAA | 5007 |
| `/knowledge-assist/sandbox` | KAA · ai-engine | 5007 · 5010 |
| `/knowledge-assist/forensics` | KAA | 5007 |
| `/knowledge-assist/mastery` | KAA | 5007 |
| `/learning-generator` | KAA · lmg-service | 5007 · 5012 |
| `/learning-generator/*` (gaps/materials/coverage) | lmg-service | 5012 |
| `/learning-generator/materials/[id]` | lmg-service · ai-engine | 5012 · 5010 |
| `/learning-generator/workspace` | ai-engine | 5010 |
| `/peer-learning/*` | peer-learning | 8000 |
| `/notification` | peer-learning | 8000 |
| `/assessment/*` | assessment-agent | 5002 |

---

*This document is generated from the live source trees of `mentora-backend` and `mentora-frontend`. Companion docs: `docs/DEPLOYMENT_REPORT.md` (deployment), `ARCHITECTURE.md` (KAA deep-dive), `INTEGRATION_PLAN.md`, `FULL_SYSTEM_SETUP.md`.*
