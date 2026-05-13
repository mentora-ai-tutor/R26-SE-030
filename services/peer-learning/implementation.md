# Collaborative Peer Learning & Knowledge Exchange Agent — Implementation Document

## Project Overview

This is a **production-ready FastAPI-based microservice** that orchestrates peer-to-peer learning among students. It transforms weak students into strong learners by:

1. **Importing student profiles** with knowledge gaps, strengths, and mastery levels
2. **Optimally matching** learners with teachers using the **Hungarian Algorithm**
3. **Generating adaptive questions** via **gemma4 (Ollama/LLM)** following **Bloom's Taxonomy**
4. **Tracking mastery** through pair and group sessions with performance scoring
5. **Promoting students** from Learner → Skilled Student → Certified Teacher

The system is designed for **Mentora Research Project** (Year 4, Semester 1) and implements an 11-phase learning pipeline with real-time collaboration via WebSockets.

---

## Repository Structure

```
peer_learning/
├── main.py                                    # FastAPI entry point
├── requirements.txt                           # Python dependencies
├── Dockerfile                                 # Container build
├── docker-compose.yml                         # Multi-service orchestration
├── .env / .env.example                        # Environment config
├── PeerLearning.postman_collection.json       # API test collection
│
├── app/
│   ├── __init__.py
│   │
│   ├── core/
│   │   ├── config.py                          # Pydantic Settings (env vars)
│   │   ├── database.py                        # MongoDB connection + indexes
│   │   ├── auth.py                            # JWT authentication middleware
│   │   ├── llm_client.py                      # Ollama (gemma4) client with retry
│   │   └── websocket_manager.py               # In-memory WS room/connection manager
│   │
│   ├── models/
│   │   └── models.py                          # All Pydantic models & enums
│   │
│   ├── services/
│   │   ├── import_service.py                  # Phase 1: Student data ingestion
│   │   ├── pairing_service.py                 # Phase 2: Hungarian algorithm matching
│   │   ├── session_service.py                 # Phase 3 & 4: Interactive pair sessions
│   │   ├── question_service.py                # Phase 3 & 9: LLM question generation
│   │   ├── pool_service.py                    # Phase 5 & 10: Improved/verified pools
│   │   ├── notification_service.py            # Phase 6: Notifications & WebSocket broadcasts
│   │   ├── group_service.py                   # Phase 7: Group sessions (3 students)
│   │   ├── verification_service.py            # Phase 10: Mastery verification
│   │   ├── performance_service.py             # Phase 11: Completion reports
│   │   └── live_room_service.py               # Real-time collaboration rooms
│   │
│   ├── api/
│   │   ├── __init__.py                        # Router aggregator
│   │   └── routes/
│   │       ├── students.py                    # Student CRUD + import
│   │       ├── sessions.py                    # Pair session + matching endpoints
│   │       ├── groups.py                      # Group session endpoints
│   │       ├── pools.py                       # Topic pool endpoints
│   │       ├── notifications.py               # Notification + waiting queue
│   │       ├── performance.py                 # Performance + question bank
│   │       ├── websockets.py                  # Real-time WS (chat, sandbox, voice)
│   │       └── live_room.py                   # Live room HTTP + WS endpoints
│   │
│   └── utils/
│       └── helpers.py                         # Scoring formulas, role rotation, ID gen
│
├── tests/
│   ├── __init__.py
│   └── test_flow.py                           # End-to-end test suite
│
└── logs/                                      # Runtime logs (app.log, server_out/err)
```

---

## 11-Phase Learning Pipeline

### Phase 1 — Data Ingestion (`import_service.py`)

- Accepts JSON payload of student profiles via `POST /api/students/import`
- Each student contains:
  - `mastery_profile.overall_mastery_score` (0-100)
  - `knowledge_gaps[]` — topics the student is weak in, with `gap_type` (FUNDAMENTAL_GAP / PARTIAL_GAP), `confidence`, and current `mastery_score`
  - `strengths[]` — topics the student is strong in, with `mastery_level` (beginner / proficient / advanced) and `can_teach_others` flag
- Gaps are sorted: **FUNDAMENTAL_GAP first** (by decreasing confidence), then PARTIAL_GAP
- The first gap becomes the student's `current_weak_topic`
- Students are upserted into the `students` MongoDB collection
- Also supports importing from a remote URL (for integration with the Knowledge Analyzed Agent)

### Phase 2 — Pair Formation (`pairing_service.py`)

Two matching modes:

#### A. Hungarian Algorithm Batch Matching (`run_full_pairing`)

Called via `POST /api/sessions/batch/all-topics` or `POST /api/sessions/pair/run`.

**Algorithm Steps:**

1. **Load all existing participants** — Retrieves all previously paired learners/teachers and group session members to avoid re-pairing
2. **Load waiting queue** — Students who were previously unmatched and are waiting
3. **Load new students** — Students not in any session or queue
4. **Topic scarcity sorting** (`_sort_topics_by_scarcity`) — Topics are ordered so scarce-teacher topics are processed FIRST
5. **Cost matrix construction** — For each topic, a cost matrix of size `max(learners, teachers) × max(learners, teachers)` is built:
   - Cost = `-compatibility_score` (the Hungarian algorithm minimizes cost, so negating the score means it maximizes compatibility)
   - Entries for nonexistent learner/teacher pairs are set to `1000` (effectively infinite cost = never selected)
6. **`scipy.optimize.linear_sum_assignment`** — The Hungarian algorithm is run on the cost matrix, producing optimal row (learner) and column (teacher) assignments
7. **Session creation** — Each matched pair creates a `pair_sessions` document with status SCHEDULED, scheduled start time, learner's initial mastery, and pairing type
8. **Student reservation** — Both students are marked `in_session` with `current_session_id`, preventing them from being matched for other topics
9. **Notifications** — Both learner and teacher receive pairing notifications with scheduled session time

**Compatibility Score Formula** (see `helpers.py`):

| Component | Weight | Description |
|---|---|---|
| Teacher Confidence | 25% | How confident the teacher is in this topic |
| Teacher Mastery Level | 25% | advanced=100, proficient=80, beginner=50 |
| Gap Severity | 20% | FUNDAMENTAL_GAP=100, PARTIAL_GAP=70 |
| Gap Magnitude | 15% | `100 - learner_mastery_score` — bigger gap = better match |
| Learner Inverse Confidence | 15% | `(1 - learner_confidence) * 100` — less confident learner needs more help |

**Score = sum of all weighted components, clamped to [0, 100]**

10. **Queue matching** (Step 2) — Remaining new students are matched against the waiting queue:
    - New students who can teach → queue learners (who need that topic)
    - New students who need a topic → queue students who can teach
    - Matched queue students are **immediately removed** from the waiting queue
11. **Auto-queue** (Step 3) — Unmatched new students are automatically added to the waiting queue with calculated priority scores
12. **Batch record** — A `batch_pairing_records` document is saved with full summary

#### B. Individual Student Matching (`match_student_and_create_session`)

Called via `POST /api/sessions/pair/match-me`.

- Finds the authenticated student's weakest topic
- Searches for available teachers using atomic `find_one_and_update` to **prevent race conditions** (two concurrent requests cannot claim the same teacher)
- If found: creates a pair session immediately
- If not found: adds student to waiting queue with priority

### Phase 3 — Interactive Pair Sessions (`session_service.py` + `question_service.py`)

**Session lifecycle:** SCHEDULED → ACTIVE (triggered when scheduled time passes or teacher accepts) → COMPLETED

#### Question Generation (`POST /api/sessions/{id}/start-question`)

- Uses `OllamaClient.generate_question()` in `llm_client.py` to call **gemma4** via Ollama API
- Questions follow **Bloom's Taxonomy** (6 levels):
  1. Remember — Recall facts, definitions, syntax
  2. Understand — Explain concepts, summarize, paraphrase
  3. Apply — Use concepts to solve problems, write code
  4. Analyze — Break down, find patterns, debug code
  5. Evaluate — Judge, critique, compare, optimize
  6. Create — Design, build, teach others
- The LLM prompt includes:
  - Topic name, Bloom level, current mastery score, specific misconception
  - A clause to **avoid repeating** the previously asked question
- The response is parsed as JSON with: `question_text`, `expected_answer`, `hints[3]`, `time_limit_seconds`
- If the LLM fails to generate valid JSON, a **fallback question** is used
- Questions are saved to `questions_bank` collection with analytics tracking

**Bloom Level Progression:**
- Advance: 2 consecutive correct answers → level +1
- Regress: 1 consecutive incorrect → level -1
- Levels stay within [1, 6]

#### Answer Submission (`POST /api/sessions/{id}/answer`)

- Uses LLM to evaluate the student's answer (`llm_client.evaluate_answer`)
- Returns: `is_correct`, `feedback`, `score_percentage`
- Updates learner's mastery score dynamically:
  - `base_change = +5.0 if correct, -3.0 if incorrect`
  - Multiplied by difficulty (bloom_level × 0.1), consistency (consecutive_correct/incorrect × 0.1), and time modifiers
- Records question analytics (success rate, average hints, average time)
- If a question's success rate < 40% after 5+ attempts → **flagged for review**

#### Hints (`POST /api/sessions/{id}/hint`)

- Maximum 3 hints per session
- Hints are drawn from the LLM-generated question's `hints[]` array

### Phase 4 — Performance & Completion (`session_service.py`)

Called via `POST /api/sessions/{id}/complete`.

**Learner Outcome:**
- ≥85% → **MASTERED** (enters Phase 5 improved pool)
- 50-84% → **CONTINUE** (can do more questions)
- <50% → **REGROUP** (needs a new teacher)

**Teacher Score:**
- Calculated as: `(final_mastery - initial_mastery) / (100 - initial_mastery) × 100`
- <50% → `NEEDS_IMPROVEMENT` (teacher's own gaps are marked for Phase 8)
- ≥50% → `OK`

**On completion:**
- Both students are released to `active` status
- Teacher's `can_teach_others` is set to `False` for this topic (prevents re-matching as teacher for same topic)
- Learner's knowledge gap is marked `completed: True`

### Phase 5 — Improved Pool (`pool_service.py`)

- Students who MASTERED a topic (≥85% in pair session) are added to the `improved_pools` collection
- The gap is removed from the student's knowledge_gaps list
- Overall mastery score is recalculated
- If the pool reaches **3+ students** for a given topic, it automatically triggers group session formation

### Phase 6 — Waiting Queue & Notifications (`notification_service.py` + `notifications.py`)

- When no teacher is available, students are added to the `waiting_queue` with a **priority score**:
  - `Priority = base(50 for FUNDAMENTAL, 25 for PARTIAL) + waiting_minutes + (attempts × 20)`
- Notifications are stored in the `notifications` collection and broadcast via WebSocket
- Notifications have types: `pairing_success`, `queue_entry`, `no_teachers_available`, `knowledge_gap_completed`
- Teacher accepts a notification → session is immediately activated

### Phase 7 — Group Sessions (`group_service.py`)

- **Trigger:** When ≥3 students are in the improved pool for a topic
- **Formation:** 3 students are randomly selected, sorted by mastery, and assigned roles:
  - Highest mastery → **EXPLAINER**
  - Middle → **SOLVER**
  - Lowest → **REVIEWER**
- **Activity types:** `coding`, `debugging`, `mini_project` (randomly selected)
- **LLM-generated problem:** via `llm_client.generate_group_problem()` with role-specific guides and starter code
- **Submission:** Each member submits task_completion, collaboration, and communication scores
  - `Role Score = task_completion × 50% + collaboration × 30% + communication × 20%`
- **Post-submission outcomes:**
  - Score ≥90% → increments consecutive counter (toward verification)
  - Score <50% → removed from pool, back to pair programming
  - Group average <70% → group disbanded
  - Group average ≥70% → **role rotation** (`rotate_group_roles`) and next session formed

**Role Rotation:**
- Session 1: member[0]=EXPLAINER, [1]=SOLVER, [2]=REVIEWER
- Session 2: member[1]=EXPLAINER, [2]=SOLVER, [0]=REVIEWER
- Session 3: member[2]=EXPLAINER, [0]=SOLVER, [1]=REVIEWER

### Phase 8 — Teacher Gap Resolution (`session_service.py`)

- When a teacher scores <50%, their teaching ability for the topic is disabled
- A knowledge gap is added back for the teacher (they now become a learner for that topic)
- If the teacher has other gaps and is not in a session, they become available for the pairing algorithm

### Phase 9 — Question Bank (`question_service.py`)

- All generated questions are persisted in `questions_bank` with:
  - Analytics: `success_rate`, `average_hints_used`, `average_time_taken`, `used_count`
  - `flagged_for_review` flag (auto-set when success rate < 40% after 5 uses)
- Accessible via `GET /api/questions/bank/{topic_id}`
- Manual generation/evaluation endpoints available

### Phase 10 — Verification (`verification_service.py`)

**Criteria (ALL must be met):**
1. **3 consecutive group sessions** with score ≥ 90%
2. **Demonstrated teaching ability** — at least one completed pair session as teacher with score ≥ 50
3. **No hints used** in the last 2 pair sessions
4. **Independent problem-solving** — at least one pair session with score ≥ 90%, 0 hints, 0 help requests

When all criteria are met:
- Student is moved to `verified_pools` (with `teaching_certified: True`)
- Removed from `improved_pools`
- `can_teach_others` is set to `True` for the topic
- If all topics are mastered → completion report is generated (Phase 11)

### Phase 11 — Completion (`performance_service.py`)

- Generated via `GET /api/performance/{student_id}/completion`
- Includes: initial vs final mastery, topics mastered, sessions completed, topics can teach, total time

---

## Grouping Algorithms — Detailed Analysis

### 1. Hungarian Algorithm (Optimal Matching) — `pairing_service.py:run_full_pairing`

**Purpose:** Find the globally optimal one-to-one pairing of learners to teachers within a topic.

**Implementation:**
```python
from scipy.optimize import linear_sum_assignment

size = max(n_learners, n_teachers)
cost_matrix = np.full((size, size), 1000.0)  # High cost = invalid match

for i, learner in enumerate(learners):
    for j, teacher in enumerate(teachers):
        score = calculate_compatibility_score(...)
        cost_matrix[i][j] = -score  # Negate to maximize compatibility

row_ind, col_ind = linear_sum_assignment(cost_matrix)
```

**Why Hungarian:**
- Guarantees globally optimal assignment (unlike greedy approaches)
- Handles imbalanced sets (pads with high-cost dummy entries)
- O(n³) complexity — acceptable for class-size groups (10-100 students)

### 2. Topic Scarcity Sorting — `pairing_service.py:_sort_topics_by_scarcity`

**Purpose:** Prioritize topics with fewer teachers per learner to maximize overall coverage.

**Algorithm:**
```python
ratio = n_teachers / max(n_learners, 1)
# Sort by ratio ascending, then by learner count descending
scored.sort(key=lambda x: (ratio, -n_learners))
```

This ensures scarce-teacher topics are processed first, reducing the chance that teachers are consumed by abundant-topic matches.

### 3. Queue Matching — `pairing_service.py:run_full_pairing` (Step 2)

**Purpose:** Match newly imported students with existing waiting queue students.

**Two sub-steps:**
- New teachers → queue learners (new student can teach, queue student needs)
- Queue teachers → new learners (queue student can teach, new student needs)

Students are removed from queue immediately upon match to prevent stale entries.

### 4. Waiting Queue Priority — `helpers.py:calculate_priority_score`

**Purpose:** Order students in the waiting queue so the most urgent cases are served first.

```python
priority = base(50 FUNDAMENTAL / 25 PARTIAL) + waiting_minutes + (attempts × 20)
```

### 5. Group Formation & Role Assignment — `group_service.py:form_group_session`

**Purpose:** Select 3 students from the improved pool and assign collaborative roles.

- Random selection from pool (all have mastered the topic in pair sessions)
- Sorted by mastery score for role assignment
- Roles assigned by `assign_initial_group_roles` (highest=EXPLAINER, middle=SOLVER, lowest=REVIEWER)
- Subsequent sessions use `rotate_group_roles` for equal experience

### 6. Dynamic Bloom Level Progression — `helpers.py:get_next_bloom_level`

**Purpose:** Adapt question difficulty based on learner performance.

```python
if consecutive_correct >= 2 and current < 6:
    return current + 1   # Level up
if consecutive_incorrect >= 1 and current > 1:
    return current - 1   # Level down
return current           # Stay
```

### 7. Dynamic Mastery Scoring — `helpers.py:calculate_updated_mastery_score`

**Purpose:** Continuously update learner's mastery after each answer.

```python
change = base_change(±5) × difficulty_multiplier(1 + bloom×0.1)
         × consistency_multiplier(1 + consecutive×0.1)
         × time_modifier(1.0-1.2)
```

---

## Real-Time Features (WebSockets)

### Connection Types:

| Endpoint | Purpose |
|---|---|
| `/ws/session/{session_id}` | Pair session: chat, sandbox sync, voice signaling |
| `/ws/group/{session_id}` | Group session: chat, sandbox, role actions |
| `/ws/notifications/{student_id}` | Live notification stream |
| `/ws/live/{session_id}` (via `live_room.py`) | Full live room with whiteboard, screen share, presence |

### Message Types:

- `chat` — Text messaging with DB persistence
- `sandbox_update` — Collaborative code editor sync
- `voice_signal` — WebRTC signaling (offer/answer/ICE)
- `typing` — Typing indicators
- `screen_share` — Screen sharing start/stop + WebRTC signals
- `whiteboard` / `whiteboard_clear` — Collaborative whiteboard
- `question_update` — Question status changes
- `session_action` — Session lifecycle events
- `presence` — Online status
- `hint_request` — Hint notifications
- `ping/pong` — Keepalive

### Connection Manager (`websocket_manager.py`):

- In-memory room-based connection tracking
- Auto-cleanup of dead connections on broadcast
- Targeted messaging to specific students within a room

---

## Data Models

### MongoDB Collections:

| Collection | Indexes | Purpose |
|---|---|---|
| `students` | `student_id` (unique), `current_session_id`, `status` | Student profiles, gaps, strengths |
| `pair_sessions` | `session_id` (unique), `teacher_id`, `learner_id`, `topic_id`, `status` | Pair programming sessions |
| `group_sessions` | `session_id` (unique), `topic_id`, `status` | 3-student collaborative sessions |
| `improved_pools` | `(topic_id, student_id)` (unique) | Students who mastered a topic |
| `verified_pools` | `(topic_id, student_id)` (unique) | Fully certified teachers |
| `waiting_queue` | `(topic_id, priority_score)`, `student_id` | Waiting students |
| `notifications` | `student_id`, `expires_at`, `status` | Notifications with 60s TTL |
| `questions_bank` | `question_id` (unique), `topic_id`, `bloom_level` | LLM-generated questions |
| `batch_pairing_records` | — | History of batch matching runs |

### Key Enums:

- `GapType`: FUNDAMENTAL_GAP, PARTIAL_GAP
- `MasteryLevel`: advanced, proficient, beginner
- `SessionStatus`: active, scheduled, completed, abandoned, waiting
- `PairingType`: RECIPROCAL, ONE_WAY
- `GroupRole`: EXPLAINER, SOLVER, REVIEWER
- `ActivityType`: coding, debugging, mini_project
- `StudentStatus`: active, in_session, complete

---

## Scoring Formulas

### Compatibility Score
```
= Teacher_Confidence × 100 × 0.25
+ MasteryLevel_to_Score(level) × 0.25
+ GapType_to_Score(type) × 0.20
+ (100 - Learner_Mastery) × 0.15
+ (1 - Learner_Confidence) × 100 × 0.15
```

### Learner Score
```
Base_Accuracy = (Correct / Total) × 100
Penalty = (Hints × 5) + (Help_Requests × 10)
Final = max(0, Base_Accuracy - Penalty)
```

### Teacher Score
```
Improvement = (Final_Mastery - Initial_Mastery) / (100 - Initial_Mastery)
Teacher_Score = clamp(Improvement × 100, 0, 100)
```

### Role Score (Group)
```
= Task_Completion × 0.50 + Collaboration × 0.30 + Communication × 0.20
```

### Waiting Queue Priority
```
= Base(50 FUNDAMENTAL / 25 PARTIAL) + Minutes_Waiting + (Attempts × 20)
```

---

## Technology Stack

| Component | Technology |
|---|---|
| **API Framework** | FastAPI (Python 3.11+) |
| **Database** | MongoDB 7.0 (via Motor async driver) |
| **LLM** | Ollama / gemma4 |
| **Matching Algorithm** | SciPy Hungarian (`linear_sum_assignment`) |
| **Math** | NumPy |
| **Authentication** | JWT (python-jose) |
| **Real-time** | WebSockets (via FastAPI + websockets library) |
| **Caching** | Redis (configured but not yet used) |
| **Notifications** | MongoDB + WebSocket push |
| **Logging** | Loguru (console + file rotation) |
| **Validation** | Pydantic v2 |
| **Containerization** | Docker + Docker Compose |
| **Testing** | pytest + httpx (end-to-end) |

---

## API Endpoints Summary

### Students (`/api/students`)
| Method | Path | Phase |
|---|---|---|
| POST | `/import` | 1 — Import JSON |
| GET | `/` | List all |
| GET | `/{id}` | Get by ID |
| GET | `/{id}/weaknesses` | Get knowledge gaps |
| GET | `/{id}/history` | Get session history |

### Sessions (`/api/sessions`)
| Method | Path | Phase |
|---|---|---|
| POST | `/pair/run` | 2 — Batch pair all |
| POST | `/pair/match-me` | 2 — Individual match |
| GET | `/pair/all` | List all sessions |
| GET | `/pair/waiting-queue` | 6 — Waiting queue |
| GET | `/pair/my-status` | Current user status |
| GET | `/all/active` | Active sessions |
| GET | `/{id}` | Session details |
| POST | `/{id}/start-question` | 3 — Generate question |
| POST | `/{id}/answer` | 3 — Submit answer |
| POST | `/{id}/hint` | 3 — Request hint |
| POST | `/{id}/complete` | 4 — Complete session |
| POST | `/my/start-question` | 3 — Auto-resolve session |
| POST | `/my/answer` | 3 — Auto-resolve answer |

### Groups (`/api/groups`)
| Method | Path | Phase |
|---|---|---|
| POST | `/form` | 7 — Form group |
| GET | `/{id}` | Group details |
| POST | `/{id}/submit` | 7 — Submit scores |

### Pools (`/api/pools`)
| Method | Path | Phase |
|---|---|---|
| GET | `/all` | 5 — All pools |
| GET | `/{topic_id}/students` | 5 — Pool members |
| POST | `/{topic_id}/create` | Create pool |

### Notifications (`/api`)
| Method | Path | Phase |
|---|---|---|
| GET | `/notifications` | 6 — List notifications |
| POST | `/notifications/{id}/accept` | 6 — Accept (join) |
| POST | `/notifications/{id}/read` | Mark read |
| POST | `/notifications/read-all` | Mark all read |

### Performance (`/api/performance`)
| Method | Path | Phase |
|---|---|---|
| GET | `/{student_id}` | Performance summary |
| GET | `/{student_id}/topic/{topic_id}` | Topic-level performance |
| GET | `/{student_id}/completion` | 11 — Completion report |

### Questions (`/api/questions`)
| Method | Path | Phase |
|---|---|---|
| POST | `/generate` | 3 — Manual generate |
| POST | `/evaluate` | 3 — Manual evaluate |
| GET | `/bank/{topic_id}` | 9 — Question bank |

### Live Room (`/api/live-room`)
| Method | Path | Phase |
|---|---|---|
| GET | `/{session_id}` | Get room |
| GET | `/{session_id}/ready` | Check readiness |
| POST | `/{session_id}/join` | Join room |
| POST | `/{session_id}/leave` | Leave room |
| POST | `/{session_id}/close` | Close room |
| GET | `/{session_id}/screen-share` | Screen share state |
| GET | `/{session_id}/members` | Room members |
| POST | `/my/room` | Auto room for user |

---

## Development Setup

### Prerequisites

- Python 3.11+
- MongoDB 7.0+
- Redis 7+ (optional, for future caching)
- Ollama with gemma4:latest pulled

### Local Setup

```powershell
# Clone and setup
cd services/peer-learning
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Configure
copy .env.example .env

# Ensure MongoDB is running locally
# Ensure Ollama is running with gemma4 pulled
ollama pull gemma4:latest

# Start
mkdir -p logs
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Docker Setup

```powershell
copy .env.example .env
docker-compose up -d
# Wait ~2-3 minutes for Ollama to pull gemma4 on first run
docker-compose logs -f ollama
```

### Running Tests

```powershell
# Ensure server is running first
python tests/test_flow.py
# Or against a different URL
python tests/test_flow.py --base-url http://your-server:8000
```

The test suite (`test_flow.py`) exercises the full pipeline:
1. Health check → 2. Import 4 students → 3. Preview match → 4. Batch pair → 5. List active sessions → 6. Generate question → 7. Request hint → 8. Submit answer → 9. Complete session → 10. Check pools → 11. Waiting queue → 12. Performance report → 13. Question bank → 14. Group session attempt

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `MONGODB_URL` | `mongodb://localhost:27017` | MongoDB connection |
| `MONGODB_DB_NAME` | `peer_learning` | Database name |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server |
| `OLLAMA_MODEL` | `gemma4:latest` | LLM model |
| `OLLAMA_TIMEOUT` | `120` | LLM timeout (seconds) |
| `REDIS_URL` | `redis://localhost:6379` | Redis connection |
| `NOTIFICATION_TTL_SECONDS` | `60` | Notification expiry |
| `COMPATIBILITY_THRESHOLD` | `60` | Min queue match score |
| `MASTERY_THRESHOLD` | `90` | Min score for pool entry |
| `IMPROVED_POOL_GROUP_TRIGGER` | `3` | Pool size → group trigger |
| `VERIFICATION_CONSECUTIVE_SESSIONS` | `3` | Group sessions for verification |
| `APP_SECRET_KEY` | — | Flask-style secret |
| `JWT_SECRET_KEY` | — | JWT signing key |
| `APP_DEBUG` | `false` | Debug mode |

---

## Known Limitations & Future Work

- **Reciprocal pairing** is modeled in the enum `PairingType.RECIPROCAL` but not fully implemented in the matching logic (student A teaches topic X to B while B teaches topic Y to A)
- **Redis** is configured but not yet used (intended for WebSocket pub/sub across multiple app instances and distributed rate limiting)
- **Background matching loop** (`start_background_matching`) is stubbed out in `main.py` — currently matching is only triggered via API calls
- `_check_no_hints` in `group_service.py` is a placeholder (always returns `True`)
- The live room state is in-memory only (not persisted to MongoDB) — will be lost on server restart
- No pagination on list endpoints
- No WebSocket authentication middleware (token validation is done per-connection via query param)
