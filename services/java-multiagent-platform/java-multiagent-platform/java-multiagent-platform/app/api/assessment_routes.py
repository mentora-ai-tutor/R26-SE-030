import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.api.student_routes import get_latest_student_analysis, verify_jwt_student
from app.agents.assessment_agent import assessment_agent
from app.agents.student_agent import grade_coding_submission
from app.api.collab_routes import collab_manager
from app.services.mongodb import get_collection, save_assessment

router = APIRouter(prefix="/api/assessment", tags=["Assessment Agent"])


class CodeEvaluationRequest(BaseModel):
    code: str


@router.post("/evaluate")
async def evaluate_code(
    request: CodeEvaluationRequest,
    token_student_id: str = Depends(verify_jwt_student),
):
    """
    Assessment Agent හරහා කේතය පරීක්ෂා කර සෘජුවම Response එක ලබාදෙන Endpoint එක.
    """
    try:
        analysis = get_latest_student_analysis(token_student_id)
        gaps = analysis.get("knowledge_gaps") or analysis.get("mastery_profile", {}).get("knowledge_gaps") or []
        topic_id = (analysis.get("gap_topic_ids") or [None])[0]
        if not topic_id and gaps:
            topic_id = gaps[0].get("topic_id")
        result = assessment_agent.evaluate_java_code(
            student_id=token_student_id,
            code=request.code,
            topic_id=topic_id
        )

        # Save the code assessment result to MongoDB
        save_assessment({
            "student_id": token_student_id,
            "language": "java",
            "topic_id": topic_id,
            "code": request.code,
            "evaluation": result.get("evaluation", result),
            "result": result,
        })

        # A collaborative room is the source of truth for peer-task progress.
        rooms = get_collection("collab_rooms")
        room = rooms.find_one({
            "$or": [
                {"learner_student_id": token_student_id},
                {"peer_student_id": token_student_id},
            ],
            "status": "in_progress",
        }, sort=[("created_at", -1)])
        if room and room.get("coding_tasks"):
            current_task = room.get("current_task", room.get("current_task_index", 0) + 1)
            task_index = current_task - 1
            tasks = room["coding_tasks"]
            if task_index < 0 or task_index >= len(tasks):
                raise HTTPException(status_code=409, detail="No unlocked task is available.")

            task = tasks[task_index]
            topic = room.get("topic", "Java Programming")
            subskill = room.get("target_subskill", "Java Concepts")
            try:
                grade_result = grade_coding_submission(
                    topic=topic,
                    subskill=subskill,
                    task_description=task.get("task_description", ""),
                    evaluation_criteria=task.get("evaluation_criteria", ""),
                    submitted_code=request.code,
                )
            except Exception as grade_error:
                grade_result = {
                    "grade": "fail",
                    "feedback": f"Grading failed: {grade_error}. Manual review required.",
                    "sample_approach": "Review the task requirements and try again.",
                }

            syntax_evaluation = result.get("evaluation", {})
            passed = bool(syntax_evaluation.get("is_valid")) and grade_result.get("grade") == "pass"
            progress = list(room.get("task_progress", []))
            while len(progress) < len(tasks):
                index = len(progress)
                progress.append({
                    "task_number": index + 1,
                    "task_type": tasks[index].get("task_type", ""),
                    "status": "available" if index == 0 else "locked",
                    "attempts": 0,
                    "passed": False,
                })

            current_progress = dict(progress[task_index])
            current_progress["attempts"] = current_progress.get("attempts", 0) + 1
            current_progress["passed"] = passed
            current_progress["status"] = "completed" if passed else "available"
            progress[task_index] = current_progress

            next_task = current_task
            sequence_complete = passed and task_index == len(tasks) - 1
            if passed and not sequence_complete:
                next_task = current_task + 1
                progress[next_task - 1]["status"] = "available"

            next_attempts = 0 if passed and not sequence_complete else current_progress["attempts"]
            next_passed = passed if sequence_complete else False

            now = datetime.now(timezone.utc).isoformat()
            result_entry = {
                "task_number": current_task,
                "submitted_code": request.code,
                "grade": grade_result.get("grade", "fail"),
                "passed": passed,
                "feedback": grade_result.get("feedback", ""),
                "sample_approach": grade_result.get("sample_approach", ""),
                "syntax_result": syntax_evaluation,
                "graded_at": now,
            }
            update = {
                "$push": {"results": result_entry},
                "$set": {
                    "current_task_index": next_task - 1,
                    "current_task": next_task,
                    "status": "completed" if sequence_complete else "in_progress",
                    "attempts": next_attempts,
                    "passed": next_passed,
                    "task_progress": progress,
                    "updated_at": now,
                },
            }
            update_result = rooms.update_one(
                {"_id": room["_id"], "current_task": current_task, "status": "in_progress"},
                update,
            )
            if update_result.matched_count != 1:
                raise HTTPException(status_code=409, detail="Task state changed; reload the room and try again.")

            collab_manager.room_task_index[room["room_id"]] = next_task - 1
            if passed and not sequence_complete:
                collab_manager.update_code_state(room["room_id"], tasks[next_task - 1].get("starter_code", ""))

            progress_message = json.dumps({
                "type": "TASK_PROGRESS",
                "current_task": next_task,
                "current_task_index": next_task - 1,
                "total_tasks": len(tasks),
                "status": "completed" if sequence_complete else "in_progress",
                "attempts": next_attempts,
                "passed": next_passed,
                "task_progress": progress,
                "task": tasks[next_task - 1],
                "sequence_complete": sequence_complete,
            })
            await collab_manager.broadcast_all(progress_message, room["room_id"])

            return {
                **result,
                "evaluation_type": "collaborative_task",
                "task_evaluation": grade_result,
                "task_number": current_task,
                "passed": passed,
                "current_task": next_task,
                "sequence_complete": sequence_complete,
            }

        # Legacy diagnostic sessions use this endpoint as the submission step.
        sessions = get_collection("diagnostic_sessions")
        session = sessions.find_one(
            {"student_id": token_student_id, "status": "in_progress"},
            sort=[("created_at", -1)],
        )
        if not session:
            return result

        current_index = session.get("current_task_index", 0)
        tasks = session.get("tasks", [])
        if current_index >= len(tasks):
            return result

        task = tasks[current_index]
        topic = session.get("topic", "Java Programming")
        subskill = session.get("subskill", "Java Concepts")
        try:
            grade_result = grade_coding_submission(
                topic=topic,
                subskill=subskill,
                task_description=task.get("task_description", ""),
                evaluation_criteria=task.get("evaluation_criteria", ""),
                submitted_code=request.code,
            )
        except Exception as grade_error:
            grade_result = {
                "grade": "fail",
                "feedback": f"Grading failed: {grade_error}. Manual review required.",
                "sample_approach": f"A correct solution would demonstrate {subskill} in {topic}.",
            }

        now = datetime.now(timezone.utc).isoformat()
        passed = bool(result.get("evaluation", {}).get("is_valid")) and grade_result.get("grade") == "pass"
        task_progress = list(session.get("task_progress", []))
        while len(task_progress) < len(tasks):
            index = len(task_progress)
            task_progress.append({
                "task_number": index + 1,
                "task_type": tasks[index].get("task_type", ""),
                "status": "available" if index == current_index else "locked",
                "attempts": 0,
                "passed": False,
            })
        current_progress = dict(task_progress[current_index])
        current_progress["attempts"] = current_progress.get("attempts", 0) + 1
        current_progress["passed"] = passed
        current_progress["status"] = "completed" if passed else "available"
        task_progress[current_index] = current_progress
        next_index = current_index + 1 if passed else current_index
        sequence_complete = passed and next_index == len(tasks)
        if passed and not sequence_complete:
            task_progress[next_index]["status"] = "available"
        result_entry = {
            "task_number": current_index + 1,
            "submitted_code": request.code,
            "grade": grade_result.get("grade", "fail"),
            "passed": passed,
            "feedback": grade_result.get("feedback", ""),
            "sample_approach": grade_result.get("sample_approach", ""),
            "syntax_result": result.get("evaluation", {}),
            "graded_at": now,
        }
        sessions.update_one(
            {"_id": session["_id"], "current_task_index": current_index},
            {
                "$push": {"results": result_entry},
                "$set": {
                    "current_task_index": next_index,
                    "current_task": min(next_index + 1, len(tasks)),
                    "status": "completed" if sequence_complete else "in_progress",
                    "attempts": current_progress["attempts"] if not passed else 0,
                    "passed": passed if sequence_complete else False,
                    "task_progress": task_progress,
                    "tasks_passed": sum(1 for item in task_progress if item.get("passed")),
                    "mastery_score": int((sum(1 for item in task_progress if item.get("passed")) / len(tasks)) * 100),
                    "updated_at": now,
                },
            },
        )

        return {
            **result,
            "evaluation_type": "diagnostic_task",
            "task_evaluation": grade_result,
            "task_number": current_index + 1,
            "passed": passed,
            "next_task_available": passed and current_index + 1 < len(tasks),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Assessment Error: {str(e)}")