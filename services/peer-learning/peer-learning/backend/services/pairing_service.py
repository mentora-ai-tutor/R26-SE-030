# backend/services/pairing_service.py
from database import get_db
from datetime import datetime
import uuid

async def find_teacher_for_topic(topic_id: str, exclude_student_id: str) -> dict | None:
    """
    MongoDB query: find a student who is strong in this topic,
    can teach others, and is not currently in an active session.
    """
    db = get_db()
    
    teacher = await db.students.find_one({
        # Must be strong in the topic and allowed to teach
        "strengths": {
            "$elemMatch": {
                "topic_id": topic_id,
                "can_teach_others": True
            }
        },
        # Must not be the learner themselves
        "student_id": {"$ne": exclude_student_id},
        # Must not be in an active session right now
        "current_session_id": None
    })
    
    return teacher

async def create_pair_session(learner_id: str, teacher_id: str, topic_id: str, topic_name: str) -> dict:
    """Creates a new pair session document in MongoDB."""
    db = get_db()
    
    session_id = f"PS-{uuid.uuid4().hex[:8].upper()}"
    
    session_doc = {
        "session_id": session_id,
        "teacher_id": teacher_id,
        "learner_id": learner_id,
        "topic_id": topic_id,
        "topic_name": topic_name,
        "status": "active",
        "created_at": datetime.utcnow(),
        "completed_at": None,
        "questions_asked": 0,
        "correct_answers": 0,
        "hints_used_by_learner": 0,
        "hints_used_by_teacher": 0,
        "help_requests": 0,
        "performance_score": None,
        "decision": None,
        "question_log": []
    }
    
    await db.pair_sessions.insert_one(session_doc)
    
    # Mark both students as busy
    await db.students.update_many(
        {"student_id": {"$in": [learner_id, teacher_id]}},
        {"$set": {"current_session_id": session_id}}
    )
    
    return session_doc

async def start_pairing_for_student(student_id: str) -> dict:
    """
    Main entry point: given a student, find their current weak topic,
    find a teacher for it, and create a session.
    """
    db = get_db()
    
    student = await db.students.find_one({"student_id": student_id})
    if not student:
        return {"error": "Student not found"}
    
    if student["current_session_id"]:
        return {"error": "Student already in a session"}
    
    topic_id = student["current_weak_topic"]
    if not topic_id:
        return {"message": "No weak topics remaining — student is complete!"}
    
    # Find the topic name from weaknesses list
    topic_name = next(
        (w["topic"] for w in student["weaknesses"] if w["topic_id"] == topic_id),
        topic_id
    )
    
    teacher = await find_teacher_for_topic(topic_id, student_id)
    if not teacher:
        return {"error": f"No available teacher for topic {topic_name} right now. Try again later."}
    
    session = await create_pair_session(
        learner_id=student_id,
        teacher_id=teacher["student_id"],
        topic_id=topic_id,
        topic_name=topic_name
    )
    
    return {
        "session_id": session["session_id"],
        "learner_id": student_id,
        "teacher_id": teacher["student_id"],
        "topic": topic_name
    }


def _select_primary_gap(knowledge_gaps: list[dict]) -> dict | None:
    if not knowledge_gaps:
        return None

    def gap_priority(gap: dict):
        gap_type_score = 0 if gap.get("gap_type") == "FUNDAMENTAL_GAP" else 1
        return (gap_type_score, -float(gap.get("confidence", 0)))

    return min(knowledge_gaps, key=gap_priority)


def _topic_matches(topic_a: str, topic_b: str) -> bool:
    return topic_a.strip().lower() == topic_b.strip().lower()


def _teacher_strength_score(teacher_strength: dict, learner_topic_id: str, learner_topic: str) -> int:
    if teacher_strength.get("topic_id") == learner_topic_id or _topic_matches(teacher_strength.get("topic", ""), learner_topic):
        mastery_level = teacher_strength.get("mastery_level", "").lower()
        mastery_bonus = 30 if mastery_level == "advanced" else 15 if mastery_level == "proficient" else 5
        return 70 + int(teacher_strength.get("confidence", 0) * 25) + mastery_bonus
    return 0


def _compatibility_score(learner_gap: dict, teacher_strengths: list[dict]) -> int:
    learner_topic = learner_gap.get("topic", "")
    learner_topic_id = learner_gap.get("topic_id", "")
    best_strength = 0
    for strength in teacher_strengths:
        best_strength = max(best_strength, _teacher_strength_score(strength, learner_topic_id, learner_topic))
    if best_strength == 0:
        return 0
    gap_weight = 40 if learner_gap.get("gap_type") == "FUNDAMENTAL_GAP" else 15
    return best_strength + gap_weight


def _hungarian_algorithm(cost_matrix: list[list[int]]) -> list[int]:
    n = len(cost_matrix)
    if n == 0:
        return []

    u = [0] * (n + 1)
    v = [0] * (n + 1)
    p = [0] * (n + 1)
    way = [0] * (n + 1)

    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = [float('inf')] * (n + 1)
        used = [False] * (n + 1)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = float('inf')
            j1 = 0
            for j in range(1, n + 1):
                if not used[j]:
                    cur = cost_matrix[i0 - 1][j - 1] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j] = cur
                        way[j] = j0
                    if minv[j] < delta:
                        delta = minv[j]
                        j1 = j
            for j in range(n + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while True:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
            if j0 == 0:
                break

    assignment = [-1] * n
    for j in range(1, n + 1):
        if p[j] != 0:
            assignment[p[j] - 1] = j - 1
    return assignment


async def match_students_using_hungarian(students: list[dict]) -> dict:
    learners = []
    teachers = []

    for student in students:
        if not isinstance(student, dict):
            continue
        mastery_profile = student.get("mastery_profile", {})
        if not mastery_profile:
            continue

        primary_gap = _select_primary_gap(mastery_profile.get("knowledge_gaps", []))
        strengths = mastery_profile.get("strengths", [])

        if primary_gap:
            learners.append({
                "student_id": student.get("student_id"),
                "primary_gap": primary_gap
            })

        teacher_strengths = [s for s in strengths if s.get("can_teach_others")]
        if teacher_strengths:
            teachers.append({
                "student_id": student.get("student_id"),
                "strengths": teacher_strengths
            })

    if not learners or not teachers:
        return {
            "pairs": [],
            "unmatched_learners": [l["student_id"] for l in learners],
            "unmatched_teachers": [t["student_id"] for t in teachers],
            "message": "No valid learners or no available teachers for Hungarian matching."
        }

    matrix_size = max(len(learners), len(teachers))
    max_cost = 1000
    cost_matrix = [[max_cost] * matrix_size for _ in range(matrix_size)]

    for i, learner in enumerate(learners):
        for j, teacher in enumerate(teachers):
            if learner["student_id"] == teacher["student_id"]:
                continue
            score = _compatibility_score(learner["primary_gap"], teacher["strengths"])
            if score > 0:
                cost_matrix[i][j] = max_cost - score

    assignment = _hungarian_algorithm(cost_matrix)
    pairs = []
    assigned_teachers = set()
    assigned_learners = set()

    for learner_index, teacher_index in enumerate(assignment):
        if learner_index >= len(learners) or teacher_index >= len(teachers):
            continue
        if teacher_index < 0:
            continue
        if cost_matrix[learner_index][teacher_index] >= max_cost:
            continue

        learner = learners[learner_index]
        teacher = teachers[teacher_index]
        assigned_learners.add(learner["student_id"])
        assigned_teachers.add(teacher["student_id"])

        pairs.append({
            "learner_id": learner["student_id"],
            "learner_topic": learner["primary_gap"].get("topic"),
            "learner_gap_type": learner["primary_gap"].get("gap_type"),
            "teacher_id": teacher["student_id"],
            "teacher_strengths": teacher["strengths"],
            "compatibility_score": max_cost - cost_matrix[learner_index][teacher_index]
        })

    unmatched_learners = [l["student_id"] for l in learners if l["student_id"] not in assigned_learners]
    unmatched_teachers = [t["student_id"] for t in teachers if t["student_id"] not in assigned_teachers]

    return {
        "pairs": pairs,
        "unmatched_learners": unmatched_learners,
        "unmatched_teachers": unmatched_teachers,
        "summary": {
            "learners_considered": len(learners),
            "teachers_considered": len(teachers),
            "pairs_created": len(pairs)
        }
    }
