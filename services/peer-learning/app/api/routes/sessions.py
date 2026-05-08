from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
from app.core.auth import TokenPayload, get_current_user
from app.services.pairing_service import (
    run_full_pairing,
    get_all_paired_sessions,
    get_waiting_queue_students,
    batch_match_all_topics,
    get_student_pairing_status,
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

@router.get("/pair/my-status", summary="Get current user's pairing status")
async def my_pairing_status(current_user: TokenPayload = Depends(get_current_user)) -> Dict[str, Any]:
    """
    Returns the pairing status of the authenticated user.
    Possible statuses:
    - 'in_pair_session': User is in an active pair session (as learner or teacher)
    - 'in_group_session': User is in an active group session
    - 'waiting': User is in the waiting queue for one or more topics
    - 'idle': User is not in any session or queue
    """
    return await get_student_pairing_status(current_user.student_id)


@router.post("/pair/run", summary="Auto-pair ALL students across ALL topics")
async def run_pairing(current_user: TokenPayload = Depends(get_current_user)) -> Dict[str, Any]:
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
async def list_all_paired(current_user: TokenPayload = Depends(get_current_user)) -> List[Dict]:
    """
    Returns every pair session saved in the DB — active, completed, and abandoned —
    sorted newest first.
    """
    return await get_all_paired_sessions()


@router.get("/pair/waiting-queue", summary="Get all students in the waiting queue")
async def list_waiting_queue(current_user: TokenPayload = Depends(get_current_user)) -> List[Dict]:
    """
    Returns all students currently waiting for a teacher, sorted by priority score
    (highest first). Priority = gap severity + waiting time + retry attempts.
    """
    return await get_waiting_queue_students()


# ─── Active / session detail endpoints ───────────────────────────────────────

@router.get("/all/active", summary="Get all currently active sessions")
async def list_active(current_user: TokenPayload = Depends(get_current_user)) -> List[Dict]:
    return await get_all_active_sessions()


@router.get("/{session_id}", summary="Get session details by ID")
async def get_session_endpoint(
    session_id: str,
    current_user: TokenPayload = Depends(get_current_user),
) -> Dict:
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


# ─── In-session interaction endpoints ────────────────────────────────────────

@router.post("/{session_id}/start-question", summary="Generate next Bloom question for session")
async def start_question(
    session_id: str,
    current_user: TokenPayload = Depends(get_current_user),
) -> Dict:
    question = await start_session_question(session_id)
    if not question:
        raise HTTPException(status_code=400, detail="Could not generate question")
    return question


@router.post("/{session_id}/answer", summary="Submit answer to current question")
async def answer_question(
    session_id: str,
    body: AnswerBody,
    current_user: TokenPayload = Depends(get_current_user),
) -> Dict[str, Any]:
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return await submit_answer(session_id, body.answer, body.time_taken_seconds)


@router.post("/{session_id}/hint", summary="Request a hint for current question")
async def get_hint_endpoint(
    session_id: str,
    body: HintBody,
    current_user: TokenPayload = Depends(get_current_user),
) -> Dict[str, Any]:
    return await request_hint(session_id, body.question_id)


@router.post("/{session_id}/ask-teacher", summary="Ask teacher for help")
async def ask_teacher_endpoint(
    session_id: str,
    body: TeacherHelpBody,
    current_user: TokenPayload = Depends(get_current_user),
) -> Dict[str, Any]:
    return await ask_teacher(session_id, body.message, body.sandbox_code)


@router.post("/{session_id}/complete", summary="Complete a session and calculate scores")
async def complete_session_endpoint(
    session_id: str,
    current_user: TokenPayload = Depends(get_current_user),
) -> Dict[str, Any]:
    session = await get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return await complete_session(session_id)