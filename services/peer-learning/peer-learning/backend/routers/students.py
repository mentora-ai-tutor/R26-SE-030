# backend/routers/students.py
from fastapi import APIRouter, HTTPException
from database import get_db
from services.import_service import import_student_profile

router = APIRouter(prefix="/api/students")

@router.post("/import")
async def import_students(profiles: list[dict]):
    """Accepts a list of student JSON objects from the Knowledge Analysis Agent."""
    results = []
    for profile in profiles:
        result = await import_student_profile(profile)
        results.append({"student_id": result["student_id"], "status": "imported"})
    return {"imported": len(results), "students": results}

@router.get("/{student_id}/status")
async def get_student_status(student_id: str):
    db = get_db()
    student = await db.students.find_one(
        {"student_id": student_id},
        {"_id": 0}  # exclude MongoDB's internal _id from response
    )
    if not student:
        raise HTTPException(status_code=404, detail=f"Student '{student_id}' not found")
    return student