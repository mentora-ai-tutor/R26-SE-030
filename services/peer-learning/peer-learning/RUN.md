# 🚀 Peer Learning Agent — Run Guide

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | ≥ 3.11 | Uses `list[dict]` syntax |
| MongoDB | ≥ 6.0 | Running locally on port `27017` |
| Ollama | Latest | Running locally on port `11434` with `llama3` model |

---

## 1. Clone / Navigate to the Project

```bash
cd services/peer-learning/backend
```

---

## 2. Create & Activate a Virtual Environment (Recommended)

```bash
python3 -m venv venv
source venv/bin/activate        # macOS / Linux
# venv\Scripts\activate         # Windows
```

---

## 3. Install Dependencies

```bash
pip install fastapi motor uvicorn python-dotenv httpx
```

---

## 4. Configure Environment Variables

Edit `backend/.env`:

```env
MONGODB_URL=mongodb://localhost:27017
DATABASE_NAME=peer_learning
OLLAMA_BASE_URL=http://localhost:11434
SECRET_KEY=your-secret-key-here
```

---

## 5. Start MongoDB

```bash
# macOS (Homebrew)
brew services start mongodb-community

# Or run directly
mongod --dbpath /usr/local/var/mongodb
```

---

## 6. Start Ollama + Pull the Model

```bash
# Start Ollama service
ollama serve

# Pull llama3 model (first-time only)
ollama pull llama3
```

---

## 7. Run the FastAPI Server

### Development (with hot-reload)

```bash
cd "/Volumes/My Data/SLIIT/Research/Project/mentora-backend/services/peer-learning/backend"
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Production

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

---

## 8. Verify the Server is Running

```bash
curl http://localhost:8000/
# Expected: {"status": "Peer Learning Agent running"}
```

---

## 9. Access API Documentation

| Interface | URL |
|---|---|
| Swagger UI (Interactive) | http://localhost:8000/docs |
| ReDoc | http://localhost:8000/redoc |
| OpenAPI JSON | http://localhost:8000/openapi.json |

---

## API Endpoints Summary

### Health Check
| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Health check — returns running status |

### Students (`/api/students`)
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/students/import` | Import student profiles from Knowledge Analysis Agent |
| `GET` | `/api/students/{student_id}/status` | Get a student's current status |

### Sessions (WebSocket)
| Protocol | Endpoint | Description |
|---|---|---|
| `WebSocket` | `/ws/pair/{session_id}/{student_id}` | Join an active pair learning session |

---

## WebSocket Message Protocol

### Learner Messages (client → server)
| Type | Payload | Description |
|---|---|---|
| `SUBMIT_ANSWER` | `{ "type": "SUBMIT_ANSWER", "answer": "..." }` | Submit an answer to the current question |
| `REQUEST_HINT` | `{ "type": "REQUEST_HINT" }` | Request a hint (up to 3 levels) |
| `ASK_TEACHER` | `{ "type": "ASK_TEACHER" }` | Signal the teacher for help |

### Teacher Messages (client → server)
| Type | Payload | Description |
|---|---|---|
| `TEACHER_DONE_EXPLAINING` | `{ "type": "TEACHER_DONE_EXPLAINING" }` | Signal that teaching is done |

### Server Messages (server → client)
| Type | Description |
|---|---|
| `NEW_QUESTION` | New question sent to learner |
| `ANSWER_CORRECT` | Correct answer feedback |
| `ANSWER_WRONG` | Wrong answer feedback |
| `HINT` | Hint response |
| `NO_MORE_HINTS` | All hints exhausted |
| `TEACHER_NOTIFIED` | Teacher has been alerted |
| `TIME_EXPIRED` | 120s timer expired |
| `SESSION_COMPLETE` | Session finished with score & decision |
| `TEACHER_STANDBY` | Teacher connected and waiting |
| `LEARNER_NEEDS_HELP` | Pushed to teacher when learner asks for help |

---

## MongoDB Collections

| Collection | Description |
|---|---|
| `students` | Student profiles with strengths, weaknesses, roles |
| `pair_sessions` | Active and completed pair learning sessions |
| `group_sessions` | Group sessions (coding/debugging/mini_project) |
| `topic_pools` | Students in `improved` or `verified` topic pools |

---

## Troubleshooting

| Error | Fix |
|---|---|
| `Connection refused :27017` | Start MongoDB: `brew services start mongodb-community` |
| `Connection refused :11434` | Start Ollama: `ollama serve` |
| `ModuleNotFoundError` | Run `pip install fastapi motor uvicorn python-dotenv httpx` |
| WebSocket disconnects immediately | Ensure `session_id` exists in DB before connecting |
