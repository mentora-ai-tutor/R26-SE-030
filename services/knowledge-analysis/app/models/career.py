"""Pydantic models for career-fit prediction (the `/api/v1/career` contract).

The hand-made NumPy classifier (``app/services/career/model.py``) decides the role, fit
and gaps; the LLM only fills ``CareerNarrative``. Additive artifact — does NOT touch
``CanonicalMasteryOutput``.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class RankedRole(BaseModel):
    role: str
    fit_score: float = Field(ge=0, le=1, description="Calibrated softmax probability for this role.")
    confidence: float = Field(ge=0, le=1, description="Same as fit_score; named for UI clarity.")


class CompetencyGap(BaseModel):
    axis: str                       # e.g. "A6"
    axis_name: str                  # e.g. "Concurrency"
    your_score: float = Field(ge=0, le=1)
    required_score: float = Field(ge=0, le=1)
    gap: float = Field(ge=0, le=1)  # required - your_score, clamped at 0


class AspirationAlignment(BaseModel):
    stated_role: str
    fit_to_stated: float = Field(ge=0, le=1)
    gap_to_stated: List[CompetencyGap] = Field(default_factory=list)
    est_hours_to_ready: int = 0


class CareerNarrative(BaseModel):
    """The ONLY part the LLM writes. It explains the model's decision; it cannot change it."""
    headline: str
    why_fit: List[str] = Field(default_factory=list)
    gap_plan: List[str] = Field(default_factory=list)
    encouragement: str = ""


class CareerPredictRequest(BaseModel):
    student_id: str = Field(..., min_length=1)
    target_role: Optional[str] = Field(
        default=None, description="Optional stated ambition -> drives aspiration_alignment."
    )


class CareerPrediction(BaseModel):
    schema_version: str
    student_id: str
    generated_at: str
    method: str = "numpy-softmax"
    model_version: str = ""
    evidence_sufficient: bool
    evidence: dict = Field(default_factory=dict)
    best_fit_role: Optional[str] = None
    readiness_level: Optional[str] = None
    ranked_roles: List[RankedRole] = Field(default_factory=list)
    matched_competencies: List[str] = Field(default_factory=list)
    missing_competencies: List[CompetencyGap] = Field(default_factory=list)
    aspiration_alignment: Optional[AspirationAlignment] = None
    narrative: Optional[CareerNarrative] = None
    note: Optional[str] = None
