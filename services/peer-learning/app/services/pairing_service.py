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
from app.services.notification_service import send_pairing_notification, send_queue_notification


# ─── Low-level helpers ────────────────────────────────────────────────────────

def _get_strength_for_topic(student: Dict, topic_id: str, topic_name: Optional[str] = None) -> Optional[Dict]:
    for s in student.get("mastery_profile", {}).get("strengths", []):
        if s.get("topic_id") == topic_id:
            return s
    if topic_name:
        for s in student.get("mastery_profile", {}).get("strengths", []):
            if s.get("topic") == topic_name:
                return s
    return None


def _get_gap_for_topic(student: Dict, topic_id: str, topic_name: Optional[str] = None) -> Optional[Dict]:
    for g in student.get("mastery_profile", {}).get("knowledge_gaps", []):
        if g.get("topic_id") == topic_id:
            return g
    if topic_name:
        for g in student.get("mastery_profile", {}).get("knowledge_gaps", []):
            if g.get("topic") == topic_name:
                return g
    return None


def _student_can_teach_topic(student: Dict, topic_id: str, topic_name: Optional[str] = None) -> bool:
    s = _get_strength_for_topic(student, topic_id, topic_name)
    return s is not None and s.get("can_teach_others", False)


def _student_needs_topic(student: Dict, topic_id: str, topic_name: Optional[str] = None) -> bool:
    return _get_gap_for_topic(student, topic_id, topic_name) is not None


def _sort_topics_by_scarcity(
    topic_map: Dict[str, str], all_students: List[Dict]
) -> List[Tuple[str, str]]:
    """
    Sort topics so scarce-teacher topics are processed FIRST.
    """
    scored = []
    for topic_id, topic_name in topic_map.items():
        learners = [s for s in all_students if _student_needs_topic(s, topic_id, topic_name)]
        learner_ids = {l["student_id"] for l in learners}
        teachers = [
            s for s in all_students
            if _student_can_teach_topic(s, topic_id, topic_name)
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
    System-wide auto-pairing with step-based priority:
    1. Pair new students among themselves.
    2. Match remaining new students with the waiting queue.
    3. Auto-queue final remainders.
    """
    db = get_db()

    # 1. Load existing pair session participants
    existing_sessions = await db.pair_sessions.find(
        {}, {"learner_id": 1, "teacher_id": 1, "_id": 0}
    ).to_list(length=None)
    already_paired_ids: Set[str] = set()
    for s in existing_sessions:
        if s.get("learner_id"):
            already_paired_ids.add(s["learner_id"])
        if s.get("teacher_id"):
            already_paired_ids.add(s["teacher_id"])

    # Exclude students who are/were in group sessions
    existing_groups = await db.group_sessions.find(
        {}, {"members.student_id": 1, "_id": 0}
    ).to_list(length=None)
    for g in existing_groups:
        for member in g.get("members", []):
            mid = member.get("student_id")
            if mid:
                already_paired_ids.add(mid)

    # 2. Load waiting queue students with full profiles
    waiting_queue = await db.waiting_queue.find(
        {"status": "waiting"}, {"_id": 0}
    ).to_list(length=None)

    queue_students: Dict[str, Dict] = {}
    for entry in waiting_queue:
        sid = entry["student_id"]
        student = await db.students.find_one({"student_id": sid}, {"_id": 0})
        if student:
            queue_students[sid] = {
                "student": student,
                "entry": entry,
                "topic_id": entry["topic_id"],
                "topic_name": entry["topic_name"],
            }

    # 3. Load NEW students — not in sessions and not in queue
    queue_student_ids = set(queue_students.keys())
    already_processed_ids = already_paired_ids | queue_student_ids

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
            "message": "No new students to pair.",
            "sessions_created": 0, "students_paired": 0, "students_queued": 0,
            "waiting_queue_matched": 0,
            "paired": [], "sessions": [], "waiting_queue": [],
        }

    reserved_as_learner: Set[str] = set()
    reserved_as_teacher: Set[str] = set()
    all_sessions_created: List[Dict] = []
    pairing_details: List[Dict] = []
    queue_matched_students: List[str] = []
    new_students_matched_with_queue: Set[str] = set()

    # ─── STEP 1: Normal pairing for new students (intra-batch) ────────────────

    topic_map: Dict[str, str] = {}
    for stu in all_students:
        for gap in stu.get("mastery_profile", {}).get("knowledge_gaps", []):
            tid = gap.get("topic_id")
            if tid:
                topic_map[tid] = gap.get("topic", tid)

    sorted_topics = _sort_topics_by_scarcity(topic_map, all_students)

    for topic_id, topic_name in sorted_topics:
        learners = [
            s for s in all_students
            if _student_needs_topic(s, topic_id, topic_name)
            and s["student_id"] not in reserved_as_learner
            and s["student_id"] not in reserved_as_teacher
        ]
        if not learners:
            continue

        learner_ids = {l["student_id"] for l in learners}

        teachers = [
            s for s in all_students
            if _student_can_teach_topic(s, topic_id, topic_name)
            and s["student_id"] not in reserved_as_teacher
            and s["student_id"] not in reserved_as_learner
            and s["student_id"] not in learner_ids
        ]
        if not teachers:
            continue

        n_l = len(learners)
        n_t = len(teachers)
        size = max(n_l, n_t)
        cost_matrix = np.full((size, size), 1000.0)

        for i, learner in enumerate(learners):
            gap = _get_gap_for_topic(learner, topic_id, topic_name)
            if not gap:
                continue
            learner_mastery = gap.get("mastery_score") or 0.0
            for j, teacher in enumerate(teachers):
                strength = _get_strength_for_topic(teacher, topic_id, topic_name)
                if not strength:
                    continue
                score = calculate_compatibility_score(
                    teacher_confidence=strength.get("confidence", 0.5),
                    teacher_mastery_level=strength.get("mastery_level", "proficient"),
                    gap_type=gap.get("gap_type", "PARTIAL_GAP"),
                    learner_mastery_score=learner_mastery,
                    learner_confidence=gap.get("confidence", 0.5),
                )
                cost_matrix[i][j] = -score

        row_ind, col_ind = linear_sum_assignment(cost_matrix)

        for r, c in zip(row_ind, col_ind):
            if r >= n_l or c >= n_t or cost_matrix[r][c] >= 999:
                continue
            learner = learners[r]
            teacher = teachers[c]
            
            # Check specific roles (A student can be a learner for one topic and a teacher for another)
            if learner["student_id"] in reserved_as_learner:
                continue
            if teacher["student_id"] in reserved_as_teacher:
                continue

            compatibility = round(-cost_matrix[r][c], 2)
            gap = _get_gap_for_topic(learner, topic_id, topic_name)
            learner_mastery = gap.get("mastery_score") or 0.0

            s = await _create_pair_session(
                teacher_id=teacher["student_id"],
                learner_id=learner["student_id"],
                topic_id=topic_id, topic_name=topic_name,
                pairing_type=PairingType.ONE_WAY,
                learner_initial_mastery=learner_mastery,
            )
            if s is None:
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
                "topic_id": topic_id, "topic_name": topic_name,
                "session_id": s["session_id"],
                "compatibility_score": compatibility,
            })
            await send_pairing_notification(
                student_id=learner["student_id"], session_id=s["session_id"],
                topic_name=topic_name, role="learner", peer_id=teacher["student_id"]
            )
            await send_pairing_notification(
                student_id=teacher["student_id"], session_id=s["session_id"],
                topic_name=topic_name, role="teacher", peer_id=learner["student_id"]
            )

    # ─── STEP 2: Match remaining new students with waiting queue ─────────────

    logger.info(
        f"Queue matching: {len(all_students)} new students, {len(queue_students)} queue students"
    )

    for new_stu in all_students:
        new_sid = new_stu["student_id"]
        if new_sid in reserved_as_teacher:
            continue
            
        # 2a. New students who can teach -> queue learners
        for strength in new_stu.get("mastery_profile", {}).get("strengths", []):
            if not strength.get("can_teach_others"):
                continue
            if new_sid in reserved_as_teacher:
                break
            topic_id = strength["topic_id"]
            topic_name = strength.get("topic", topic_id)

            for q_sid, q_info in queue_students.items():
                if q_sid in queue_matched_students or new_sid in reserved_as_teacher:
                    continue
                if q_info["topic_id"] != topic_id and q_info["topic_name"] != topic_name:
                    continue
                queue_learner = q_info["student"]
                gap = _get_gap_for_topic(queue_learner, topic_id, topic_name)
                if not gap:
                    continue

                logger.info(f"Queue match: {new_sid}(teacher) -> {q_sid}(learner) for {topic_name}")
                learner_mastery = gap.get("mastery_score") or 0.0
                s = await _create_pair_session(
                    teacher_id=new_sid, learner_id=q_sid,
                    topic_id=topic_id, topic_name=topic_name,
                    pairing_type=PairingType.ONE_WAY,
                    learner_initial_mastery=learner_mastery,
                )
                if s is None:
                    continue

                reserved_as_learner.add(q_sid)
                reserved_as_teacher.add(new_sid)
                new_students_matched_with_queue.add(new_sid)
                queue_matched_students.append(q_sid)

                # IMMEDIATE Queue Removal to prevent stale entries
                await db.waiting_queue.delete_many({"student_id": q_sid, "status": "waiting"})
                logger.info(f"Immediately removed {q_sid} from queue after match")

                await _reserve_student(q_sid, s["session_id"])
                await _reserve_student(new_sid, s["session_id"])
                all_sessions_created.append(s)
                pairing_details.append({
                    "type": "QUEUE_MATCH(new_teaches_queue_learner)",
                    "learner_id": q_sid, "teacher_id": new_sid,
                    "topic_id": topic_id, "topic_name": topic_name,
                    "session_id": s["session_id"],
                })
                await send_pairing_notification(
                    student_id=q_sid, session_id=s["session_id"],
                    topic_name=topic_name, role="learner", peer_id=new_sid
                )
                await send_pairing_notification(
                    student_id=new_sid, session_id=s["session_id"],
                    topic_name=topic_name, role="teacher", peer_id=q_sid
                )
                break

    for new_stu in all_students:
        new_sid = new_stu["student_id"]
        if new_sid in reserved_as_learner:
            continue
            
        # 2b. New students who need a topic -> queue students who can teach
        for gap in new_stu.get("mastery_profile", {}).get("knowledge_gaps", []):
            topic_id = gap["topic_id"]
            topic_name = gap.get("topic", topic_id)
            if new_sid in reserved_as_learner:
                break

            for q_sid, q_info in queue_students.items():
                if q_sid in queue_matched_students or q_sid in reserved_as_teacher or new_sid in reserved_as_learner:
                    continue
                queue_student = q_info["student"]
                if not _student_can_teach_topic(queue_student, topic_id, topic_name):
                    continue

                logger.info(f"Queue match: {q_sid}(teacher) -> {new_sid}(learner) for {topic_name}")
                learner_mastery = gap.get("mastery_score") or 0.0
                s = await _create_pair_session(
                    teacher_id=q_sid, learner_id=new_sid,
                    topic_id=topic_id, topic_name=topic_name,
                    pairing_type=PairingType.ONE_WAY,
                    learner_initial_mastery=learner_mastery,
                )
                if s is None:
                    continue

                reserved_as_learner.add(new_sid)
                reserved_as_teacher.add(q_sid)
                new_students_matched_with_queue.add(new_sid)
                queue_matched_students.append(q_sid)

                # IMMEDIATE Queue Removal to prevent stale entries
                await db.waiting_queue.delete_many({"student_id": q_sid, "status": "waiting"})
                logger.info(f"Immediately removed {q_sid} from queue after match")

                await _reserve_student(new_sid, s["session_id"])
                await _reserve_student(q_sid, s["session_id"])
                all_sessions_created.append(s)
                pairing_details.append({
                    "type": "QUEUE_MATCH(queue_teaches_new_learner)",
                    "learner_id": new_sid, "teacher_id": q_sid,
                    "topic_id": topic_id, "topic_name": topic_name,
                    "session_id": s["session_id"],
                })
                await send_pairing_notification(
                    student_id=new_sid, session_id=s["session_id"],
                    topic_name=topic_name, role="learner", peer_id=q_sid
                )
                await send_pairing_notification(
                    student_id=q_sid, session_id=s["session_id"],
                    topic_name=topic_name, role="teacher", peer_id=new_sid
                )
                break

    # Log matched queue entries
    if queue_matched_students:
        logger.info(f"Matched {len(queue_matched_students)} queue students: {queue_matched_students}")

    # ─── STEP 3: Auto-queue unmatched new students ──────────────────────────

    queued: List[Dict] = []
    for stu in all_students:
        sid = stu["student_id"]
        if sid in reserved_as_learner or sid in reserved_as_teacher:
            continue
        gaps = stu.get("mastery_profile", {}).get("knowledge_gaps", [])
        if not gaps:
            continue
        fresh = await db.students.find_one({"student_id": sid}, {"_id": 0})
        if fresh and fresh.get("current_session_id"):
            continue
        already_waiting = await db.waiting_queue.find_one({
            "student_id": sid, "status": "waiting",
        })
        if already_waiting:
            continue
        sorted_gaps = sort_knowledge_gaps(list(gaps))
        topic_id_q = stu.get("current_weak_topic") or sorted_gaps[0].get("topic_id")
        gap_q = _get_gap_for_topic(stu, topic_id_q)
        topic_name_q = gap_q.get("topic", topic_id_q) if gap_q else topic_id_q
        entry = await _auto_add_to_waiting_queue(sid, topic_id_q, topic_name_q, gap_q)
        queued.append(entry)

    # ─── STEP 4: Save batch record ──────────────────────────────────────────

    batch_id = generate_batch_id()
    await db.batch_pairing_records.insert_one({
        "batch_id": batch_id,
        "created_at": datetime.utcnow(),
        "topics_processed": list(topic_map.keys()),
        "sessions_created": len(all_sessions_created),
        "students_paired": len(reserved_as_learner),
        "students_queued": len(queued),
        "waiting_queue_matched": len(queue_matched_students),
        "details": pairing_details,
    })

    logger.info(
        f"Pairing complete — sessions={len(all_sessions_created)}, "
        f"paired={len(reserved_as_learner)}, queue_matched={len(queue_matched_students)}, queued={len(queued)}"
    )
    return {
        "batch_id": batch_id,
        "sessions_created": len(all_sessions_created),
        "students_paired": len(reserved_as_learner),
        "students_queued": len(queued),
        "waiting_queue_matched": len(queue_matched_students),
        "queue_matched_students": queue_matched_students,
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


async def get_student_pairing_status(student_id: str) -> Dict[str, Any]:
    """
    Return the current pairing status of a specific student.
    """
    db = get_db()
    active_session = await db.pair_sessions.find_one({
        "$or": [
            {"learner_id": student_id, "status": "active"},
            {"teacher_id": student_id, "status": "active"},
        ]
    }, {"_id": 0})
    if active_session:
        role = "learner" if active_session["learner_id"] == student_id else "teacher"
        peer_id = active_session["teacher_id"] if role == "learner" else active_session["learner_id"]
        peer = await db.students.find_one({"student_id": peer_id}, {"_id": 0, "name": 1, "email": 1})
        return {
            "student_id": student_id,
            "status": "in_pair_session",
            "session_id": active_session["session_id"],
            "role": role,
            "topic_id": active_session["topic_id"],
            "topic_name": active_session["topic_name"],
            "pairing_type": active_session["pairing_type"],
            "peer": {
                "student_id": peer_id,
                "name": peer.get("name") if peer else "Unknown",
                "email": peer.get("email") if peer else "",
            },
            "current_bloom_level": active_session.get("current_bloom_level"),
            "questions_asked": active_session.get("questions_asked", 0),
        }
    queue_entries = await db.waiting_queue.find(
        {"student_id": student_id, "status": "waiting"}, {"_id": 0}
    ).to_list(length=None)
    if queue_entries:
        return {
            "student_id": student_id,
            "status": "waiting",
            "queue_entries": queue_entries,
            "waiting_count": len(queue_entries),
        }
    group_session = await db.group_sessions.find_one({
        "members.student_id": student_id,
        "status": "active",
    }, {"_id": 0})
    if group_session:
        member_info = next(
            (m for m in group_session["members"] if m["student_id"] == student_id), None
        )
        peers = [
            {"student_id": m["student_id"], "role": m["role"]}
            for m in group_session["members"]
            if m["student_id"] != student_id
        ]
        return {
            "student_id": student_id,
            "status": "in_group_session",
            "session_id": group_session["session_id"],
            "topic_id": group_session["topic_id"],
            "topic_name": group_session["topic_name"],
            "role": member_info["role"] if member_info else "member",
            "peers": peers,
            "activity_type": group_session.get("activity_type"),
        }
    return {
        "student_id": student_id,
        "status": "idle",
        "message": "Student is not currently in any session or waiting queue.",
    }


# ─── Internal DB helpers ──────────────────────────────────────────────────────

async def get_available_learners_for_topic(topic_id: str, topic_name: Optional[str] = None) -> List[Dict]:
    db = get_db()
    query = {
        "$or": [
            {"mastery_profile.knowledge_gaps.topic_id": topic_id},
            {"mastery_profile.knowledge_gaps.topic": topic_name} if topic_name else {}
        ],
        "current_session_id": None,
        "status": {"$ne": "complete"},
    }
    if not topic_name:
        query.pop("$or")
        query["mastery_profile.knowledge_gaps.topic_id"] = topic_id

    return await db.students.find(query, {"_id": 0}).to_list(length=None)


async def get_available_teachers_for_topic(
    topic_id: str, topic_name: Optional[str] = None, exclude_ids: List[str] = None
) -> List[Dict]:
    db = get_db()
    query = {
        "$or": [
            {
                "mastery_profile.strengths": {
                    "$elemMatch": {"topic_id": topic_id, "can_teach_others": True}
                }
            },
            {
                "mastery_profile.strengths": {
                    "$elemMatch": {"topic": topic_name, "can_teach_others": True}
                }
            } if topic_name else {}
        ],
        "current_session_id": None,
        "status": {"$ne": "complete"},
    }
    if not topic_name:
        query.pop("$or")
        query["mastery_profile.strengths"] = {
            "$elemMatch": {"topic_id": topic_id, "can_teach_others": True}
        }

    if exclude_ids:
        query["student_id"] = {"$nin": exclude_ids}
    return await db.students.find(query, {"_id": 0}).to_list(length=None)


async def _active_session_exists(learner_id: str, topic_id: str) -> bool:
    """Return True if an active session already exists for this learner+topic."""
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
    """Create and persist a pair session."""
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
        return {**existing, "priority_score": round(priority, 2), "already_queued": True}

    queue_id = generate_queue_id()
    entry = {
        "queue_id": queue_id,
        "student_id": student_id,
        "topic_id": topic_id,
        "topic_name": topic_name,
        "gap_type": gap_type,
        "waiting_since": now,
        "priority_score": priority,
        "attempts": attempts,
        "status": "waiting",
    }
    await db.waiting_queue.insert_one(entry)
    logger.info(f"Student {student_id} queued for {topic_name}")
    
    # Notify student about being added to queue
    await send_queue_notification(student_id, topic_name, queue_id)
    
    entry.pop("_id", None)
    return {**entry, "priority_score": round(priority, 2), "already_queued": False}




# ─── Backward-compat alias ────────────────────────────────────────────────────

async def batch_match_all_topics() -> Dict[str, Any]:
    return await run_full_pairing()

async def get_available_teachers_for_topic(
    topic_id: str,
    topic_name=None,
    exclude_ids=None,
):
    """
    Find all students in `studentsdb` who can teach topic_id.
    Excludes:
      - IDs in exclude_ids (e.g. the requesting student)
      - Students whose status is 'in_session' (batch-paired)
      - Students who appear in an ACTIVE pair_session (double-safety)
      - Students already moved to auto_pair_sessions
    """
    from app.core.database import get_db
    db = get_db()
    exclude_ids = set(exclude_ids or [])

    # Pull IDs already committed to an active pair session
    active_sessions = await db.pair_sessions.find(
        {"status": SessionStatus.ACTIVE.value},
        {"learner_id": 1, "teacher_id": 1, "_id": 0},
    ).to_list(length=None)
    for s in active_sessions:
        exclude_ids.add(s.get("learner_id"))
        exclude_ids.add(s.get("teacher_id"))
    exclude_ids.discard(None)

    query = {
        "student_id": {"$nin": list(exclude_ids)},
        "status": {"$ne": "in_session"},
    }
    all_potential = await db.students.find(query, {"_id": 0}).to_list(length=None)
    return [s for s in all_potential if _student_can_teach_topic(s, topic_id, topic_name)]


async def match_student_and_create_session(student_id: str):
    """
    Student-initiated matching:
    - Finds the student's weak topic and searches for the best teacher.
    - Uses atomic reservation to prevent race-condition duplicate sessions.
    - If found: creates a PairSession, moves both to auto_pair_sessions, deletes from studentsdb.
    - If not found: adds student to waiting queue.
    """
    from app.core.database import get_db
    db = get_db()

    # ── Guard: student must exist in studentsdb (not already moved out) ───────
    student = await db.students.find_one({"student_id": student_id}, {"_id": 0})
    if not student:
        # Check if already in an active pair session (moved to auto_pair_sessions)
        existing = await db.pair_sessions.find_one(
            {
                "$or": [{"learner_id": student_id}, {"teacher_id": student_id}],
                "status": SessionStatus.ACTIVE.value,
            },
            {"session_id": 1, "_id": 0},
        )
        if existing:
            return {
                "matched": False,
                "message": f"You are already in an active session ({existing['session_id']}). No new match needed.",
            }
        return {"matched": False, "message": "Student not found in the imported records."}

    # Check status flag (set by batch pairing)
    if student.get("status") == "in_session":
        return {"matched": False, "message": "Student is already in an active session."}

    # Extra guard: cross-check pair_sessions directly
    existing_session = await db.pair_sessions.find_one(
        {
            "$or": [{"learner_id": student_id}, {"teacher_id": student_id}],
            "status": SessionStatus.ACTIVE.value,
        },
        {"session_id": 1, "_id": 0},
    )
    if existing_session:
        return {
            "matched": False,
            "message": f"You are already in an active session ({existing_session['session_id']}).",
        }

    # ── Determine weak topic ──────────────────────────────────────────────────
    topic_id = student.get("current_weak_topic")
    if not topic_id:
        gaps = student.get("mastery_profile", {}).get("knowledge_gaps", [])
        if gaps:
            sorted_gaps = sort_knowledge_gaps(list(gaps))
            topic_id = sorted_gaps[0].get("topic_id")
    if not topic_id:
        return {"matched": False, "message": "No weak areas found for this student."}

    gap = _get_gap_for_topic(student, topic_id)
    topic_name = gap.get("topic", topic_id) if gap else topic_id
    learner_mastery = gap.get("mastery_score") or 0.0

    # ── Find & score available teachers ──────────────────────────────────────
    teachers = await get_available_teachers_for_topic(topic_id, topic_name, exclude_ids=[student_id])
    if not teachers:
        await _auto_add_to_waiting_queue(student_id, topic_id, topic_name, gap)
        return {
            "matched": False,
            "queued": True,
            "message": f"No available teachers for '{topic_name}'. You have been added to the waiting queue.",
        }

    scored = []
    for t in teachers:
        strength = _get_strength_for_topic(t, topic_id, topic_name)
        if not strength:
            continue
        score = calculate_compatibility_score(
            teacher_confidence=strength.get("confidence", 0.5),
            teacher_mastery_level=strength.get("mastery_level", "proficient"),
            gap_type=gap.get("gap_type", "PARTIAL_GAP"),
            learner_mastery_score=learner_mastery,
            learner_confidence=gap.get("confidence", 0.5),
        )
        scored.append((score, t))
    scored.sort(key=lambda x: x[0], reverse=True)

    # ── Atomic reservation: try each candidate until one succeeds ─────────────
    # Use findOneAndDelete to atomically claim the teacher from studentsdb.
    # This prevents two concurrent match-me calls from both picking the same teacher.
    reserved_teacher = None
    for _, candidate in scored:
        claimed = await db.students.find_one_and_delete(
            {
                "student_id": candidate["student_id"],
                "status": {"$ne": "in_session"},
            }
        )
        if claimed:
            claimed.pop("_id", None)
            reserved_teacher = claimed
            break

    if not reserved_teacher:
        # All candidates were claimed by concurrent requests
        await _auto_add_to_waiting_queue(student_id, topic_id, topic_name, gap)
        return {
            "matched": False,
            "queued": True,
            "message": f"No suitable teacher available for '{topic_name}' at this moment. Added to waiting queue.",
        }

    # ── Also atomically remove the learner from studentsdb ────────────────────
    await db.students.delete_one({"student_id": student_id})

    # ── Create the pair session ───────────────────────────────────────────────
    session_id = generate_session_id()
    session_doc = {
        "session_id": session_id,
        "teacher_id": reserved_teacher["student_id"],
        "learner_id": student_id,
        "topic_id": topic_id,
        "topic_name": topic_name,
        "pairing_type": PairingType.ONE_WAY.value,
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
        "learner_initial_mastery": learner_mastery,
        "teacher_score": None,
    }
    await db.pair_sessions.insert_one(session_doc)
    session_doc.pop("_id", None)

    # ── Persist both profiles in auto_pair_sessions ───────────────────────────
    # Use update_one with upsert to prevent duplicate auto_pair_session records
    for record, role in [(student, "learner"), (reserved_teacher, "teacher")]:
        await db.auto_pair_sessions.update_one(
            {"student_id": record["student_id"], "session_id": session_id},
            {"$setOnInsert": {**record, "session_id": session_id, "role": role}},
            upsert=True,
        )

    # Clean up waiting queue for both
    both_ids = [student_id, reserved_teacher["student_id"]]
    await db.waiting_queue.delete_many({"student_id": {"$in": both_ids}})

    logger.info(
        f"[match-me] {student_id} paired with {reserved_teacher['student_id']} "
        f"for '{topic_name}' -> session {session_id}"
    )

    # ── Send notifications (idempotent upsert to prevent duplicates) ──────────
    for notif_student_id, role, peer_id in [
        (student_id, "learner", reserved_teacher["student_id"]),
        (reserved_teacher["student_id"], "teacher", student_id),
    ]:
        notif_doc = {
            "student_id": notif_student_id,
            "type": "pairing_success",
            "session_id": session_id,
            "topic_name": topic_name,
            "role": role,
            "peer_id": peer_id,
            "message": f"Your peer learning session for {topic_name} is starting! You are paired as {role}.",
            "created_at": datetime.utcnow(),
            "status": "unread",
        }
        await db.notifications.update_one(
            {"student_id": notif_student_id, "session_id": session_id},
            {"$setOnInsert": notif_doc},
            upsert=True,
        )

    return {
        "matched": True,
        "session_id": session_id,
        "session_details": session_doc,
        "learner_details": student,
        "teacher_details": reserved_teacher,
    }
