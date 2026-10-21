import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pymongo import ASCENDING, MongoClient
from pymongo.errors import CollectionInvalid

from app.config import settings

logger = logging.getLogger("mongodb")

_client: Optional[MongoClient] = None

DB_NAME = settings.DATABASE_NAME

# Collection name -> list of (field, direction) indexes to ensure on startup
COLLECTIONS = {
    "students": [("student_id", ASCENDING)],
    "student_analyses": [("student_id", ASCENDING)],
    "quiz_evaluations": [("student_id", ASCENDING)],
    "diagnostic_sessions": [("student_id", ASCENDING), ("status", ASCENDING)],
    "assessments": [("student_id", ASCENDING)],
    "content_recommendations": [("student_id", ASCENDING)],
    "peer_matches": [("student_id", ASCENDING)],
    "peer_notifications": [("student_id", ASCENDING), ("status", ASCENDING)],
    "chat_sessions": [("room_id", ASCENDING)],
    "collab_rooms": [("room_id", ASCENDING)],
    "collab_chat_messages": [("room_id", ASCENDING), ("timestamp", ASCENDING)],
    "peer_teaching_history": [("student_id", ASCENDING), ("topic", ASCENDING)],
    "knowledge_chunks": [("chunk_index", ASCENDING)],
}

WORKSPACE_COLLECTIONS = {
    "workspaces": [
        ("workspace_id", ASCENDING),
        ("owner_student_id", ASCENDING),
        ("members.student_id", ASCENDING),
    ],
    "join_keys": [("key_hash", ASCENDING), ("workspace_id", ASCENDING)],
    "workspace_invites": [
        ("workspace_id", ASCENDING),
        ("student_id", ASCENDING),
        ("status", ASCENDING),
    ],
    "workspace_files": [("workspace_id", ASCENDING), ("path", ASCENDING)],
    "file_versions": [
        ("workspace_id", ASCENDING),
        ("file_id", ASCENDING),
        ("created_at", ASCENDING),
    ],
    "workspace_chat": [
        ("workspace_id", ASCENDING),
        ("student_id", ASCENDING),
        ("created_at", ASCENDING),
    ],
    "workspace_chat_reads": [
        ("workspace_id", ASCENDING),
        ("student_id", ASCENDING),
    ],
    "workspace_comments": [("workspace_id", ASCENDING), ("file_id", ASCENDING)],
    "workspace_tasks": [("workspace_id", ASCENDING)],
    "activity_log": [("workspace_id", ASCENDING), ("created_at", ASCENDING)],
    "workspace_sync": [("workspace_id", ASCENDING), ("file_id", ASCENDING)],
    "workspace_trash": [("workspace_id", ASCENDING)],
    "workspace_notifications": [("student_id", ASCENDING), ("workspace_id", ASCENDING)],
}
COLLECTIONS.update(WORKSPACE_COLLECTIONS)


def get_client() -> MongoClient:
    """Lazily creates and reuses the MongoDB client."""
    global _client
    if _client is None:
        _client = MongoClient(
            settings.MONGODB_URL,
            serverSelectionTimeoutMS=5000,
            maxPoolSize=10,
        )
    return _client


def get_db():
    return get_client()[DB_NAME]


def get_collection(name: str):
    return get_db()[name]


def init_db() -> bool:
    """Creates the database and its collections/indexes if they don't exist."""
    try:
        client = get_client()
        client.admin.command("ping")

        db = get_db()
        for name, indexes in COLLECTIONS.items():
            try:
                db.create_collection(name)
            except CollectionInvalid:
                pass
            for field, direction in indexes:
                try:
                    db[name].create_index([(field, direction)])
                except Exception:
                    pass

        try:
            db["join_keys"].create_index(
                [("key_hash", ASCENDING)],
                unique=True,
                name="workspace_join_key_hash_unique",
            )
        except Exception:
            logger.exception("Failed to create unique workspace join-key index")

        try:
            db["join_keys"].create_index(
                [("expires_at", ASCENDING)],
                expireAfterSeconds=0,
                name="workspace_join_key_expiry_ttl",
            )
        except Exception:
            logger.exception("Failed to create workspace join-key expiry index")

        try:
            db["workspace_invites"].create_index(
                [("workspace_id", ASCENDING), ("student_id", ASCENDING)],
                unique=True,
                partialFilterExpression={"status": "pending"},
                name="workspace_pending_invite_unique",
            )
        except Exception:
            logger.exception("Failed to create unique pending workspace invitation index")

        try:
            db["workspace_join_attempts"].create_index(
                [("expires_at", ASCENDING)],
                expireAfterSeconds=0,
                name="workspace_join_attempt_expiry_ttl",
            )
        except Exception:
            logger.exception("Failed to create workspace join-attempt expiry index")

        try:
            db["workspace_trash"].create_index(
                [("expires_at", ASCENDING)],
                expireAfterSeconds=0,
                name="workspace_trash_expiry_ttl",
            )
        except Exception:
            logger.exception("Failed to create workspace trash expiry index")

        try:
            db["workspace_chat_reads"].create_index(
                [("workspace_id", ASCENDING), ("student_id", ASCENDING)],
                unique=True,
                name="workspace_chat_read_marker_unique",
            )
        except Exception:
            logger.exception("Failed to create unique workspace chat read-marker index")

        logger.info(f"MongoDB connected. Database ready: {DB_NAME}")
        return True
    except Exception as e:
        logger.warning(f"MongoDB unavailable ({DB_NAME}): {e}")
        return False


def close_db() -> None:
    """Closes the shared MongoDB client (used on app shutdown)."""
    global _client
    if _client is not None:
        _client.close()
        _client = None


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def insert_record(collection: str, record: Dict[str, Any]) -> Optional[str]:
    """Inserts a record. Never raises; failures are logged and skipped."""
    try:
        doc = dict(record)
        doc.setdefault("saved_at", _utcnow())
        result = get_collection(collection).insert_one(doc)
        return str(result.inserted_id)
    except Exception as e:
        logger.warning(f"Failed to save record to '{collection}': {e}")
        return None


# --- Per-domain persistence helpers ---


def save_student(data: Dict[str, Any]) -> Optional[str]:
    return insert_record("students", data)


def save_student_analysis(data: Dict[str, Any]) -> Optional[str]:
    return insert_record("student_analyses", data)


def save_quiz_evaluation(data: Dict[str, Any]) -> Optional[str]:
    return insert_record("quiz_evaluations", data)


def save_assessment(data: Dict[str, Any]) -> Optional[str]:
    return insert_record("assessments", data)


def save_content_recommendation(data: Dict[str, Any]) -> Optional[str]:
    return insert_record("content_recommendations", data)


def save_peer_match(data: Dict[str, Any]) -> Optional[str]:
    return insert_record("peer_matches", data)


def save_chat_session(data: Dict[str, Any]) -> Optional[str]:
    return insert_record("chat_sessions", data)


def upsert_collab_room(room_id: str, code: str, active_users: int = 0) -> bool:
    """Creates or updates a collaborative room's code state in MongoDB."""
    try:
        get_collection("collab_rooms").update_one(
            {"room_id": room_id},
            {
                "$set": {
                    "code": code,
                    "active_users": active_users,
                    "updated_at": _utcnow(),
                },
                "$setOnInsert": {"created_at": _utcnow()},
            },
            upsert=True,
        )
        return True
    except Exception as e:
        logger.warning(f"Failed to persist collab room '{room_id}': {e}")
        return False
