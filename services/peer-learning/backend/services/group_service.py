# backend/services/group_service.py
from database import get_db
from services.question_service import generate_question
from datetime import datetime
import random, uuid

async def trigger_group_session(topic_id: str):
    """Called when ≥3 students are in the improved pool for a topic."""
    db = get_db()
    
    # Get all students in the improved pool for this topic
    pool_cursor = db.topic_pools.find({
        "topic_id": topic_id,
        "pool_type": "improved"
    })
    pool_docs = await pool_cursor.to_list(length=100)
    
    if len(pool_docs) < 3:
        return
    
    # Pick 3 at random
    selected = random.sample(pool_docs, 3)
    student_ids = [s["student_id"] for s in selected]
    
    # Assign roles randomly
    roles_list = ["explainer", "solver", "reviewer"]
    random.shuffle(roles_list)
    members = [
        {"student_id": sid, "role": role}
        for sid, role in zip(student_ids, roles_list)
    ]
    
    # Determine session type (cycle through coding → debugging → mini_project)
    session_types = ["coding", "debugging", "mini_project"]
    session_type = random.choice(session_types)
    
    # Generate a group problem using LLM
    topic_name = pool_docs[0]["topic_name"]
    problem = await generate_group_problem(topic_name, session_type)
    
    session_id = f"GS-{uuid.uuid4().hex[:8].upper()}"
    
    group_doc = {
        "session_id": session_id,
        "topic_id": topic_id,
        "topic_name": topic_name,
        "session_type": session_type,
        "status": "active",
        "created_at": datetime.utcnow(),
        "members": members,
        "problem": problem,
        "performance": {sid: {"score": 0, "hints_used": 0, "role_adherence": 1.0} for sid in student_ids},
        "session_history": []
    }
    
    await db.group_sessions.insert_one(group_doc)
    
    # Remove these 3 from the pool (they're now in a group session)
    await db.topic_pools.delete_many({
        "topic_id": topic_id,
        "pool_type": "improved",
        "student_id": {"$in": student_ids}
    })
    
    return group_doc

async def generate_group_problem(topic_name: str, session_type: str) -> dict:
    """Generate a problem suited to the group session type."""
    type_instructions = {
        "coding": "a coding problem to implement from scratch",
        "debugging": "buggy code that needs to be found and fixed",
        "mini_project": "a small self-contained project combining multiple concepts"
    }
    
    instruction = type_instructions.get(session_type, "a coding problem")
    
    # Use same Ollama function but with group-level prompt
    import httpx, json, os
    OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    
    prompt = f"""Generate {instruction} about {topic_name} for a group of 3 students.
The group has roles: Explainer (explains concepts), Solver (writes code), Reviewer (checks and suggests improvements).

Return ONLY a JSON object:
{{
  "problem_statement": "clear problem description",
  "requirements": ["requirement 1", "requirement 2", "requirement 3"],
  "explainer_guide": "what concepts the explainer should cover",
  "solver_starter": "starter code or pseudocode for the solver",
  "reviewer_checklist": ["check 1", "check 2", "check 3"],
  "hints": ["group hint 1", "group hint 2", "group hint 3"]
}}"""
    
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": "llama3", "prompt": prompt, "stream": False}
        )
    
    raw = response.json()["response"].strip().removeprefix("```json").removesuffix("```").strip()
    return json.loads(raw)

async def rotate_group_roles(session_id: str) -> dict:
    """Rotate roles for the next group session."""
    db = get_db()
    session = await db.group_sessions.find_one({"session_id": session_id})
    
    members = session["members"]
    roles = [m["role"] for m in members]
    # Rotate: explainer→reviewer→solver→explainer
    rotated_roles = roles[-1:] + roles[:-1]
    
    new_members = [
        {"student_id": m["student_id"], "role": rotated_roles[i]}
        for i, m in enumerate(members)
    ]
    
    # Save history before rotating
    await db.group_sessions.update_one(
        {"session_id": session_id},
        {
            "$push": {"session_history": {"members": members, "completed_at": datetime.utcnow().isoformat()}},
            "$set": {"members": new_members}
        }
    )
    
    return new_members

async def check_group_mastery(session_id: str) -> str:
    """Check if all 3 students have ≥90% — if so, move to Verified Pool."""
    db = get_db()
    session = await db.group_sessions.find_one({"session_id": session_id})
    
    scores = [v["score"] for v in session["performance"].values()]
    all_mastered = all(s >= 90 for s in scores)
    
    if all_mastered:
        student_ids = [m["student_id"] for m in session["members"]]
        
        for student_id in student_ids:
            # Add to verified pool
            await db.topic_pools.insert_one({
                "topic_id": session["topic_id"],
                "topic_name": session["topic_name"],
                "pool_type": "verified",
                "student_id": student_id,
                "added_at": datetime.utcnow()
            })
            # Mark topic as verified in student doc
            await db.students.update_one(
                {"student_id": student_id},
                {"$addToSet": {"verified_topics": session["topic_id"]}}
            )
            # Move to next weak topic
            from services.performance_service import move_to_next_weak_topic
            await move_to_next_weak_topic(student_id)
        
        await db.group_sessions.update_one(
            {"session_id": session_id},
            {"$set": {"status": "completed"}}
        )
        return "ALL_MASTERED"
    
    else:
        return "NEEDS_MORE_SESSIONS"