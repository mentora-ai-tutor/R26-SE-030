# backend/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import connect_db, close_db
from routers import students, sessions, dashboard
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_db()
    yield
    await close_db()

app = FastAPI(title="Peer Learning Agent", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React frontend
    allow_methods=["*"],
    allow_headers=["*"]
)

app.include_router(students.router)
app.include_router(sessions.router)

@app.get("/")
async def root():
    return {"status": "Peer Learning Agent running"}