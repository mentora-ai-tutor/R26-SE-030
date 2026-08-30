# Java Multi-Agent Pedagogy Platform

A FastAPI backend for personalized Java learning. The platform combines mastery-analysis import, diagnostic coding tasks, Java syntax compilation, AI grading, targeted learning content, peer matching, collaborative rooms, real-time code synchronization, and moderated peer discussion.

## Features

- JWT-authenticated student workflows
- Student mastery-analysis import and retrieval
- Seven-task sequential Java diagnostic assessment
- Native `javac` validation when a JDK is installed
- Strict structural validation fallback when `javac` is unavailable
- OpenAI-powered coding-task generation and grading with local fallbacks
- Targeted RAG/content recommendations
- Peer matching based on strengths and knowledge gaps
- MongoDB persistence for students, analyses, sessions, assessments, rooms, notifications, and chat summaries
- Collaborative WebSocket code editing
- Learner and Peer Teacher task-progress synchronization
- Live named learner/Peer Teacher cursors with presence cleanup
- Shared collaborative whiteboard with drawing and text annotations
- WebSocket reconnect/refresh state restoration

## Architecture

```text
Client
  |
  +-- REST API ------------------------------+
  |                                           |
  |   Student / Assessment / Content / Peer   |
  |   Collaboration / Chat                   |
  |                                           v
  +-- WebSockets                       FastAPI application
                                              |
                    +-------------------------+-------------------------+
                    |                         |                         |
                 MongoDB                 OpenAI / LangChain          ChromaDB
              persistent state          task generation, grading       RAG data
                    |
             javac subprocess
             Java syntax checks
```

### Registered application modules

The application registers these routers in `app/main.py`:

- `app/api/student_routes.py`
- `app/api/assessment_routes.py`
- `app/api/content_routes.py`
- `app/api/peer_routes.py`
- `app/api/chat_routes.py`
- `app/api/collab_routes.py`

`app/api/agent_routes.py`, `app/api/rag_routes.py`, and `app/api/websocket_routes.py` contain additional/legacy implementations but are not registered by the current `app/main.py`.

## Requirements

- Python 3.11+
- MongoDB 5+ or a compatible MongoDB deployment
- JDK/JRE with `javac` recommended for real Java compilation checks
- OpenAI API key recommended for dynamic generation and grading
- Docker and Docker Compose are optional

## Installation

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

On macOS/Linux:

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Environment configuration

Create a `.env` file in the project root:

```dotenv
OPENAI_API_KEY=sk-your-key
MONGODB_URL=mongodb://localhost:27017
DATABASE_NAME=java_learning_db
USER_SERVICE_JWT_SECRET=replace-with-the-user-service-secret
USER_SERVICE_JWT_ALGORITHM=HS256
```

Supported JWT fallback variable names are `JWT_SECRET` and `JWT_SECRET_KEY`. The default secret is intended only for local development and must be replaced.

The JWT must contain one of these student identifier claims:

- `sub`
- `student_id`
- `studentId`
- `user_id`
- `id`
- `userId`

Every protected REST request uses:

```http
Authorization: Bearer <jwt-token>
```

WebSocket clients pass the token as a query parameter:

```text
?token=<jwt-token>
```

## Run locally

Start MongoDB, then run the API from the repository root:

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The API is available at:

- Health check: `http://127.0.0.1:8000/`
- Swagger UI: `http://127.0.0.1:8000/docs`
- OpenAPI JSON: `http://127.0.0.1:8000/openapi.json`

If port 8000 is occupied:

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
```

## Docker

The supplied Docker configuration runs the backend on port 8000 and reads environment variables from `.env`:

```powershell
docker compose up --build
```

The current `docker-compose.yml` assumes MongoDB is reachable using the `MONGODB_URL` in `.env`; it does not create a MongoDB container automatically.

Stop the service:

```powershell
docker compose down
```

## Core workflow: mastery analysis to diagnostic tasks

The diagnostic workflow is JWT-authenticated and requires a mastery analysis with at least one knowledge gap and weak subskill.

### 1. Import the mastery analysis

```http
POST /api/student/import-analysis
Authorization: Bearer <jwt-token>
Content-Type: application/json
```

Example body:

```json
{
  "student_id": "STU_1787332282984_4874",
  "mastery_profile": {
    "overall_mastery_score": 42,
    "knowledge_gaps": [
      {
        "topic": "Java Exception Handling",
        "topic_id": "JAVA-EXCEPTIONS",
        "gap_type": "weak_subskill",
        "confidence": 0.92,
        "mastery_score": 42,
        "weak_subskills": [
          {
            "subskill": "Try-Catch-Finally",
            "subskill_id": "JAVA-EXCEPTIONS-TCF",
            "status": "weak"
          }
        ],
        "misconceptions": []
      }
    ],
    "strengths": []
  },
  "recommendations": {}
}
```

The JWT student ID must match `student_id` in the body.

### 2. Start or resume the diagnostic session

```http
POST /api/student/onboard-and-diagnose
Authorization: Bearer <jwt-token>
```

The first request generates and stores seven tasks, but returns only Task 1. The seven task types are always intended to be ordered as follows:

1. `write_code`
2. `complete_missing_code`
3. `fix_incorrect_code`
4. `debug_error`
5. `predict_and_correct_behavior`
6. `implement_method`
7. `improve_solution`

Subsequent calls return the currently unlocked task. A completed session returns `status: "session_complete"` with the performance summary.

### 3. Submit the current Java code

```http
POST /api/assessment/evaluate
Authorization: Bearer <jwt-token>
Content-Type: application/json
```

```json
{
  "code": "public class Main { public static void main(String[] args) { System.out.println(\"Hello\"); } }"
}
```

The backend performs:

1. Empty-code validation
2. Class-structure validation
3. `javac` compilation when available, otherwise fallback structural checks
4. AI task grading against the stored task description and criteria
5. Persistent result storage

A task passes only when both syntax validation and AI grading pass.

### Sequential progression rules

- Task 1 is available when the session starts.
- Tasks 2 through 7 are locked until their predecessor passes.
- A failed submission increments `attempts` and keeps the same task active.
- Failed responses return feedback and a non-solution hint; they do not reveal a complete solution.
- A passing submission marks the task completed and unlocks only the next task.
- Task 7 passing changes the sequence status to `completed`.
- Calling `/api/student/onboard-and-diagnose` after completion returns the stored summary instead of creating a second session.
- The reset endpoint is available when a new diagnostic attempt is explicitly required.

Expected client sequence:

```text
1. POST /api/student/onboard-and-diagnose  -> Task 1
2. POST /api/assessment/evaluate           -> Evaluate Task 1
3. POST /api/student/onboard-and-diagnose  -> Task 2, only if Task 1 passed
4. POST /api/assessment/evaluate           -> Evaluate Task 2
5. Repeat the pair through Task 7
6. POST /api/student/onboard-and-diagnose  -> Session summary
```

### Diagnostic session support endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/student/diagnostic-session/reset` | Delete the student's existing diagnostic session |
| `GET` | `/api/student/diagnostic-session/status` | Inspect session state, task index, and result count |
| `GET` | `/api/student/analysis/{student_id}` | Retrieve the authenticated student's latest analysis |

## Collaborative peer-learning workflow

Peer learning creates a collaborative room containing seven coding tasks generated for the learner's gap. The room stores the code, participants, task sequence, attempts, pass state, and task-progress list in MongoDB.

### 1. Find a peer

```http
POST /api/peer/match
Authorization: Bearer <jwt-token>
```

The service searches saved students and imported analyses for a complementary strength/gap match. On success it creates a room ID and notifications for both participants.

### 2. Initialize or join the room

```http
POST /api/collab/initialize-session?room_id=<room-id>&topic_id=<topic-id>
Authorization: Bearer <jwt-token>
```

The peer-match flow initializes the room automatically. The endpoint is also useful for explicit room setup.

### 3. Connect both participants to the collaboration WebSocket

```text
ws://127.0.0.1:8000/api/collab/ws/collab/<room-id>?token=<jwt-token>
```

Each connection receives an `INIT_STATE` message containing:

- Current code
- Active user count
- Current task and zero-based task index
- Total task count
- Session status
- Current attempts and pass state
- `task_progress` for every task
- Only the currently available task content, not future locked task content
- `sequence_complete`

The state is read from MongoDB, so refresh/reconnect restores the same progress.

### Collaboration WebSocket messages

Client to server:

```json
{"type":"CODE_CHANGE","code":"public class Main {}"}
```

```json
{"type":"CURSOR_MOVE","position":{"line":3,"column":10}}
```

```json
{"type":"CHAT_MESSAGE","message":"Can you review the catch block?"}
```

Cursor presence uses the same room socket. Send the editor or workspace position
as a `CURSOR_MOVE`; the server adds the authenticated participant name, role, and
stable indicator color before relaying it to the other participant:

```json
{
  "type": "CURSOR_MOVE",
  "position": {"x": 420, "y": 180, "editor_line": 12, "editor_column": 8}
}
```

The relayed event includes `student_id`, `name`, `role`, `color`, and `position`.
The server sends `PRESENCE_JOINED` and `PRESENCE_LEFT` events so clients can add
or remove named cursor indicators immediately.

Whiteboard operations use the same socket and room. The client renders each
operation according to its `kind` (`freehand`, `arrow`, `line`, `rectangle`,
`circle`, or `text`):

```json
{
  "type": "WHITEBOARD_DRAW",
  "color": "#111827",
  "operation": {
    "id": "draw-001",
    "kind": "arrow",
    "points": [{"x": 100, "y": 120}, {"x": 260, "y": 180}]
  }
}
```

Use `WHITEBOARD_ERASE` with an `operation_id` to remove one operation, or
`WHITEBOARD_CLEAR` to clear the shared canvas. Drawing is an independent overlay;
when the client drawing mode is disabled, normal editor typing and `CODE_CHANGE`
behavior are unchanged. Whiteboard operations are stored in `collab_rooms.whiteboard`
and included in `INIT_STATE` after reconnect.

`NEXT_TASK` and `PREV_TASK` are rejected with `TASK_LOCKED`. Clients cannot skip tasks or move backward through the sequence. The assessment endpoint is the only progression authority.

Server broadcasts include:

```json
{
  "type": "TASK_PROGRESS",
  "current_task": 2,
  "current_task_index": 1,
  "total_tasks": 7,
  "status": "in_progress",
  "attempts": 0,
  "passed": false,
  "task_progress": [],
  "sequence_complete": false
}
```

Progress broadcasts are sent to every connected room client, including the learner and Peer Teacher. When a task passes, the next starter code is loaded into the room state.

### Collaborative room REST endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/collab/rooms` | List active in-memory rooms |
| `GET` | `/api/collab/rooms/{room_id}/state` | Read active room code |
| `POST` | `/api/collab/initialize-session` | Initialize a room |

## Discussion moderator workflow

The discussion WebSocket is separate from the collaborative code WebSocket:

```text
ws://127.0.0.1:8000/api/chat/ws/<room-id>/<student-id>?token=<jwt-token>
```

Messages are broadcast to the room and analyzed for Java relevance by the discussion moderator. Summarize a discussion with:

```http
POST /api/chat/summarize-session?room_id=<room-id>
Authorization: Bearer <jwt-token>
```

The summary is stored in MongoDB.

## Learning content workflow

Generate content from the student's latest imported analysis:

```http
POST /api/content/recommend
Authorization: Bearer <jwt-token>
```

The live registered endpoint derives the first knowledge gap and weak subskill from the authenticated student's analysis, saves the recommendation, and returns a targeted learning resource.

If `OPENAI_API_KEY` is absent, the application uses local fallback responses for the OpenAI-backed student task functions. The registered content route currently returns deterministic recommendation content.

## Peer notifications

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/peer/notifications` | List notifications; supports `status=unread`, `read`, or `all` |
| `POST` | `/api/peer/notifications/{notification_id}/read` | Mark one notification read |
| `POST` | `/api/peer/notifications/read-all` | Mark all notifications read |
| `POST` | `/api/peer/notifications/{notification_id}/unread` | Mark one notification unread |

## Java assessment behavior

`AssessmentAgent` in `app/agents/assessment_agent.py` checks whether `javac` is available at startup.

With `javac`:

- The submitted code is written to a temporary file.
- The filename is derived from the first class declaration.
- `javac` compiles the file with a ten-second timeout.
- Compiler diagnostics are returned in the evaluation errors.

Without `javac`:

- Brackets are checked.
- A main method shape is checked.
- Basic missing-semicolon patterns are checked.

The current complexity estimate is heuristic: no loops returns `O(1)`, one loop returns `O(n)`, and multiple detected `for`/`while` loops return `O(n^k)`.

## MongoDB collections

The application initializes/indexes these collections when MongoDB is reachable:

- `students`
- `student_analyses`
- `quiz_evaluations`
- `diagnostic_sessions`
- `assessments`
- `content_recommendations`
- `peer_matches`
- `peer_notifications`
- `chat_sessions`
- `collab_rooms`
- `knowledge_chunks`

Important persisted collaboration fields include:

```text
coding_tasks
current_task_index
current_task
status
attempts
passed
task_progress
results
learner_student_id
peer_student_id
updated_at
```

## Project structure

```text
app/
  main.py                    FastAPI app and registered routers
  config.py                  Environment-backed settings
  agents/
    assessment_agent.py     Java syntax/compilation assessment
    student_agent.py        Task generation and AI grading
    peer_matching.py        Peer matching agent
    knowledge_rag.py        RAG support
    graph_workflow.py       Agent workflow support
    moderator_agent.py      Moderator support
  api/
    student_routes.py       Analysis import and diagnostic sessions
    assessment_routes.py    Java evaluation and task progression
    content_routes.py       Registered content recommendations
    peer_routes.py          Peer matching and notifications
    collab_routes.py        Collaborative rooms and code WebSocket
    chat_routes.py          Discussion WebSocket and summaries
  models/
    schemas.py              Pydantic request/response models
    db_models.py            Database model definitions
  services/
    mongodb.py              MongoDB client and persistence helpers
    quiz_generator.py       Quiz prompt and fallback generation
  rag/
    document_loader.py      RAG document loading
    vector_store.py         Chroma vector-store integration
    data/                    RAG source data
  tests/                     Pytest tests
  postman/                   Postman collection
```

## Testing

Run the full suite:

```powershell
python -m pytest -q
```

Compile the application modules:

```powershell
python -m py_compile app/main.py app/api/*.py app/agents/*.py app/services/*.py
```

The current legacy tests in `tests/test_agents.py` call JWT-protected endpoints without authorization headers and may return `401`. For endpoint tests, provide a valid JWT or override the authentication dependency in the test fixture.

## Postman

Import:

```text
postman/java-multiagent-platform.postman_collection.json
```

Set a `baseUrl` variable such as:

```text
http://127.0.0.1:8000
```

Protected requests must include a valid Bearer token. The diagnostic evaluator accepts only the current request body shape:

```json
{"code":"<java source>"}
```

## Troubleshooting

### MongoDB connection warnings

Check `MONGODB_URL`, ensure MongoDB is running, and verify that the configured database is reachable. The FastAPI process can start while MongoDB initialization reports a warning, but persistence-backed workflows will fail until MongoDB is available.

### `401 Missing or invalid Authorization header`

Add:

```http
Authorization: Bearer <jwt-token>
```

Confirm the token is signed with the same secret and algorithm configured by `USER_SERVICE_JWT_SECRET` and `USER_SERVICE_JWT_ALGORITHM`.

### `404 No imported analysis found`

Call `/api/student/import-analysis` first using a body whose `student_id` matches the JWT identity.

### Tasks do not advance

A task advances only when both `evaluation.is_valid` is true and the AI grader returns `grade: "pass"`. Inspect `/api/student/diagnostic-session/status` or the collaborative room's `task_progress` field.

### `javac` is unavailable

Install a JDK and ensure `javac` is on `PATH`. Without it, the backend uses fallback structural validation and cannot guarantee full Java compilation correctness.

## Security notes

- Never use the default JWT secret outside local development.
- Keep `.env` and API keys out of source control.
- Restrict CORS origins before production deployment; the current configuration allows all origins for local development.
- Java compilation currently validates source but does not execute untrusted student programs. Add sandboxed execution before running submitted code in production.
- Protect MongoDB with authentication, network restrictions, and appropriate backups.

## License

No license file is currently included in this repository.
