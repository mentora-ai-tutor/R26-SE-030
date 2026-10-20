from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

# Import Agent Instances
from app.agents.assessment_agent import assessment_agent
from app.agents.student_agent import grade_coding_submission
from app.api.student_routes import verify_jwt_student
from app.services.mongodb import get_collection

router = APIRouter(prefix="/api", tags=["AI Agents Engine"])


# ==========================================
# 1. Pydantic Request & Response Schemas
# ==========================================

class CodeEvaluationRequest(BaseModel):
    code: str = Field(..., example="public class Main {\n    public static void main(String[] args) {\n        System.out.println(\"Hello World\");\n    }\n}")


class PeerMatchRequest(BaseModel):
    student_id: str = Field(..., example="STU_2026_0428")
    target_topic: str = Field(..., example="Recursion")
    max_matches: int = Field(default=3, example=3)


class RAGQueryRequest(BaseModel):
    student_id: str = Field(..., example="STU_2026_0428")
    query: str = Field(..., example="Java වල Interface භාවිතා කරන්නේ ඇයි?")
    code_context: Optional[str] = Field(default=None)


class DiscussionSummaryRequest(BaseModel):
    session_id: str = Field(..., example="SESS_8832")
    chat_messages: List[Dict[str, str]] = Field(
        ...,
        example=[
            {"sender": "STU_001", "message": "Base case එක නැතුව recursion කල් කලොත් මොකද වෙන්නෙ?"},
            {"sender": "STU_002", "message": "StackOverflowError එකක් එනවා බං."},
        ]
    )


# ==========================================
# 2. API Endpoints
# ==========================================

# --- A. Assessment Agent Endpoints ---
@router.post(
    "/assessment/evaluate",
    summary="Evaluate Java Code Syntax, Quality & Recursion Logic",
    status_code=status.HTTP_200_OK
)
def evaluate_code(
    request: CodeEvaluationRequest,
    token_student_id: str = Depends(verify_jwt_student),
) -> Dict[str, Any]:
    """
    For diagnostic sessions: student_id and task_number are auto-fetched.
    Just provide the code.
    """
    print(f"🔍 /assessment/evaluate called by student_id={token_student_id}")

    try:
        # Standard syntax/compilation evaluation
        syntax_result = assessment_agent.evaluate_java_code(
            student_id=token_student_id,
            code=request.code,
            topic_id=None
        )

        # Check for active diagnostic session
        now = datetime.now(timezone.utc).isoformat()
        sessions = get_collection("diagnostic_sessions")

        # Debug: count all sessions for this student
        all_sessions = list(sessions.find({"student_id": token_student_id}))
        print(f"🔍 Found {len(all_sessions)} session(s) for student {token_student_id}")
        for s in all_sessions:
            print(f"   → session _id={s['_id']}, status={s.get('status')}, current_task_index={s.get('current_task_index')}")

        session = sessions.find_one(
            {"student_id": token_student_id, "status": "in_progress"},
            sort=[("created_at", -1)],
        )

        if not session:
            print(f"⚠️ No 'in_progress' session found for {token_student_id}")
            return {
                "status": "success",
                "student_id": token_student_id,
                "evaluation_type": "syntax_only",
                "syntax_evaluation": syntax_result.get("evaluation", {}),
                "note": "No active diagnostic session found. Call /api/student/onboard-and-diagnose first.",
            }

        print(f"✅ Found session: _id={session['_id']}, current_task_index={session.get('current_task_index')}")

        # Auto-fetch task number from session
        current_index = session.get("current_task_index", 0)
        task_number = current_index + 1

        # Get task details from session
        tasks = session.get("tasks", [])
        if current_index >= len(tasks):
            print(f"⚠️ current_index={current_index} >= len(tasks)={len(tasks)}")
            return {
                "status": "success",
                "student_id": token_student_id,
                "evaluation_type": "syntax_only",
                "syntax_evaluation": syntax_result.get("evaluation", {}),
                "note": "Diagnostic session has no more tasks.",
            }

        task = tasks[current_index]
        task_description = task.get("task_description", "")
        evaluation_criteria = task.get("evaluation_criteria", "")
        topic = session.get("topic", "Java Programming")
        subskill = session.get("subskill", "Java Concepts")

        print(f"📝 Grading task {task_number}: {task.get('task_type', 'unknown')}")

        # Grade the submission (isolated error handling)
        try:
            grade_result = grade_coding_submission(
                topic=topic,
                subskill=subskill,
                task_description=task_description,
                evaluation_criteria=evaluation_criteria,
                submitted_code=request.code,
            )
            print(f"✅ Grading complete: grade={grade_result.get('grade')}")
        except Exception as grade_err:
            print(f"⚠️ Grading error for task {task_number}: {grade_err}")
            grade_result = {
                "grade": "fail",
                "feedback": f"Grading failed: {str(grade_err)}. Manual review required.",
                "sample_approach": f"A correct solution would demonstrate {subskill} in {topic}.",
            }

        result_entry = {
            "task_number": task_number,
            "submitted_code": request.code,
            "grade": grade_result.get("grade", "fail"),
            "feedback": grade_result.get("feedback", ""),
            "sample_approach": grade_result.get("sample_approach", ""),
            "syntax_result": syntax_result.get("evaluation", {}),
            "graded_at": now,
        }

        # ALWAYS update session — even if grading failed
        update_result = sessions.update_one(
            {"_id": session["_id"]},
            {
                "$push": {"results": result_entry},
                "$set": {"current_task_index": current_index + 1, "updated_at": now},
            },
        )

        print(f"✅ Session updated for task {task_number}: matched={update_result.matched_count}, modified={update_result.modified_count}, new_index={current_index + 1}")

        return {
            "status": "success",
            "student_id": token_student_id,
            "evaluation_type": "diagnostic_task",
            "syntax_evaluation": syntax_result.get("evaluation", {}),
            "task_evaluation": grade_result,
            "task_number": task_number,
            "next_task_available": task_number < 7,
        }

    except Exception as e:
        print(f"❌ Assessment error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Assessment Agent Error: {str(e)}"
        )


# --- B. Student Learning Agent Endpoints ---
@router.get(
    "/student/{student_id}/mastery-profile",
    summary="Get Student Mastery Profile & Knowledge Gaps JSON",
    status_code=status.HTTP_200_OK
)
def get_student_mastery_profile(student_id: str) -> Dict[str, Any]:
    """
    ශිෂ්‍යයාගේ progress, weak subskills, knowledge gaps සහ mastery score
    අඩංගු සම්පූර්ණ JSON Profile Analysis එක ලබාදෙයි.
    """
    try:
        profile_data = student_agent_instance.analyze_student_progress(student_id)
        return profile_data
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Student Learning Agent Error: {str(e)}"
        )


# --- C. Peer Matching Agent Endpoints ---
@router.post(
    "/peers/match",
    summary="Match Learning Partners using KNN / Cosine Similarity",
    status_code=status.HTTP_200_OK
)
def match_study_peers(request: PeerMatchRequest) -> Dict[str, Any]:
    """
    ශිෂ්‍යයාගේ skill gaps සහ වෙනත් සිසුන්ගේ strengths සසඳමින් (KNN / Cosine Similarity)
    ගැළපෙන Study Partners නිර්දේශ කරයි.
    """
    try:
        # Placeholder for PeerMatchingAgent integration logic
        return {
            "status": "success",
            "student_id": request.student_id,
            "target_topic": request.target_topic,
            "matched_peers": [
                {
                    "peer_id": "STU_2026_0102",
                    "similarity_score": 0.92,
                    "mastery_score": 88,
                    "can_help_with": ["Recursion", "Loops"],
                    "status": "online"
                },
                {
                    "peer_id": "STU_2026_0311",
                    "similarity_score": 0.85,
                    "mastery_score": 82,
                    "can_help_with": ["Recursion"],
                    "status": "busy"
                }
            ]
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Peer Matching Agent Error: {str(e)}"
        )


# --- D. Knowledge Retrieval Agent (RAG) Endpoints ---
@router.post(
    "/knowledge/query",
    summary="Query Java Knowledge Base using RAG Pipeline",
    status_code=status.HTTP_200_OK
)
def query_java_knowledge(request: RAGQueryRequest) -> Dict[str, Any]:
    """
    Vector Database (ChromaDB) එකෙන් Java docs retrieve කර
    Context-aware explanation සහ code examples ලබාදෙයි.
    """
    try:
        # Placeholder for RAG / RetrievalAgent integration
        return {
            "status": "success",
            "student_id": request.student_id,
            "query": request.query,
            "responding_agent": "Knowledge Retrieval Agent",
            "answer": "Java හි Interface භාවිත කරන්නේ Multiple Inheritance සාක්ෂාත් කර ගැනීමට, Abstraction ලබා දීමට සහ Loose Coupling තහවුරු කිරීමටයි.",
            "retrieved_sources": [
                "Java_Docs_Chapter_5_Interfaces.pdf",
                "OOP_Concepts_Lecture_Note_3.md"
            ]
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Retrieval Agent Error: {str(e)}"
        )


# --- E. Discussion Moderator Agent Endpoints ---
@router.post(
    "/moderator/summarize",
    summary="Analyze and Summarize Collaborative Chat Sessions",
    status_code=status.HTTP_200_OK
)
def summarize_discussion(request: DiscussionSummaryRequest) -> Dict[str, Any]:
    """
    Real-time collaboration සන්නිවේදනය පරීක්ෂා කර
    වැදගත් Learning Points හා Discussion Summary සකස් කරයි.
    """
    try:
        # Placeholder for DiscussionModeratorAgent logic
        return {
            "status": "success",
            "session_id": request.session_id,
            "summary": "ශිෂ්‍යයන් Recursion Base Case එකක් නොමැති වූ විට සිදුවන StackOverflowError එක පිළිබඳව සාකච්ඡා කරන ලදී.",
            "key_takeaways": [
                "Recursion එකක ප්‍රධාන කොටස් දෙකකි: Base Case සහ Recursive Step.",
                "Base Case එකක් නොමැති නම් infinite loop එකක් වී StackOverflowError එකක් ලැබේ."
            ],
            "off_topic_detected": False
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Moderator Agent Error: {str(e)}"
        )