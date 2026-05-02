from datetime import datetime
from typing import List, Dict, Any, Optional, Set, Tuple
import numpy as np
from scipy.optimize import linear_sum_assignment
from loguru import logger
from app.core.database import get_db
from app.models.models import PairingType, SessionStatus
from app.utils.helpers import (
    calculate_compatibility_score,
    calculate_priority_score,
    generate_session_id,
    generate_batch_id,
    generate_queue_id,
    sort_knowledge_gaps,
)


# ─── Low-level helpers ────────────────────────────────────────────────────────

def _get_strength_for_topic(student: Dict, topic_id: str) -> Optional[Dict]:
    for s in student.get("mastery_profile", {}).get("strengths", []):
        if s.get("topic_id") == topic_id:
            return s
    return None


def _get_gap_for_topic(student: Dict, topic_id: str) -> Optional[Dict]:
    for g in student.get("mastery_profile", {}).get("knowledge_gaps", []):
        if g.get("topic_id") == topic_id:
            return g
    return None


def _student_can_teach_topic(student: Dict, topic_id: str) -> bool:
    s = _get_strength_for_topic(student, topic_id)
    return s is not None and s.get("can_teach_others", False)


def _student_needs_topic(student: Dict, topic_id: str) -> bool:
    return _get_gap_for_topic(student, topic_id) is not None


def _find_reciprocal_topic(learner: Dict, teacher: Dict) -> Optional[Dict]:
    """
    Check if the learner can teach the teacher something in return.
    Returns the learner's strength record if a reciprocal topic exists.
    """
    teacher_gap_ids = {
        g["topic_id"]
        for g in teacher.get("mastery_profile", {}).get("knowledge_gaps", [])
    }
    for s in learner.get("mastery_profile", {}).get("strengths", []):
        if s.get("can_teach_others") and s.get("topic_id") in teacher_gap_ids:
            return s
    return None


def _sort_topics_by_scarcity(
    topic_map: Dict[str, str], all_students: List[Dict]
) -> List[Tuple[str, str]]:
    """
    Sort topics so scarce-teacher topics are processed FIRST.
    This prevents high-supply teachers from being consumed by easy topics
    before harder-to-fill topics are matched.
    Sort key: teacher/learner ratio ascending, then learner count descending.
    """
    scored = []
    for topic_id, topic_name in topic_map.items():
        learners = [s for s in all_students if _student_needs_topic(s, topic_id)]
        learner_ids = {l["student_id"] for l in learners}
        teachers = [
            s for s in all_students
            if _student_can_teach_topic(s, topic_id)
            and s["student_id"] not in learner_ids
        ]
        n_l = len(learners)
        n_t = len(teachers)
        ratio = n_t / max(n_l, 1)
        scored.append((topic_id, topic_name, n_l, n_t, ratio))
    scored.sort(key=lambda x: (x[4], -x[2]))
    return [(tid, tname) for tid, tname, _, _, _ in scored]


# ─── Core auto-pairing engine ─────────────────────────────────────────────────

async def run_full_pairing() -> Dict[str, Any]:
    """
    System-wide auto-pairing across ALL students and ALL topics.

    Key design decisions
    --------------------
    * TWO separate reservation sets:
        reserved_as_learner  — student is already the learner in a session
        reserved_as_teacher  — student is already the teacher in a session
      This allows student A to be a learner for topic X AND simultaneously
      a teacher for topic Y in two different sessions.

    * Topic processing order: sorted by teacher scarcity (fewest teachers
      per learner processed first), so scarce teachers are not wasted on
      topics that have plenty of teachers.

    * Empty-matrix guard: if learners or teachers list is empty after
      filtering, the topic is skipped (avoids numpy crash).

    Steps
    -----
    1. Load every free student (current_session_id=None, status!=complete).
    2. Build topic map and sort by scarcity.
    3. Per topic:
         a. Learners  = need this topic AND not yet reserved_as_learner
         b. Teachers  = can teach this topic AND not yet reserved_as_teacher
                        AND not in learner list for this same topic
         c. Skip if either list is empty
         d. Build cost matrix (cost = -compatibility_score), run Hungarian algo
         e. For each valid match: detect RECIPROCAL, create sessions, reserve
    4. Any student still un-reserved as learner AND has gaps → auto-queue
    5. Save batch record, return full summary
    """
    db = get_db()

    # 1. Collect every student_id that has already appeared in ANY pair session
    #    (as learner OR teacher, any status).  These are "already processed"
    #    students — we must never re-pair or re-queue them.
    existing_sessions = await db.pair_sessions.find(
        {}, {"learner_id": 1, "teacher_id": 1, "_id": 0}
    ).to_list(length=None)
    already_paired_ids: Set[str] = set()
    for s in existing_sessions:
        if s.get("learner_id"):
            already_paired_ids.add(s["learner_id"])
        if s.get("teacher_id"):
            already_paired_ids.add(s["teacher_id"])

    # Also exclude students already in the waiting queue
    existing_queue = await db.waiting_queue.find(
        {"status": "waiting"}, {"student_id": 1, "_id": 0}
    ).to_list(length=None)
    already_queued_ids: Set[str] = {e["student_id"] for e in existing_queue}

    already_processed_ids = already_paired_ids | already_queued_ids

    # Load only NEW students — those never seen in any session or queue
    all_students: List[Dict] = await db.students.find(
        {
            "student_id": {"$nin": list(already_processed_ids)},
            "status": {"$ne": "complete"},
        },
        {"_id": 0},
    ).to_list(length=None)

    if not all_students:
        return {
            "batch_id": generate_batch_id(),
            "message": "No new students to pair. All students have already been processed.",
            "sessions_created": 0,
            "students_paired": 0,
            "students_queued": 0,
            "paired": [],
            "sessions": [],
            "waiting_queue": [],
        }

    # Separate reservation sets — a student CAN be both a teacher for one
    # topic and a learner for another simultaneously
    reserved_as_learner: Set[str] = set()
    reserved_as_teacher: Set[str] = set()

    all_sessions_created: List[Dict] = []
    pairing_details: List[Dict] = []

    # 2. Collect all topics and sort by scarcity
    topic_map: Dict[str, str] = {}
    for stu in all_students:
        for gap in stu.get("mastery_profile", {}).get("knowledge_gaps", []):
            tid = gap.get("topic_id")
            if tid:
                topic_map[tid] = gap.get("topic", tid)

    sorted_topics = _sort_topics_by_scarcity(topic_map, all_students)

    # 3. Process each topic
    for topic_id, topic_name in sorted_topics:

        # a. Learners: need this topic, not yet in a learner slot
        learners = [
            s for s in all_students
            if _student_needs_topic(s, topic_id)
            and s["student_id"] not in reserved_as_learner
        ]
        if not learners:
            continue

        learner_ids = {l["student_id"] for l in learners}

        # b. Teachers: can teach, not yet in a teacher slot, not also a
        #    learner for this SAME topic
        teachers = [
            s for s in all_students
            if _student_can_teach_topic(s, topic_id)
            and s["student_id"] not in reserved_as_teacher
            and s["student_id"] not in learner_ids
        ]

        # c. Empty-matrix guard — no teachers means these learners get queued
        if not teachers:
            logger.info(
                f"No available teachers for '{topic_name}' "
                f"({len(learners)} learner(s) will be queued)."
            )
            continue

        # d. Build cost matrix (rows = learners, cols = teachers, square-padded)
        n_l = len(learners)
        n_t = len(teachers)
        size = max(n_l, n_t)
        cost_matrix = np.full((size, size), 1000.0)

        for i, learner in enumerate(learners):
            gap = _get_gap_for_topic(learner, topic_id)
            if not gap:
                continue
            learner_mastery = gap.get("mastery_score") or 0.0
            for j, teacher in enumerate(teachers):
                strength = _get_strength_for_topic(teacher, topic_id)
                if not strength:
                    continue
                score = calculate_compatibility_score(
                    teacher_confidence=strength.get("confidence", 0.5),
                    teacher_mastery_level=strength.get("mastery_level", "proficient"),
                    gap_type=gap.get("gap_type", "PARTIAL_GAP"),
                    learner_mastery_score=learner_mastery,
                    learner_confidence=gap.get("confidence", 0.5),
                )
                cost_matrix[i][j] = -score  # negate: algorithm minimises

        row_ind, col_ind = linear_sum_assignment(cost_matrix)

        # e. Process each match from the algorithm
        for r, c in zip(row_ind, col_ind):
            # Skip padded rows/cols
            if r >= n_l or c >= n_t:
                continue
            # Skip if no valid score (still at penalty value)
            if cost_matrix[r][c] >= 999:
                continue

            learner = learners[r]
            teacher = teachers[c]

            # Re-check in case reserved by an earlier match in this same loop
            if learner["student_id"] in reserved_as_learner:
                continue
            if teacher["student_id"] in reserved_as_teacher:
                continue

            compatibility = round(-cost_matrix[r][c], 2)
            gap = _get_gap_for_topic(learner, topic_id)
            learner_mastery = gap.get("mastery_score") or 0.0

            reciprocal_topic = _find_reciprocal_topic(learner, teacher)

            if reciprocal_topic:
                # ── RECIPROCAL: two sessions ──────────────────────────
                s1 = await _create_pair_session(
                    teacher_id=teacher["student_id"],
                    learner_id=learner["student_id"],
                    topic_id=topic_id,
                    topic_name=topic_name,
                    pairing_type=PairingType.RECIPROCAL,
                    learner_initial_mastery=learner_mastery,
                )
                if s1 is None:
                    # Duplicate — active session already exists, skip
                    reserved_as_learner.add(learner["student_id"])
                    reserved_as_teacher.add(teacher["student_id"])
                    continue
                rec_gap = _get_gap_for_topic(teacher, reciprocal_topic["topic_id"])
                rec_mastery = rec_gap.get("mastery_score") or 0.0 if rec_gap else 0.0
                s2 = await _create_pair_session(
                    teacher_id=learner["student_id"],
                    learner_id=teacher["student_id"],
                    topic_id=reciprocal_topic["topic_id"],
                    topic_name=reciprocal_topic["topic"],
                    pairing_type=PairingType.RECIPROCAL,
                    learner_initial_mastery=rec_mastery,
                )
                if s2 is None:
                    s2 = s1  # fallback: point to s1 if reverse already exists
                await _reserve_student(learner["student_id"], s1["session_id"])
                await _reserve_student(teacher["student_id"], s1["session_id"])
                # In s1: learner=learner, teacher=teacher
                reserved_as_learner.add(learner["student_id"])
                reserved_as_teacher.add(teacher["student_id"])
                # In s2 roles swap: learner becomes teacher, teacher becomes learner
                reserved_as_teacher.add(learner["student_id"])
                reserved_as_learner.add(teacher["student_id"])

                all_sessions_created.extend([s1, s2])
                pairing_details.append({
                    "type": "RECIPROCAL",
                    "learner_id": learner["student_id"],
                    "teacher_id": teacher["student_id"],
                    "topic_id": topic_id,
                    "topic_name": topic_name,
                    "session_id": s1["session_id"],
                    "reciprocal_topic_id": reciprocal_topic["topic_id"],
                    "reciprocal_topic_name": reciprocal_topic["topic"],
                    "reciprocal_session_id": s2["session_id"],
                    "compatibility_score": compatibility,
                })

            else:
                # ── ONE_WAY ───────────────────────────────────────────
                s = await _create_pair_session(
                    teacher_id=teacher["student_id"],
                    learner_id=learner["student_id"],
                    topic_id=topic_id,
                    topic_name=topic_name,
                    pairing_type=PairingType.ONE_WAY,
                    learner_initial_mastery=learner_mastery,
                )
                if s is None:
                    # Duplicate — active session already exists, skip
                    reserved_as_learner.add(learner["student_id"])
                    reserved_as_teacher.add(teacher["student_id"])
                    continue
                await _reserve_student(learner["student_id"], s["session_id"])
                await _reserve_student(teacher["student_id"], s["session_id"])
                reserved_as_learner.add(learner["student_id"])
                reserved_as_teacher.add(teacher["student_id"])

                all_sessions_created.append(s)
                pairing_details.append({
                    "type": "ONE_WAY",
                    "learner_id": learner["student_id"],
                    "teacher_id": teacher["student_id"],
                    "topic_id": topic_id,
                    "topic_name": topic_name,
                    "session_id": s["session_id"],
                    "compatibility_score": compatibility,
                })

    # 4. Auto-queue every student who:
    #    - has at least one knowledge gap
    #    - was NOT reserved as a learner (meaning no one taught them)
    queued: List[Dict] = []
    for stu in all_students:
        sid = stu["student_id"]

        # Already getting taught — skip
        if sid in reserved_as_learner:
            continue

        # No gaps — nothing to learn, skip
        gaps = stu.get("mastery_profile", {}).get("knowledge_gaps", [])
        if not gaps:
            continue

        # Race-condition guard: confirm still free in DB
        fresh = await db.students.find_one({"student_id": sid}, {"_id": 0})
        if fresh and fresh.get("current_session_id"):
            continue

        # Duplicate queue guard: skip if already in waiting queue for any gap topic
        already_waiting = await db.waiting_queue.find_one({
            "student_id": sid,
            "status": "waiting",
        })
        if already_waiting:
            continue

        # Queue for highest-priority gap
        sorted_gaps = sort_knowledge_gaps(list(gaps))
        topic_id_q = stu.get("current_weak_topic") or sorted_gaps[0].get("topic_id")
        gap_q = _get_gap_for_topic(stu, topic_id_q)
        topic_name_q = gap_q.get("topic", topic_id_q) if gap_q else topic_id_q

        entry = await _auto_add_to_waiting_queue(sid, topic_id_q, topic_name_q, gap_q)
        queued.append(entry)

    # 5. Persist batch record
    batch_id = generate_batch_id()
    await db.batch_pairing_records.insert_one({
        "batch_id": batch_id,
        "created_at": datetime.utcnow(),
        "topics_processed": list(topic_map.keys()),
        "sessions_created": len(all_sessions_created),
        "students_paired": len(reserved_as_learner),
        "students_queued": len(queued),
        "details": pairing_details,
    })

    logger.info(
        f"Pairing complete — sessions={len(all_sessions_created)}, "
        f"paired={len(reserved_as_learner)}, queued={len(queued)}"
    )
    return {
        "batch_id": batch_id,
        "sessions_created": len(all_sessions_created),
        "students_paired": len(reserved_as_learner),
        "students_queued": len(queued),
        "paired": pairing_details,
        "sessions": all_sessions_created,
        "waiting_queue": queued,
    }


# ─── Read helpers ─────────────────────────────────────────────────────────────

async def get_all_paired_sessions() -> List[Dict]:
    """Return every pair session saved in DB, newest first."""
    db = get_db()
    return await db.pair_sessions.find(
        {}, {"_id": 0}
    ).sort("created_at", -1).to_list(length=None)


async def get_waiting_queue_students() -> List[Dict]:
    """Return all students in the waiting queue, highest priority first."""
    db = get_db()
    return await db.waiting_queue.find(
        {"status": "waiting"}, {"_id": 0}
    ).sort("priority_score", -1).to_list(length=None)


# ─── Internal DB helpers ──────────────────────────────────────────────────────

async def get_available_learners_for_topic(topic_id: str) -> List[Dict]:
    db = get_db()
    return await db.students.find(
        {
            "mastery_profile.knowledge_gaps.topic_id": topic_id,
            "current_session_id": None,
            "status": {"$ne": "complete"},
        },
        {"_id": 0},
    ).to_list(length=None)


async def get_available_teachers_for_topic(
    topic_id: str, exclude_ids: List[str] = None
) -> List[Dict]:
    db = get_db()
    query = {
        "mastery_profile.strengths": {
            "$elemMatch": {"topic_id": topic_id, "can_teach_others": True}
        },
        "current_session_id": None,
        "status": {"$ne": "complete"},
    }
    if exclude_ids:
        query["student_id"] = {"$nin": exclude_ids}
    return await db.students.find(query, {"_id": 0}).to_list(length=None)


async def _active_session_exists(learner_id: str, topic_id: str) -> bool:
    """Return True if an active session already exists for this learner+topic.
    Prevents duplicate sessions when pairing is run more than once."""
    db = get_db()
    existing = await db.pair_sessions.find_one({
        "learner_id": learner_id,
        "topic_id": topic_id,
        "status": {"$in": ["active", "waiting"]},
    })
    return existing is not None


async def _create_pair_session(
    teacher_id: str,
    learner_id: str,
    topic_id: str,
    topic_name: str,
    pairing_type: PairingType,
    learner_initial_mastery: float = 0.0,
) -> Optional[Dict]:
    """Create and persist a pair session.
    Returns None if a duplicate active session already exists for this
    learner + topic — prevents duplicates on repeated pairing runs."""
    if await _active_session_exists(learner_id, topic_id):
        logger.warning(
            f"Duplicate skipped: active session already exists for "
            f"learner={learner_id} topic={topic_id}"
        )
        return None
    db = get_db()
    session_id = generate_session_id()
    doc = {
        "session_id": session_id,
        "teacher_id": teacher_id,
        "learner_id": learner_id,
        "topic_id": topic_id,
        "topic_name": topic_name,
        "pairing_type": pairing_type.value,
        "status": SessionStatus.ACTIVE.value,
        "created_at": datetime.utcnow(),
        "completed_at": None,
        "questions_asked": 0,
        "correct_answers": 0,
        "hints_used_by_learner": 0,
        "hints_used_by_teacher": 0,
        "help_requests": 0,
        "question_log": [],
        "performance_score": None,
        "current_bloom_level": 1,
        "consecutive_correct": 0,
        "consecutive_incorrect": 0,
        "current_question_id": None,
        "learner_initial_mastery": learner_initial_mastery,
        "teacher_score": None,
    }
    await db.pair_sessions.insert_one(doc)
    doc.pop("_id", None)
    logger.info(
        f"Session {session_id}: {teacher_id} -> {learner_id} "
        f"[{topic_name}] ({pairing_type.value})"
    )
    return doc


async def _reserve_student(student_id: str, session_id: str):
    db = get_db()
    await db.students.update_one(
        {"student_id": student_id},
        {
            "$set": {
                "current_session_id": session_id,
                "status": "in_session",
                "updated_at": datetime.utcnow(),
            },
            "$push": {"session_history": session_id},
        },
    )


async def _auto_add_to_waiting_queue(
    student_id: str,
    topic_id: str,
    topic_name: str,
    gap: Optional[Dict],
) -> Dict:
    """
    Persist a waiting-queue entry for a student who could not be matched.
    If already queued for this topic, refresh priority score only.
    """
    db = get_db()
    gap_type = gap.get("gap_type", "PARTIAL_GAP") if gap else "PARTIAL_GAP"
    now = datetime.utcnow()

    existing = await db.waiting_queue.find_one(
        {"student_id": student_id, "topic_id": topic_id, "status": "waiting"},
        {"_id": 0},
    )
    attempts = existing.get("attempts", 0) if existing else 0
    priority = calculate_priority_score(gap_type, now, attempts)

    if existing:
        await db.waiting_queue.update_one(
            {"student_id": student_id, "topic_id": topic_id, "status": "waiting"},
            {"$set": {"priority_score": priority}},
        )
        logger.info(f"Waiting queue priority refreshed: {student_id} / {topic_id}")
        return {
            "queue_id": existing["queue_id"],
            "student_id": student_id,
            "topic_id": topic_id,
            "topic_name": topic_name,
            "gap_type": gap_type,
            "priority_score": round(priority, 2),
            "status": "waiting",
            "already_queued": True,
        }

    queue_id = generate_queue_id()
    await db.waiting_queue.insert_one({
        "queue_id": queue_id,
        "student_id": student_id,
        "topic_id": topic_id,
        "topic_name": topic_name,
        "gap_type": gap_type,
        "waiting_since": now,
        "priority_score": priority,
        "attempts": attempts,
        "status": "waiting",
    })
    logger.info(
        f"Student {student_id} auto-queued for '{topic_name}' "
        f"(queue_id={queue_id}, priority={priority:.1f})"
    )
    return {
        "queue_id": queue_id,
        "student_id": student_id,
        "topic_id": topic_id,
        "topic_name": topic_name,
        "gap_type": gap_type,
        "priority_score": round(priority, 2),
        "status": "waiting",
        "already_queued": False,
    }


# ─── Backward-compat alias ────────────────────────────────────────────────────

async def batch_match_all_topics() -> Dict[str, Any]:
    return await run_full_pairing()