from __future__ import annotations

import certifi
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo import MongoClient

from app.core.config import MONGODB_DB, MONGODB_URL

_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        # tlsCAFile: trust Atlas' CA bundle (certifi) instead of the system
        # store, which fixes CERTIFICATE_VERIFY_FAILED on macOS/containers.
        _client = AsyncIOMotorClient(MONGODB_URL, tlsCAFile=certifi.where())
    return _client


def get_database() -> AsyncIOMotorDatabase:
    return get_client()[MONGODB_DB]
