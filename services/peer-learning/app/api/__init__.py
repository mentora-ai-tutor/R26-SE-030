from fastapi import APIRouter
from app.api.routes import students, sessions, groups, pools, notifications, performance, websockets, live_room

api_router = APIRouter()

api_router.include_router(students.router)
api_router.include_router(sessions.router)
api_router.include_router(groups.router)
api_router.include_router(pools.router)
api_router.include_router(notifications.router)
api_router.include_router(performance.router)
api_router.include_router(websockets.router)
api_router.include_router(live_room.router)
