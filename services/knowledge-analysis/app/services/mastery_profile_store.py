from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from bson import ObjectId

from app.db.database import get_database


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _json_safe(value: Any) -> Any:
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    return value


async def ensure_mastery_profile_indexes() -> None:
    db = get_database()
    await db.mastery_profiles.create_index([("student_id", 1), ("created_at", -1)])
    await db.mastery_profiles.create_index([("gap_topic_ids", 1)])
    await db.mastery_profiles.create_index([("schema_version", 1)])


def build_mastery_profile_document(
    canonical_payload: dict[str, Any],
    raw_analysis_payload: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    mastery_profile = canonical_payload.get("mastery_profile") or {}
    knowledge_gaps = mastery_profile.get("knowledge_gaps") or canonical_payload.get("knowledge_gaps") or []
    strengths = mastery_profile.get("strengths") or canonical_payload.get("strengths") or []
    overall_mastery_score = mastery_profile.get(
        "overall_mastery_score",
        canonical_payload.get("overall_mastery_score"),
    )
    now = _utcnow()

    doc = dict(canonical_payload)
    doc.update(
        {
            "mastery_profile": {
                "overall_mastery_score": overall_mastery_score,
                "knowledge_gaps": knowledge_gaps,
                "strengths": strengths,
            },
            "overall_mastery_score": overall_mastery_score,
            "knowledge_gaps": knowledge_gaps,
            "strengths": strengths,
            "gap_topic_ids": [gap.get("topic_id") for gap in knowledge_gaps if gap.get("topic_id")],
            "raw_analysis_payload": raw_analysis_payload
            if raw_analysis_payload is not None
            else canonical_payload.get("raw_analysis_payload", {}),
            "created_at": now,
            "updated_at": now,
        }
    )
    return doc


def canonical_profile_from_document(doc: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not doc:
        return None

    safe_doc = _json_safe(doc)
    mastery_profile = safe_doc.get("mastery_profile") or {
        "overall_mastery_score": safe_doc.get("overall_mastery_score"),
        "knowledge_gaps": safe_doc.get("knowledge_gaps", []),
        "strengths": safe_doc.get("strengths", []),
    }

    return {
        "profile_id": safe_doc.get("_id"),
        "schema_version": safe_doc.get("schema_version"),
        "student_id": safe_doc.get("student_id"),
        "analysis_timestamp": safe_doc.get("analysis_timestamp"),
        "data_sources": safe_doc.get("data_sources", {}),
        "mastery_profile": mastery_profile,
        "recommendations": safe_doc.get("recommendations", {}),
        "overall_mastery_score": mastery_profile.get("overall_mastery_score"),
        "knowledge_gaps": mastery_profile.get("knowledge_gaps", []),
        "strengths": mastery_profile.get("strengths", []),
        "gap_topic_ids": [
            gap.get("topic_id")
            for gap in mastery_profile.get("knowledge_gaps", [])
            if gap.get("topic_id")
        ],
        "created_at": safe_doc.get("created_at"),
        "updated_at": safe_doc.get("updated_at"),
    }


async def save_mastery_profile(
    canonical_payload: dict[str, Any],
    raw_analysis_payload: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    await ensure_mastery_profile_indexes()
    doc = build_mastery_profile_document(canonical_payload, raw_analysis_payload)
    db = get_database()
    result = await db.mastery_profiles.insert_one(doc)
    saved = await db.mastery_profiles.find_one({"_id": result.inserted_id})
    return canonical_profile_from_document(saved) or {}


async def get_latest_mastery_profile(student_id: str) -> Optional[dict[str, Any]]:
    await ensure_mastery_profile_indexes()
    db = get_database()
    doc = await db.mastery_profiles.find_one(
        {"student_id": student_id},
        sort=[("created_at", -1)],
    )
    return canonical_profile_from_document(doc)
