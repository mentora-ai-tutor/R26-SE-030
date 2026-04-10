# backend/database.py
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
import os

load_dotenv()

MONGODB_URL = os.getenv("MONGODB_URL")
DATABASE_NAME = os.getenv("DATABASE_NAME")

client = None
db = None

async def connect_db():
    global client, db
    client = AsyncIOMotorClient(MONGODB_URL)
    db = client[DATABASE_NAME]
    # Create indexes for fast queries
    await db.students.create_index("student_id", unique=True)
    await db.pair_sessions.create_index("learner_id")
    await db.pair_sessions.create_index("teacher_id")
    await db.topic_pools.create_index([("topic", 1), ("pool_type", 1)])
    await db.group_sessions.create_index("topic")
    print("Connected to MongoDB")

async def close_db():
    global client
    if client:
        client.close()

def get_db():
    return db