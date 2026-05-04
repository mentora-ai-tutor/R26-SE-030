from fastapi import APIRouter, Depends, HTTPException, Request
from typing import List, Dict, Any
from app.core.auth import TokenPayload, get_current_user
from app.models.models import StudentImport
from app.services.import_service import (
    import_students,
    get_all_students,
    get_student,
    get_student_weaknesses,
    get_student_history,
)

router = APIRouter(prefix="/api/students", tags=["Students"])


@router.post("/import", summary="Import students from JSON")
async def import_students_endpoint(
    request: Request,
    current_user: TokenPayload = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    Phase 1: Import student data from JSON.

    Accepts TWO formats:
    - Raw array:      [ { "student_id": "...", ... }, ... ]
    - Wrapped object: { "students": [ { "student_id": "...", ... }, ... ] }

    Sorts weaknesses FUNDAMENTAL_GAP first, sets current_weak_topic.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    # Normalise: accept raw array OR {"students": [...]}
    if isinstance(body, list):
        raw_students = body
    elif isinstance(body, dict) and "students" in body:
        raw_students = body["students"]
    else:
        raise HTTPException(
            status_code=422,
            detail="Body must be a JSON array OR an object with a 'students' key.",
        )

    if not raw_students:
        raise HTTPException(status_code=400, detail="No students provided")

    # Validate each entry individually so one bad record doesn't block the rest
    parsed: List[StudentImport] = []
    validation_errors = []
    for i, raw in enumerate(raw_students):
        try:
            parsed.append(StudentImport.model_validate(raw))
        except Exception as e:
            validation_errors.append({
                "index": i,
                "student_id": raw.get("student_id", "unknown"),
                "error": str(e),
            })

    if not parsed:
        raise HTTPException(
            status_code=422,
            detail={"message": "All students failed validation", "errors": validation_errors},
        )

    result = await import_students(parsed)

    if validation_errors:
        result["validation_errors"] = validation_errors
        result["warning"] = f"{len(validation_errors)} student(s) skipped due to validation errors"

    return result


@router.get("", summary="Get all students")
async def list_students(current_user: TokenPayload = Depends(get_current_user)) -> List[Dict]:
    return await get_all_students()


@router.get("/{student_id}", summary="Get student by ID")
async def get_student_endpoint(
    student_id: str,
    current_user: TokenPayload = Depends(get_current_user),
) -> Dict:
    student = await get_student(student_id)
    if not student:
        raise HTTPException(status_code=404, detail=f"Student {student_id} not found")
    return student


@router.get("/{student_id}/history", summary="Get student pairing history")
async def get_history(
    student_id: str,
    current_user: TokenPayload = Depends(get_current_user),
) -> Dict:
    student = await get_student(student_id)
    if not student:
        raise HTTPException(status_code=404, detail=f"Student {student_id} not found")
    return await get_student_history(student_id)


@router.get("/{student_id}/weaknesses", summary="Get student knowledge gaps")
async def get_weaknesses(
    student_id: str,
    current_user: TokenPayload = Depends(get_current_user),
) -> List[Dict]:
    student = await get_student(student_id)
    if not student:
        raise HTTPException(status_code=404, detail=f"Student {student_id} not found")
    return await get_student_weaknesses(student_id)