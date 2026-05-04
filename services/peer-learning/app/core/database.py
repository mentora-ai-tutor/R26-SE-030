from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from loguru import logger
from app.core.config import settings

client: AsyncIOMotorClient = None
db: AsyncIOMotorDatabase = None


async def connect_db():
    global client, db
    logger.info(f"Connecting to MongoDB at {settings.mongodb_url}")
    client = AsyncIOMotorClient(settings.mongodb_url)
    db = client[settings.mongodb_db_name]
    await _create_indexes()
    logger.info("MongoDB connected successfully")


async def disconnect_db():
    global client
    if client:
        client.close()
        logger.info("MongoDB disconnected")


async def _create_indexes():
    # students
    await db.students.create_index("student_id", unique=True)
    await db.students.create_index("current_session_id")
    await db.students.create_index("status")

    # pair_sessions
    await db.pair_sessions.create_index("session_id", unique=True)
    await db.pair_sessions.create_index("teacher_id")
    await db.pair_sessions.create_index("learner_id")
    await db.pair_sessions.create_index("topic_id")
    await db.pair_sessions.create_index("status")

    # group_sessions
    await db.group_sessions.create_index("session_id", unique=True)
    await db.group_sessions.create_index("topic_id")
    await db.group_sessions.create_index("status")

    # waiting_queue
    await db.waiting_queue.create_index([("topic_id", 1), ("priority_score", -1)])
    await db.waiting_queue.create_index("student_id")

    # notifications
    await db.notifications.create_index("student_id")
    await db.notifications.create_index("expires_at")
    await db.notifications.create_index("status")

    # questions_bank
    await db.questions_bank.create_index("question_id", unique=True)
    await db.questions_bank.create_index("topic_id")
    await db.questions_bank.create_index("bloom_level")

    # improved_pools
    await db.improved_pools.create_index([("topic_id", 1), ("student_id", 1)], unique=True)

    # verified_pools
    await db.verified_pools.create_index([("topic_id", 1), ("student_id", 1)], unique=True)

    logger.info("Database indexes created")


def get_db() -> AsyncIOMotorDatabase:
    return db
