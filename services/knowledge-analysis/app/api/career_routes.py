"""Career-fit prediction endpoints.

``POST /api/v1/career/predict`` runs the hand-made NumPy classifier over a student's latest
mastery profile + quiz result and returns a best-fit role + calibrated ranking + gaps + an
LLM-written explanation. ``GET /api/v1/career/{student_id}/latest`` reads the newest saved
prediction.

Reads are open by ``student_id``, mirroring the mastery-profile / quiz read endpoints
(internal-key enforcement on KAA reads is the same tracked gap — ARCHITECTURE.md §9). Uses
the shared ``{"status","data"}`` envelope so the frontend ``unwrap`` helper works unchanged.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status

from app.core.config import FEATURE_CAREER_PREDICTION
from app.models.career import CareerPredictRequest
from app.services.career.predictor import predict_career
from app.services.career.store import get_latest_career_prediction

router = APIRouter(prefix="/api/v1/career", tags=["career"])


@router.post("/predict")
async def predict(payload: CareerPredictRequest) -> dict[str, Any]:
    """Predict the best-fit software role for a student from their measured competencies."""
    if not FEATURE_CAREER_PREDICTION:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Career prediction is disabled (FEATURE_CAREER_PREDICTION).",
        )
    data = await predict_career(payload.student_id, payload.target_role)
    return {"status": "success", "data": data}


@router.get("/{student_id}/latest")
async def latest_prediction(student_id: str) -> dict[str, Any]:
    """Newest saved career prediction for a student."""
    data = await get_latest_career_prediction(student_id)
    if data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No career prediction found for this student",
        )
    return {"status": "success", "data": data}
