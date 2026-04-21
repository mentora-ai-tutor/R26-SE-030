from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from app.services.pairing_service import (
    run_full_pairing,
    get_all_paired_sessions,
    get_waiting_queue_students,
    batch_match_all_topics,
)
from app.services.session_service import (
    get_session,
    get_all_active_sessions,
    start_session_question,
    submit_answer,
    request_hint,
    ask_teacher,
    complete_session,
)

router = APIRouter(prefix="/api/sessions", tags=["Sessions"])


class AnswerBody(BaseModel):
    answer: str
    time_taken_seconds: Optional[int] = None


class HintBody(BaseModel):
    question_id: str


class TeacherHelpBody(BaseModel):
    message: str
    sandbox_code: Optional[str] = None


# ─── Pairing endpoints ────────────────────────────────────────────────────────

@router.post("/pair/run", summary="Auto-pair ALL students across ALL topics")
async def run_pairing() -> Dict[str, Any]:
    """
    Runs the full system-wide pairing algorithm in one call.

    What happens internally
    -----------------------
    1. Every free student is loaded (not in a session, not complete).
    2. For every topic that has at least one learner:
         - Identifies learners (students who have a knowledge gap for that topic).
         - Identifies teachers (students who have can_teach_others=True for that topic
           and are NOT also learners for the same topic).
         - Runs the Hungarian algorithm to find the optimal one-to-one matching.
         - Detects RECIPROCAL pairs (student A teaches topic X to B, B teaches topic Y to A).
         - Creates and saves all sessions to the pair_sessions collection immediately.
         - Reserves both students so they are not matched again in another topic.
    3. Any student left unmatched after all topics are processed is automatically
       saved to the waiting_queue collection.
    4. Saves a batch_pairing_record with the full summary.

    Returns
    -------
    - sessions_created   : total sessions saved to DB
    - students_paired    : number of students now in sessions
    - students_queued    : number of students saved to waiting queue
    - paired             : list of pairing details (learner, teacher, topic, session_id)
    - sessions           : full session objects
    - waiting_queue      : list of waiting queue entries that were created/updated
    """
    return await run_full_pairing()


@router.get("/pair/all", summary="Get all pair sessions (full details)")
async def list_all_paired() -> List[Dict]:
    """
    Returns every pair session saved in the DB — active, completed, and abandoned —
    sorted newest first.
    """
    return await get_all_paired_sessions()


@router.get("/pair/waiting-queue", summary="Get all students in the waiting queue")
async def list_waiting_queue() -> List[Dict]:
    """
    Returns all students currently waiting for a teacher, sorted by priority score
    (highest first). Priority = gap severity + waiting time + retry attempts.
    """
    return await get_waiting_queue_students()


# ─── Active / session detail endpoints ───────────────────────────────────────

@router.get("/all/active", summary="Get all currently active sessions")
async def list_active() -> List[Dict]:
    return await get_all_active_sessions()


@router.get("/{session_id}", summary="Get session details by ID")
async def get_session_endpoint(session_id: str) -> Dict:
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


# ─── In-session interaction endpoints ────────────────────────────────────────

@router.post("/{session_id}/start-question", summary="Generate next Bloom question for session")
async def start_question(session_id: str) -> Dict:
    question = await start_session_question(session_id)
    if not question:
        raise HTTPException(status_code=400, detail="Could not generate question")
    return question


@router.post("/{session_id}/answer", summary="Submit answer to current question")
async def answer_question(session_id: str, body: AnswerBody) -> Dict[str, Any]:
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return await submit_answer(session_id, body.answer, body.time_taken_seconds)


@router.post("/{session_id}/hint", summary="Request a hint for current question")
async def get_hint_endpoint(session_id: str, body: HintBody) -> Dict[str, Any]:
    return await request_hint(session_id, body.question_id)


@router.post("/{session_id}/ask-teacher", summary="Ask teacher for help")
async def ask_teacher_endpoint(session_id: str, body: TeacherHelpBody) -> Dict[str, Any]:
    return await ask_teacher(session_id, body.message, body.sandbox_code)


@router.post("/{session_id}/complete", summary="Complete a session and calculate scores")
async def complete_session_endpoint(session_id: str) -> Dict[str, Any]:
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return await complete_session(session_id)