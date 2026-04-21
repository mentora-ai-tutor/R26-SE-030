# Collaborative Peer Learning & Knowledge Exchange Agent

A production-ready system that transforms weak students into strong learners through intelligent peer-to-peer learning, powered by the Hungarian Algorithm for optimal matching and gemma4 (via Ollama) for adaptive question generation.

## Architecture

```
peer_learning/
├── main.py                          # FastAPI application entry point
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── PeerLearning.postman_collection.json
├── tests/
│   └── test_flow.py                 # End-to-end test suite
└── app/
    ├── core/
    │   ├── config.py                # Settings (pydantic-settings)
    │   ├── database.py              # MongoDB connection & indexes
    │   ├── llm_client.py            # Ollama/gemma4 client with retry
    │   └── websocket_manager.py     # WebSocket room manager
    ├── models/
    │   └── models.py                # All Pydantic models & enums
    ├── services/
    │   ├── import_service.py        # Phase 1: Data ingestion
    │   ├── pairing_service.py       # Phase 2: Hungarian algorithm matching
    │   ├── session_service.py       # Phase 3 & 4: Interactive sessions
    │   ├── question_service.py      # Phase 3 & 9: LLM question generation
    │   ├── pool_service.py          # Phase 5 & 10: Improved/verified pools
    │   ├── notification_service.py  # Phase 6: Waiting queue & notifications
    │   ├── group_service.py         # Phase 7: Group sessions
    │   ├── verification_service.py  # Phase 10: Mastery verification
    │   └── performance_service.py   # Phase 11: Reports & completion
    ├── api/
    │   ├── __init__.py              # Router aggregator
    │   └── routes/
    │       ├── students.py          # Student management endpoints
    │       ├── sessions.py          # Pair session endpoints
    │       ├── groups.py            # Group session endpoints
    │       ├── pools.py             # Topic pool endpoints
    │       ├── notifications.py     # Notification & queue endpoints
    │       ├── performance.py       # Performance & question endpoints
    │       └── websockets.py        # Real-time WebSocket endpoints
    └── utils/
        └── helpers.py               # Utility functions
```

## Quick Start

### Option A: Docker Compose (Recommended)

```bash
# Clone and start everything (MongoDB + Redis + Ollama + App)
cp .env.example .env
docker-compose up -d

# Wait for Ollama to pull gemma4 (~2-3 minutes first run)
docker-compose logs -f ollama

# Access API docs
open http://localhost:8000/docs
```

### Option B: Local Development

```bash
# Prerequisites: MongoDB, Redis, Ollama running locally
# Pull the model
ollama pull gemma4:latest

# Setup Python environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your MongoDB/Redis/Ollama URLs

mkdir -p logs
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Running Tests

```bash
# Make sure the server is running first
python tests/test_flow.py

# Or against a different URL
python tests/test_flow.py --base-url http://your-server:8000
```

## Complete System Flow

### Phase 1 — Data Ingestion
```bash
POST /api/students/import
# Import JSON with student strengths, weaknesses, mastery profiles
# Gaps are automatically sorted: FUNDAMENTAL_GAP first
```

### Phase 2 — Pair Formation (Hungarian Algorithm)
```bash
POST /api/sessions/batch/all-topics   # Match all topics at once
# OR
GET  /api/sessions/match/{student_id}  # Preview best teacher
POST /api/sessions/match/{student_id}/confirm  # Create session
```

### Phase 3 — Interactive Session
```bash
POST /api/sessions/{session_id}/start-question   # Generate Bloom question via gemma4
POST /api/sessions/{session_id}/answer           # Submit answer (LLM evaluated)
POST /api/sessions/{session_id}/hint             # Request hint (max 3)
POST /api/sessions/{session_id}/ask-teacher      # Ask teacher for help
```

### Phase 4 — Performance & Completion
```bash
POST /api/sessions/{session_id}/complete
# Learner ≥90% → MASTERED → Phase 5
# Learner 50-89% → CONTINUE
# Learner <50% → REGROUP (find new teacher)
```

### Phase 5 — Improved Pool
```bash
GET /api/pools/all                      # See all topic pools
GET /api/pools/{topic_id}/students      # See who's in a pool
# Pool ≥3 students → triggers group session (Phase 7)
```

### Phase 6 — Waiting Queue
```bash
POST /api/waiting/add                             # Join queue when no teacher
GET  /api/notifications/{student_id}              # Check for teacher notifications
POST /api/notifications/{notification_id}/accept  # Accept in 60 seconds
POST /api/notifications/{notification_id}/cancel  # Cancel (returns to queue)
```

### Phase 7 — Group Sessions
```bash
POST /api/groups/form               # Form 3-student group (needs ≥3 in pool)
GET  /api/groups/{session_id}        # Get problem, roles, sandbox
POST /api/groups/{session_id}/submit # Submit role scores
```

### Phase 10 — Verification
Automatically triggered after 3 consecutive group sessions ≥90%

### Phase 11 — Completion
```bash
GET /api/performance/{student_id}/completion  # Full completion report
```

## Real-Time WebSockets

```javascript
// Pair session: chat + sandbox + voice signaling
const ws = new WebSocket('ws://localhost:8000/ws/session/PS-XXXXXXXX?student_id=STU-001&role=learner');

ws.send(JSON.stringify({ type: 'chat', message: 'I need help!' }));
ws.send(JSON.stringify({ type: 'sandbox_update', code: 'def hello(): pass', language: 'python' }));
ws.send(JSON.stringify({ type: 'voice_signal', signal_type: 'offer', signal_data: {...}, target_student_id: 'STU-002' }));

// Notifications
const notifWs = new WebSocket('ws://localhost:8000/ws/notifications/STU-001');
```

## MongoDB Collections

| Collection | Purpose |
|---|---|
| `students` | Student profiles, gaps, strengths, session state |
| `pair_sessions` | All pair programming sessions |
| `group_sessions` | All 3-student collaborative sessions |
| `improved_pools` | Students who mastered a topic in pair sessions |
| `verified_pools` | Fully certified teachers |
| `waiting_queue` | Students waiting for a teacher |
| `notifications` | Teacher-availability notifications (TTL: 60s) |
| `questions_bank` | All LLM-generated questions with analytics |
| `batch_pairing_records` | History of batch matching operations |

## Compatibility Score Formula

```
Score = Teacher_Confidence(25%) + Teacher_Mastery_Level(25%) 
      + Gap_Severity(20%) + Gap_Magnitude(15%) + Learner_Inverse_Confidence(15%)
```

## Learner Score Formula

```
Base_Accuracy = (Correct / Total) × 100
Penalty = (Hints × 5) + (Help_Requests × 10)
Final = Base_Accuracy - Penalty
```

## Bloom's Taxonomy Progression

```
Level 1 (Remember) → Level 2 (Understand) → Level 3 (Apply) 
→ Level 4 (Analyze) → Level 5 (Evaluate) → Level 6 (Create)

Advance: 2 consecutive correct answers
Regress: 2 consecutive incorrect answers  
Mastery: 2 consecutive correct at Level 5+
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `MONGODB_URL` | `mongodb://localhost:27017` | MongoDB connection |
| `MONGODB_DB_NAME` | `peer_learning` | Database name |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `gemma4:latest` | LLM model name |
| `OLLAMA_TIMEOUT` | `120` | LLM request timeout (seconds) |
| `NOTIFICATION_TTL_SECONDS` | `60` | Notification expiry time |
| `COMPATIBILITY_THRESHOLD` | `60` | Min score for queue matching |
| `MASTERY_THRESHOLD` | `90` | Min score to enter improved pool |
| `IMPROVED_POOL_GROUP_TRIGGER` | `3` | Pool size to trigger group session |
| `VERIFICATION_CONSECUTIVE_SESSIONS` | `3` | Group sessions needed for verification |
