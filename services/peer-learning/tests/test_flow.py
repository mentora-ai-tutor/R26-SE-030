"""
End-to-end test script for the Peer Learning System.
Tests the complete flow from import to verification.

Usage:
    python tests/test_flow.py [--base-url http://localhost:8000]
"""

import asyncio
import argparse
import json
import sys
from datetime import datetime
import httpx

BASE_URL = "http://localhost:8000"

# ─── Sample Data ──────────────────────────────────────────────────────────────
SAMPLE_STUDENTS = {
    "students": [
        {
            "student_id": "STU-2026-0001",
            "analysis_timestamp": "2026-04-09T08:00:00Z",
            "data_sources": {"github": "available", "sandbox": "available", "quizzes": "available"},
            "mastery_profile": {
                "overall_mastery_score": 45,
                "knowledge_gaps": [
                    {
                        "topic": "Recursion",
                        "topic_id": "CS101-REC",
                        "gap_type": "FUNDAMENTAL_GAP",
                        "confidence": 0.9,
                        "mastery_score": 20.0,
                    },
                    {
                        "topic": "Binary Search Trees",
                        "topic_id": "CS101-BST",
                        "gap_type": "PARTIAL_GAP",
                        "confidence": 0.7,
                        "mastery_score": 45.0,
                    },
                ],
                "strengths": [
                    {
                        "topic": "Loops",
                        "topic_id": "CS101-LOOP",
                        "confidence": 0.9,
                        "mastery_level": "proficient",
                        "can_teach_others": True,
                    }
                ],
            },
        },
        {
            "student_id": "STU-2026-0002",
            "analysis_timestamp": "2026-04-09T08:00:00Z",
            "data_sources": {"github": "available", "sandbox": "available", "quizzes": "available"},
            "mastery_profile": {
                "overall_mastery_score": 80,
                "knowledge_gaps": [
                    {
                        "topic": "Loops",
                        "topic_id": "CS101-LOOP",
                        "gap_type": "PARTIAL_GAP",
                        "confidence": 0.6,
                        "mastery_score": 50.0,
                    }
                ],
                "strengths": [
                    {
                        "topic": "Recursion",
                        "topic_id": "CS101-REC",
                        "confidence": 0.95,
                        "mastery_level": "advanced",
                        "can_teach_others": True,
                    },
                    {
                        "topic": "Binary Search Trees",
                        "topic_id": "CS101-BST",
                        "confidence": 0.85,
                        "mastery_level": "proficient",
                        "can_teach_others": True,
                    },
                ],
            },
        },
        {
            "student_id": "STU-2026-0003",
            "analysis_timestamp": "2026-04-09T08:00:00Z",
            "data_sources": {"github": "available", "sandbox": "available", "quizzes": "available"},
            "mastery_profile": {
                "overall_mastery_score": 35,
                "knowledge_gaps": [
                    {
                        "topic": "Recursion",
                        "topic_id": "CS101-REC",
                        "gap_type": "FUNDAMENTAL_GAP",
                        "confidence": 0.85,
                        "mastery_score": 15.0,
                    }
                ],
                "strengths": [],
            },
        },
        {
            "student_id": "STU-2026-0004",
            "analysis_timestamp": "2026-04-09T08:00:00Z",
            "data_sources": {"github": "available", "sandbox": "available", "quizzes": "available"},
            "mastery_profile": {
                "overall_mastery_score": 55,
                "knowledge_gaps": [
                    {
                        "topic": "Recursion",
                        "topic_id": "CS101-REC",
                        "gap_type": "PARTIAL_GAP",
                        "confidence": 0.75,
                        "mastery_score": 40.0,
                    }
                ],
                "strengths": [
                    {
                        "topic": "Binary Search Trees",
                        "topic_id": "CS101-BST",
                        "confidence": 0.8,
                        "mastery_level": "proficient",
                        "can_teach_others": True,
                    }
                ],
            },
        },
    ]
}


# ─── Test Helpers ─────────────────────────────────────────────────────────────

def log(msg: str, level: str = "INFO"):
    colors = {"INFO": "\033[94m", "OK": "\033[92m", "WARN": "\033[93m", "ERROR": "\033[91m"}
    reset = "\033[0m"
    prefix = colors.get(level, "") + f"[{level}]" + reset
    print(f"{prefix} {msg}")


def assert_ok(response: httpx.Response, label: str):
    if response.status_code not in (200, 201):
        log(f"FAILED {label}: HTTP {response.status_code} — {response.text[:300]}", "ERROR")
        sys.exit(1)
    log(f"✓ {label}", "OK")
    return response.json()


# ─── Test Cases ───────────────────────────────────────────────────────────────

async def test_health(client: httpx.AsyncClient):
    log("=== Health Check ===")
    r = await client.get("/health")
    data = assert_ok(r, "Health endpoint")
    log(f"  DB: {data['database']}, Model: {data['model']}")


async def test_import(client: httpx.AsyncClient):
    log("=== Phase 1: Import Students ===")
    r = await client.post("/api/students/import", json=SAMPLE_STUDENTS)
    data = assert_ok(r, "Import 4 students")
    log(f"  Imported: {data.get('imported')}, Updated: {data.get('updated')}, Errors: {len(data.get('errors', []))}")

    # Verify students exist
    r2 = await client.get("/api/students")
    students = assert_ok(r2, "List students")
    log(f"  Total students in DB: {len(students)}")

    # Check a student's sorted gaps
    r3 = await client.get("/api/students/STU-2026-0001/weaknesses")
    gaps = assert_ok(r3, "Get student weaknesses (sorted)")
    log(f"  STU-2026-0001 gaps (should be FUNDAMENTAL first): {[g['gap_type'] for g in gaps]}")
    assert gaps[0]["gap_type"] == "FUNDAMENTAL_GAP", "Gaps not sorted correctly!"
    log("  ✓ Gaps correctly sorted: FUNDAMENTAL_GAP first", "OK")

    return data


async def test_pairing(client: httpx.AsyncClient):
    log("=== Phase 2: Pair Formation (Hungarian Algorithm) ===")

    # Preview match for STU-2026-0001
    r = await client.get("/api/sessions/match/STU-2026-0001")
    data = assert_ok(r, "Preview best teacher for STU-2026-0001")
    log(f"  Best teacher: {data.get('best_teacher_id')}, Compatibility: {data.get('compatibility_score')}")

    # Batch match all topics
    r2 = await client.post("/api/sessions/batch/all-topics")
    batch = assert_ok(r2, "Batch pair all topics")
    log(f"  Sessions created: {batch.get('sessions_created')}")
    log(f"  Students queued (no teacher): {len(batch.get('students_queued', []))}")
    for detail in batch.get("details", []):
        log(f"    Topic '{detail['topic_name']}': {detail['sessions_created']} session(s)")

    return batch


async def test_active_sessions(client: httpx.AsyncClient):
    log("=== Get Active Sessions ===")
    r = await client.get("/api/sessions/all/active")
    sessions = assert_ok(r, "List active sessions")
    log(f"  Active sessions: {len(sessions)}")
    for s in sessions:
        log(f"    {s['session_id']}: {s['teacher_id']} → {s['learner_id']} [{s['topic_name']}] ({s['pairing_type']})")
    return sessions


async def test_session_flow(client: httpx.AsyncClient, sessions: list):
    log("=== Phase 3 & 4: Session Flow (Question → Answer → Score) ===")
    if not sessions:
        log("  No active sessions to test", "WARN")
        return

    session = sessions[0]
    session_id = session["session_id"]
    log(f"  Testing session: {session_id}")

    # Generate first question
    r = await client.post(f"/api/sessions/{session_id}/start-question")
    question = assert_ok(r, f"Generate question (Bloom level {session['current_bloom_level']})")
    log(f"  Question: {question.get('question_text', '')[:80]}...")
    q_id = question["question_id"]

    # Request a hint
    r2 = await client.post(
        f"/api/sessions/{session_id}/hint",
        json={"question_id": q_id},
    )
    hint_data = assert_ok(r2, "Request hint")
    log(f"  Hint received: {hint_data.get('hint', '')[:60]}...")

    # Submit a correct-ish answer
    r3 = await client.post(
        f"/api/sessions/{session_id}/answer",
        json={"answer": "This is my best answer demonstrating understanding.", "time_taken_seconds": 45},
    )
    result = assert_ok(r3, "Submit answer")
    log(f"  Answer correct: {result.get('is_correct')}")
    log(f"  Bloom level: {result.get('bloom_level_before')} → {result.get('bloom_level_after')}")
    log(f"  Feedback: {result.get('feedback', '')[:80]}")

    return session_id


async def test_complete_session(client: httpx.AsyncClient, session_id: str):
    log("=== Phase 4: Complete Session & Score ===")
    r = await client.post(f"/api/sessions/{session_id}/complete")
    result = assert_ok(r, "Complete session")
    log(f"  Learner score: {result.get('learner_score')}")
    log(f"  Teacher score: {result.get('teacher_score')}")
    log(f"  Learner outcome: {result.get('learner_outcome')}")
    log(f"  Teacher outcome: {result.get('teacher_outcome')}")
    log(f"  Next action: {result.get('next_action', 'N/A')}")
    return result


async def test_pools(client: httpx.AsyncClient):
    log("=== Phase 5 & Pools ===")
    r = await client.get("/api/pools/all")
    pools = assert_ok(r, "List all pools")
    log(f"  Pools: {len(pools)}")
    for p in pools:
        log(f"    {p['topic_name']}: {p['student_count']} students, avg mastery={p['avg_mastery']}")

    # Try to form group session for Recursion if pool has enough
    r2 = await client.get("/api/pools/CS101-REC/students")
    rec_students = assert_ok(r2, "Get Recursion pool students")
    log(f"  Recursion pool size: {len(rec_students)}")
    return pools


async def test_waiting_queue(client: httpx.AsyncClient):
    log("=== Phase 6: Waiting Queue ===")
    r = await client.post(
        "/api/waiting/add",
        json={
            "student_id": "STU-2026-0003",
            "topic_id": "CS101-REC",
            "topic_name": "Recursion",
            "gap_type": "FUNDAMENTAL_GAP",
            "attempts": 0,
        },
    )
    data = assert_ok(r, "Add student to waiting queue")
    log(f"  Queue ID: {data.get('queue_id')}, Priority: {data.get('priority'):.1f}")

    # Check notifications
    r2 = await client.get("/api/notifications/STU-2026-0003")
    notifs = assert_ok(r2, "Get notifications for STU-2026-0003")
    log(f"  Pending notifications: {len(notifs)}")


async def test_performance(client: httpx.AsyncClient):
    log("=== Performance Reports ===")
    r = await client.get("/api/performance/STU-2026-0001")
    perf = assert_ok(r, "Get performance for STU-2026-0001")
    log(f"  Initial mastery: {perf.get('initial_mastery')}")
    log(f"  Current mastery: {perf.get('current_mastery')}")
    log(f"  Sessions as learner: {perf.get('pair_sessions_as_learner')}")
    log(f"  Sessions as teacher: {perf.get('pair_sessions_as_teacher')}")
    log(f"  Topics improved: {perf.get('topics_improved')}")


async def test_question_bank(client: httpx.AsyncClient):
    log("=== Question Bank ===")
    r = await client.get("/api/questions/bank/CS101-REC")
    questions = assert_ok(r, "Get Recursion question bank")
    log(f"  Questions stored for Recursion: {len(questions)}")
    if questions:
        q = questions[0]
        log(f"  Sample: [{q['bloom_level']}] {q['question_text'][:60]}...")
        log(f"  Success rate: {q.get('success_rate', 0):.2%}, Used: {q.get('used_count', 0)} times")


async def test_group_session(client: httpx.AsyncClient):
    log("=== Phase 7: Group Session (attempt) ===")
    r = await client.post("/api/groups/form", json={"topic_id": "CS101-REC"})
    if r.status_code == 400:
        log(f"  Not enough students in pool yet (expected): {r.json().get('detail')}", "WARN")
    else:
        group = r.json()
        log(f"  Group session formed: {group.get('session_id')}", "OK")
        log(f"  Activity: {group.get('activity_type')}")
        log(f"  Members: {[(m['student_id'], m['role']) for m in group.get('members', [])]}")


# ─── Main ─────────────────────────────────────────────────────────────────────

async def run_all_tests(base_url: str):
    log(f"\n{'='*60}")
    log(f"  Peer Learning System — End-to-End Test Suite")
    log(f"  Base URL: {base_url}")
    log(f"  Time: {datetime.utcnow().isoformat()}")
    log(f"{'='*60}\n")

    async with httpx.AsyncClient(base_url=base_url, timeout=60.0) as client:
        try:
            await test_health(client)
            await test_import(client)
            batch = await test_pairing(client)
            sessions = await test_active_sessions(client)

            test_session_id = None
            if sessions:
                test_session_id = await test_session_flow(client, sessions)

            if test_session_id:
                await test_complete_session(client, test_session_id)

            await test_pools(client)
            await test_waiting_queue(client)
            await test_performance(client)
            await test_question_bank(client)
            await test_group_session(client)

            log(f"\n{'='*60}")
            log("  ALL TESTS COMPLETED SUCCESSFULLY", "OK")
            log(f"{'='*60}\n")

        except SystemExit:
            log("\nTest suite FAILED. Check errors above.", "ERROR")
            sys.exit(1)
        except Exception as e:
            log(f"\nUnexpected error: {e}", "ERROR")
            import traceback
            traceback.print_exc()
            sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    args = parser.parse_args()
    asyncio.run(run_all_tests(args.base_url))
