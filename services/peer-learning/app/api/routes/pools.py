from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
from pydantic import BaseModel
from app.services.pool_service import (
    create_topic_pool,
    get_all_pools,
    get_pool_students,
)

router = APIRouter(prefix="/api/pools", tags=["Topic Pools"])


class CreatePoolBody(BaseModel):
    topic_id: str
    topic_name: str


@router.post("/{topic_id}/create", summary="Create or verify a topic pool")
async def create_pool(topic_id: str) -> Dict[str, Any]:
    return await create_topic_pool(topic_id)


@router.get("/all", summary="Get all topic pools with stats")
async def list_pools() -> List[Dict]:
    return await get_all_pools()


@router.get("/{topic_id}/students", summary="Get students in improved pool for topic")
async def list_pool_students(topic_id: str) -> List[Dict]:
    return await get_pool_students(topic_id)
