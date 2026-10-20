"""Persistence for career predictions (``career_predictions`` collection).

Mirrors ``mastery_profile_store``: append one doc per prediction (``insert_one``), read the
newest via ``/latest``. Keyed by the public ``student_id`` (same identity convention as
``mastery_profiles``).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from bson import ObjectId

from app.db.database import get_database


def _json_safe(value: Any) -> Any:
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    return value


async def ensure_career_indexes() -> None:
    db = get_database()
    await db.career_predictions.create_index([("student_id", 1), ("created_at", -1)])
    await db.career_predictions.create_index([("best_fit_role", 1)])


async def save_career_prediction(prediction: dict[str, Any]) -> dict[str, Any]:
    db = get_database()
    doc = dict(prediction)
    doc["created_at"] = datetime.now(timezone.utc)
    result = await db.career_predictions.insert_one(doc)
    doc["_id"] = result.inserted_id
    return _json_safe(doc)


async def get_latest_career_prediction(student_id: str) -> Optional[dict[str, Any]]:
    db = get_database()
    doc = await db.career_predictions.find_one(
        {"student_id": student_id}, sort=[("created_at", -1)]
    )
    return _json_safe(doc) if doc else None
