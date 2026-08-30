import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from app.config import settings
from app.services.mongodb import (
    get_collection,
    save_student,
    save_student_analysis,
)

# Import Diagnostic AI Agent functions from student_agent.py
from app.agents.student_agent import (
    generate_all_diagnostic_coding_tasks,
    grade_coding_submission,
)

router = APIRouter(prefix="/api/student", tags=["Student Onboarding & Profile"])


# --- Pydantic Schemas (Pydantic V2 Compatible) ---
class StudentOnboardRequest(BaseModel):
    student_id: Optional[str] = Field(
        default=None,
        json_schema_extra={"example": "STU_2026005"},
        description="Unique Student ID",
    )
    name: str = Field(..., json_schema_extra={"example": "Kasun Perera"})
    current_knowledge_level: str = Field(
        ...,
        json_schema_extra={"example": "Intermediate"},
        description="Beginner, Intermediate, Advanced",
    )
    weak_subskills: List[dict] = Field(
        default=[
            {
                "topic_id": "TOPIC_JAVA_OOP_001",
                "topic": "Java OOP Concepts",
                "weak_subskill": "Polymorphism",
            },
            {
                "topic_id": "TOPIC_DS_002",
                "topic": "Data Structures",
                "weak_subskill": "Binary Search Trees",
            },
        ],
        json_schema_extra={
            "example": [
                {
                    "topic_id": "TOPIC_JAVA_OOP_001",
                    "topic": "Java OOP Concepts",
                    "weak_subskill": "Polymorphism",
                },
                {
                    "topic_id": "TOPIC_DS_002",
                    "topic": "Data Structures",
                    "weak_subskill": "Binary Search Trees",
                },
            ]
        },
    )


# --- JWT Authentication Dependency ---


def verify_jwt_student(
    authorization: Optional[str] = Header(default=None),
) -> str:
    """Verifies the login JWT Bearer token and returns the student identifier."""
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Authorization header. Expected 'Bearer <jwt>'.",
        )

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Authorization header. Expected 'Bearer <jwt>'.",
        )
    return decode_student_token(token)


def decode_student_token(token: str) -> str:
    """Verify a raw JWT, used by WebSocket handshakes without HTTP dependencies."""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            options={"verify_exp": True},
            algorithms=[settings.JWT_ALGORITHM],
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="JWT token has expired.")
    except jwt.InvalidSignatureError:
        raise HTTPException(
            status_code=401,
            detail=(
                "JWT signature verification failed. Configure this API with "
                "the same USER_SERVICE_JWT_SECRET used by the user service."
            ),
        )
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid JWT token.")

    student_id = (
        payload.get("sub")
        or payload.get("student_id")
        or payload.get("studentId")
        or payload.get("user_id")
        or payload.get("id")
        or payload.get("userId")
    )
    if not student_id:
        raise HTTPException(
            status_code=401,
            detail="JWT token does not contain a student identifier (sub/student_id).",
        )
    return str(student_id)


def get_latest_student_analysis(student_id: str) -> dict:
    """Return the imported analysis that belongs to the authenticated student."""
    try:
        document = get_collection("student_analyses").find_one(
            {"student_id": str(student_id)}, sort=[("created_at", -1)]
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Student analysis store is unavailable: {exc}",
        )

    if not document:
        raise HTTPException(
            status_code=404,
            detail=f"No imported analysis found for student '{student_id}'.",
        )
    return document


# --- Mastery Analysis Import Schemas ---


class ImportDataSources(BaseModel):
    github: str = Field(default="available")
    sandbox: str = Field(default="available")
    quizzes: str = Field(default="available")


class ImportWeakSubskill(BaseModel):
    subskill: str
    subskill_id: str
    status: str = "weak"
    evidence: Optional[str] = None
    recommended_content_focus: Optional[str] = None


class ImportObservedErrorPatterns(BaseModel):
    github: List[str] = Field(default_factory=list)
    sandbox: List[str] = Field(default_factory=list)
    quizzes: List[str] = Field(default_factory=list)


class ImportSuggestedIntervention(BaseModel):
    primary: str
    secondary: List[str] = Field(default_factory=list)
    difficulty_level: str
    estimated_time_minutes: int
    learning_objectives: List[str] = Field(default_factory=list)


class ImportKnowledgeGap(BaseModel):
    topic: str
    topic_id: str
    gap_type: str
    confidence: float
    mastery_score: int
    weak_subskills: List[ImportWeakSubskill] = Field(default_factory=list)
    known_subskills: List[Any] = Field(default_factory=list)
    misconceptions: List[str] = Field(default_factory=list)
    observed_error_patterns: ImportObservedErrorPatterns = (
        Field(default_factory=ImportObservedErrorPatterns)
    )
    evidence_summary: Optional[str] = None
    suggested_intervention: Optional[ImportSuggestedIntervention] = None


class ImportStrength(BaseModel):
    topic: str
    topic_id: str
    confidence: float
    mastery_score: int
    mastery_level: str = "advanced"
    can_teach_others: bool = False


class ImportMasteryProfile(BaseModel):
    overall_mastery_score: int
    knowledge_gaps: List[ImportKnowledgeGap] = Field(default_factory=list)
    strengths: List[ImportStrength] = Field(default_factory=list)


class ImportRecommendations(BaseModel):
    priority_order: List[str] = Field(default_factory=list)
    general_advice: Optional[str] = None
    for_instructor: Optional[str] = None


class StudentAnalysisImportRequest(BaseModel):
    import_id: Optional[str] = Field(default=None, alias="_id")
    schema_version: str = "kaa-lmg-v1.0"
    student_id: str = Field(..., json_schema_extra={"example": "STU-2026-0428"})
    analysis_timestamp: Optional[str] = None
    data_sources: ImportDataSources = Field(default_factory=ImportDataSources)
    mastery_profile: ImportMasteryProfile
    recommendations: ImportRecommendations = Field(
        default_factory=ImportRecommendations
    )
    overall_mastery_score: Optional[int] = None
    knowledge_gaps: Optional[List[ImportKnowledgeGap]] = None
    strengths: Optional[List[ImportStrength]] = None
    gap_topic_ids: List[str] = Field(default_factory=list)
    raw_analysis_payload: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    model_config = {"populate_by_name": True}


# --- Endpoints ---


@router.post(
    "/onboard-and-diagnose",
    summary="Stateful 7-Question Diagnostic Coding Session",
)
def onboard_and_diagnose_student(
    token_student_id: str = Depends(verify_jwt_student),
):
    """Manages a stateful 7-question diagnostic coding session.

    Flow:
    - First call: Creates session, generates 7 tasks, returns task 1
    - Subsequent calls: Returns next task based on current_task_index
    - After task 7: Returns session complete with performance summary

    Code evaluation happens at POST /api/assessment/evaluate.
    """
    try:
        now = datetime.now(timezone.utc).isoformat()
        sessions = get_collection("diagnostic_sessions")

        # Check for existing session
        existing_session = sessions.find_one(
            {"student_id": token_student_id, "status": {"$in": ["in_progress", "completed"]}},
            sort=[("created_at", -1)],
        )

        # A completed sequence can be revisited to retrieve its summary.
        if existing_session and existing_session.get("status") == "completed":
            results = existing_session.get("results", [])
            tasks_passed = sum(1 for result in results if result.get("passed") or result.get("grade") == "pass")
            return {
                "status": "session_complete",
                "student_id": token_student_id,
                "message": "Diagnostic session complete! All 7 tasks answered.",
                "session_summary": {
                    "total_tasks": len(existing_session.get("tasks", [])),
                    "tasks_passed": tasks_passed,
                    "mastery_score": existing_session.get("mastery_score", int((tasks_passed / 7) * 100)),
                    "results": results,
                },
            }

        # If session exists and in progress, return next task
        if existing_session and existing_session.get("status") == "in_progress":
            current_index = existing_session.get("current_task_index", 0)
            tasks = existing_session.get("tasks", [])

            # If all 7 tasks completed, mark session complete
            if current_index >= 7:
                results = existing_session.get("results", [])
                tasks_passed = sum(1 for r in results if r.get("grade") == "pass")
                mastery_score = int((tasks_passed / 7) * 100)

                sessions.update_one(
                    {"_id": existing_session["_id"]},
                    {"$set": {
                        "status": "completed",
                        "completed_at": now,
                        "tasks_passed": tasks_passed,
                        "mastery_score": mastery_score,
                    }},
                )

                return {
                    "status": "session_complete",
                    "student_id": token_student_id,
                    "message": "Diagnostic session complete! All 7 questions answered.",
                    "session_summary": {
                        "total_tasks": 7,
                        "tasks_passed": tasks_passed,
                        "mastery_score": mastery_score,
                        "results": results,
                    },
                }

            # Return current task
            current_task = tasks[current_index]
            return {
                "status": "in_progress",
                "student_id": token_student_id,
                "current_task_number": current_index + 1,
                "total_tasks": 7,
                "task": current_task,
                "instructions": (
                    f"Complete Task {current_index + 1} of 7. "
                    "Submit your code to POST /api/assessment/evaluate with task context, "
                    "then call this endpoint again to get the next task."
                ),
            }

        # No existing session — create new one
        # Fetch student analysis for knowledge gaps
        analysis = get_latest_student_analysis(token_student_id)
        knowledge_gaps = analysis.get("mastery_profile", {}).get("knowledge_gaps", [])

        if not knowledge_gaps:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"No knowledge gaps found for student '{token_student_id}'. "
                    "Import a mastery analysis first via /api/student/import-analysis."
                ),
            )

        # Use first knowledge gap's first weak subskill for diagnostic
        first_gap = knowledge_gaps[0]
        topic_id = first_gap.get("topic_id", "TOPIC_GENERIC")
        topic = first_gap.get("topic", "Java Programming")
        weak_subskills = first_gap.get("weak_subskills", [])

        if not weak_subskills:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"Student '{token_student_id}' has knowledge gaps but no "
                    "weak subskills to generate diagnostic tasks for."
                ),
            )

        subskill = weak_subskills[0].get("subskill", "General Concepts")

        # Generate all 7 tasks
        tasks = generate_all_diagnostic_coding_tasks(
            topic_id=topic_id,
            topic=topic,
            subskill=subskill,
        )

        # Save session to MongoDB
        session_doc = {
            "student_id": token_student_id,
            "status": "in_progress",
            "current_task_index": 0,
            "current_task": 1,
            "attempts": 0,
            "passed": False,
            "task_progress": [
                {
                    "task_number": index + 1,
                    "task_type": task.get("task_type", ""),
                    "status": "available" if index == 0 else "locked",
                    "attempts": 0,
                    "passed": False,
                }
                for index, task in enumerate(tasks)
            ],
            "tasks": tasks,
            "results": [],
            "topic_id": topic_id,
            "topic": topic,
            "subskill": subskill,
            "created_at": now,
            "updated_at": now,
        }
        sessions.insert_one(session_doc)

        return {
            "status": "in_progress",
            "student_id": token_student_id,
            "current_task_number": 1,
            "total_tasks": 7,
            "task": tasks[0],
            "instructions": (
                "Complete Task 1 of 7. "
                "Submit your code to POST /api/assessment/evaluate with task context, "
                "then call this endpoint again to get the next task."
            ),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start diagnostic session: {str(e)}",
        )


@router.post(
    "/diagnostic-session/reset",
    summary="Reset Diagnostic Session (Start Over)",
)
def reset_diagnostic_session(
    token_student_id: str = Depends(verify_jwt_student),
):
    """Deletes any existing diagnostic session for the student so they can start fresh."""
    try:
        sessions = get_collection("diagnostic_sessions")
        result = sessions.delete_many({"student_id": token_student_id})
        return {
            "status": "success",
            "student_id": token_student_id,
            "message": f"Deleted {result.deleted_count} diagnostic session(s). You can now call /onboard-and-diagnose to start fresh.",
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reset diagnostic session: {str(e)}",
        )


@router.get(
    "/diagnostic-session/status",
    summary="Check Diagnostic Session Status",
)
def get_diagnostic_session_status(
    token_student_id: str = Depends(verify_jwt_student),
):
    """Returns the current diagnostic session state for debugging."""
    try:
        sessions = get_collection("diagnostic_sessions")
        all_sessions = list(sessions.find({"student_id": token_student_id}))
        session_list = []
        for s in all_sessions:
            session_list.append({
                "_id": str(s["_id"]),
                "student_id": s.get("student_id"),
                "status": s.get("status"),
                "current_task_index": s.get("current_task_index"),
                "total_tasks": len(s.get("tasks", [])),
                "total_results": len(s.get("results", [])),
                "created_at": s.get("created_at"),
            })
        return {
            "status": "success",
            "student_id": token_student_id,
            "total_sessions": len(session_list),
            "sessions": session_list,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get session status: {str(e)}",
        )


@router.post(
    "/import-analysis",
    summary="Import New Student Mastery Analysis (JWT Authenticated)",
)
def import_student_analysis(
    payload: StudentAnalysisImportRequest,
    token_student_id: str = Depends(verify_jwt_student),
):
    """Imports a new student's full mastery analysis document.

    The login JWT (Bearer token in the Authorization header) is verified with a
    full signature check. The student identity is taken from the token and must
    match the ``student_id`` in the request body.
    """
    if str(token_student_id) != str(payload.student_id):
        raise HTTPException(
            status_code=403,
            detail=(
                f"JWT student '{token_student_id}' does not match payload "
                f"student_id '{payload.student_id}'."
            ),
        )

    now = datetime.now(timezone.utc).isoformat()

    imported_document = {
        "_id": payload.import_id or f"ANL_{uuid.uuid4().hex[:8].upper()}",
        "schema_version": payload.schema_version,
        "student_id": payload.student_id,
        "analysis_timestamp": payload.analysis_timestamp or now,
        "data_sources": payload.data_sources.model_dump(),
        "mastery_profile": payload.mastery_profile.model_dump(),
        "recommendations": payload.recommendations.model_dump(),
        "overall_mastery_score": payload.overall_mastery_score
        or payload.mastery_profile.overall_mastery_score,
        "knowledge_gaps": (
            [gap.model_dump() for gap in payload.knowledge_gaps]
            if payload.knowledge_gaps is not None
            else payload.mastery_profile.model_dump()["knowledge_gaps"]
        ),
        "strengths": (
            [s.model_dump() for s in payload.strengths]
            if payload.strengths is not None
            else payload.mastery_profile.model_dump()["strengths"]
        ),
        "gap_topic_ids": payload.gap_topic_ids
        or [
            gap.topic_id for gap in payload.mastery_profile.knowledge_gaps
        ],
        "raw_analysis_payload": payload.raw_analysis_payload,
        "created_at": payload.created_at or now,
        "updated_at": payload.updated_at or now,
    }

    # Save the full analysis document to MongoDB
    save_student_analysis(imported_document)

    return {
        "status": "success",
        "message": f"Student {payload.student_id} imported successfully.",
        "imported_document": imported_document,
    }


@router.get(
    "/analysis/{student_id}",
    summary="Get Student Mastery Analysis by Student ID",
)
def get_student_analysis(
    student_id: str,
    token_student_id: str = Depends(verify_jwt_student),
):
    """Retrieves the latest mastery analysis document for a student from the
    student_analyses collection.
    """
    try:
        if str(student_id) != str(token_student_id):
            raise HTTPException(status_code=403, detail="Student identity does not match the JWT.")
        document = get_latest_student_analysis(token_student_id)
        document["_id"] = str(document["_id"])
        return {
            "status": "success",
            "analysis": document,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve analysis: {str(e)}",
        )