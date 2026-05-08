import random
from datetime import datetime
from typing import Dict, Any, List, Optional
from loguru import logger
from app.core.database import get_db
from app.core.config import settings
from app.core.llm_client import llm_client
from app.models.models import ActivityType, GroupRole, SessionStatus
from app.utils.helpers import (
    generate_group_session_id,
    assign_initial_group_roles,
    rotate_group_roles,
    calculate_role_score,
)


async def form_group_session(topic_id: str) -> Optional[Dict[str, Any]]:
    """
    Phase 7: Form a group session from the improved pool.
    Triggered when pool size >= 3.
    """
    db = get_db()

    # Get students from improved pool (not yet in group)
    pool_entries = await db.improved_pools.find(
        {"topic_id": topic_id},
        {"_id": 0},
    ).to_list(length=None)

    if len(pool_entries) < 3:
        return {"error": f"Not enough students in pool (need 3, have {len(pool_entries)})"}

    # Select 3 students
    selected = random.sample(pool_entries, 3)

    # Sort by mastery for role assignment
    selected_sorted = sorted(selected, key=lambda x: x.get("mastery_score", 0), reverse=True)

    # Assign initial roles
    members_with_roles = assign_initial_group_roles([
        {"student_id": s["student_id"], "mastery_score": s.get("mastery_score", 0)}
        for s in selected_sorted
    ])

    # Pick random activity
    activity = random.choice(list(ActivityType))

    topic_name = selected[0].get("topic_name", topic_id)

    # Generate problem via LLM
    problem = await llm_client.generate_group_problem(
        topic=topic_name,
        activity_type=activity.value,
        topic_id=topic_id,
    )

    session_id = generate_group_session_id()
    doc = {
        "session_id": session_id,
        "topic_id": topic_id,
        "topic_name": topic_name,
        "members": members_with_roles,
        "activity_type": activity.value,
        "status": SessionStatus.ACTIVE.value,
        "created_at": datetime.utcnow(),
        "completed_at": None,
        "problem_statement": problem.get("problem_statement") if problem else None,
        "explainer_guide": problem.get("explainer_guide") if problem else None,
        "solver_starter": problem.get("solver_starter") if problem else None,
        "reviewer_checklist": problem.get("reviewer_checklist") if problem else None,
        "expected_solution": problem.get("expected_solution") if problem else None,
        "session_number": 1,
        "group_average_score": None,
        "chat_log": [],
        "sandbox_code": problem.get("solver_starter") if problem else "",
    }

    await db.group_sessions.insert_one(doc)
    doc.pop("_id", None)

    # Reserve students
    for member in members_with_roles:
        await db.students.update_one(
            {"student_id": member["student_id"]},
            {
                "$set": {
                    "current_session_id": session_id,
                    "status": "in_session",
                    "updated_at": datetime.utcnow(),
                },
                "$push": {"session_history": session_id},
            },
        )

    logger.info(f"Group session {session_id} formed for topic {topic_name}")
    return doc


async def get_group_session(session_id: str) -> Optional[Dict]:
    db = get_db()
    return await db.group_sessions.find_one({"session_id": session_id}, {"_id": 0})


async def submit_group_scores(
    session_id: str,
    student_id: str,
    task_completion: float,
    collaboration: float,
    communication: float,
) -> Dict[str, Any]:
    """
    Submit scores for a member in a group session.
    Checks if all members have submitted, then evaluates and decides next action.
    """
    db = get_db()
    session = await db.group_sessions.find_one({"session_id": session_id})
    if not session:
        return {"error": "Group session not found"}

    role_score = calculate_role_score(task_completion, collaboration, communication)

    # Update member's score
    members = session.get("members", [])
    updated_members = []
    for m in members:
        if m["student_id"] == student_id:
            m = {
                **m,
                "score": role_score,
                "task_completion": task_completion,
                "collaboration": collaboration,
                "communication": communication,
            }
        updated_members.append(m)

    await db.group_sessions.update_one(
        {"session_id": session_id},
        {"$set": {"members": updated_members}},
    )

    # Check if all members have submitted scores
    all_scored = all(m.get("score") is not None for m in updated_members)

    if not all_scored:
        return {"session_id": session_id, "status": "score_recorded", "waiting_for_others": True}

    # All scores in: compute group average and decide
    avg_score = sum(m.get("score", 0) for m in updated_members) / len(updated_members)
    session_number = session.get("session_number", 1)

    await db.group_sessions.update_one(
        {"session_id": session_id},
        {
            "$set": {
                "status": SessionStatus.COMPLETED.value,
                "completed_at": datetime.utcnow(),
                "group_average_score": round(avg_score, 2),
                "members": updated_members,
            }
        },
    )

    # Release all students
    for m in updated_members:
        await db.students.update_one(
            {"student_id": m["student_id"]},
            {
                "$set": {
                    "current_session_id": None,
                    "status": "active",
                    "updated_at": datetime.utcnow(),
                }
            },
        )

    results = []
    for member in updated_members:
        student_id_m = member["student_id"]
        member_score = member.get("score", 0)

        if member_score >= settings.group_session_mastery_threshold:
            # Update consecutive sessions counter in improved pool
            pool_entry = await db.improved_pools.find_one(
                {"student_id": student_id_m, "topic_id": session["topic_id"]}
            )
            if pool_entry:
                new_consecutive = pool_entry.get("consecutive_group_sessions_above_threshold", 0) + 1
                group_ids = pool_entry.get("group_session_ids", []) + [session_id]
                no_hints_last_two = _check_no_hints(group_ids, db)

                await db.improved_pools.update_one(
                    {"student_id": student_id_m, "topic_id": session["topic_id"]},
                    {
                        "$set": {
                            "consecutive_group_sessions_above_threshold": new_consecutive,
                            "group_session_ids": group_ids,
                        }
                    },
                )

                # Check verification criteria
                if new_consecutive >= settings.verification_consecutive_sessions:
                    from app.services.verification_service import check_verification_criteria
                    verification = await check_verification_criteria(
                        student_id_m, session["topic_id"]
                    )
                    results.append({
                        "student_id": student_id_m,
                        "score": member_score,
                        "action": "verification_check",
                        "verification_result": verification,
                    })
                    continue

            results.append({
                "student_id": student_id_m,
                "score": member_score,
                "action": "continue_group",
            })

        elif member_score < 50:
            # Remove from group, back to pair programming
            await db.improved_pools.update_one(
                {"student_id": student_id_m, "topic_id": session["topic_id"]},
                {"$set": {"consecutive_group_sessions_above_threshold": 0}},
            )
            results.append({
                "student_id": student_id_m,
                "score": member_score,
                "action": "back_to_pair_programming",
            })
        else:
            results.append({
                "student_id": student_id_m,
                "score": member_score,
                "action": "continue_group",
            })

    # Check group average - if below 70, disband
    if avg_score < 70:
        action = "group_disbanded"
    else:
        action = "continue"

    # Form next group session if continuing
    if action == "continue" and avg_score >= 50:
        await _form_next_group_session(session, updated_members, avg_score)

    return {
        "session_id": session_id,
        "group_average_score": round(avg_score, 2),
        "member_results": results,
        "group_action": action,
    }


def _check_no_hints(group_session_ids: List[str], db) -> bool:
    """Placeholder: Check if no hints used in last 2 sessions."""
    # In a full implementation, we'd query session hint usage
    return True


async def _form_next_group_session(
    prev_session: Dict, members: List[Dict], prev_avg_score: float
):
    """Form a new group session with role rotation for continuing members."""
    db = get_db()

    # Only continue members who scored >= 50
    continuing = [m for m in members if m.get("score", 0) >= 50]
    if len(continuing) < 3:
        return

    topic_id = prev_session["topic_id"]
    topic_name = prev_session["topic_name"]
    prev_session_number = prev_session.get("session_number", 1)

    # Rotate roles
    rotated = rotate_group_roles(
        [{k: v for k, v in m.items() if k != "score"} for m in continuing],
        session_number=prev_session_number + 1,
    )

    activity = random.choice(list(ActivityType))
    problem = await llm_client.generate_group_problem(
        topic=topic_name,
        activity_type=activity.value,
        topic_id=topic_id,
    )

    session_id = generate_group_session_id()
    doc = {
        "session_id": session_id,
        "topic_id": topic_id,
        "topic_name": topic_name,
        "members": rotated,
        "activity_type": activity.value,
        "status": SessionStatus.ACTIVE.value,
        "created_at": datetime.utcnow(),
        "completed_at": None,
        "problem_statement": problem.get("problem_statement") if problem else None,
        "explainer_guide": problem.get("explainer_guide") if problem else None,
        "solver_starter": problem.get("solver_starter") if problem else None,
        "reviewer_checklist": problem.get("reviewer_checklist") if problem else None,
        "expected_solution": problem.get("expected_solution") if problem else None,
        "session_number": prev_session_number + 1,
        "group_average_score": None,
        "chat_log": [],
        "sandbox_code": problem.get("solver_starter") if problem else "",
    }

    await db.group_sessions.insert_one(doc)
    for m in rotated:
        await db.students.update_one(
            {"student_id": m["student_id"]},
            {
                "$set": {
                    "current_session_id": session_id,
                    "status": "in_session",
                    "updated_at": datetime.utcnow(),
                },
                "$push": {"session_history": session_id},
            },
        )

    logger.info(f"Follow-up group session {session_id} formed (session #{prev_session_number + 1})")
    return doc
