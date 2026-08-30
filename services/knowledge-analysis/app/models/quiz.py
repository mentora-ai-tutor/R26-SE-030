"""Pydantic models for the adaptive Java quiz (Skill Check panel + sandbox ladder).

Three layers live here:
  * the *generation contract* (`GeneratedQuestionBatch`) — the strict JSON shape the
    LLM router must return for `Task.QUESTION_GEN`;
  * the *API request* models the quiz routes accept;
  * everything served to the browser is a plain dict assembled in ``quiz_store`` with
    the answer key stripped out, so it is intentionally not modelled here.
"""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from app.models.schemas import QuizPerformance

Difficulty = Literal["easy", "medium", "hard"]
QuestionType = Literal["mcq", "predict_output"]
OptionId = Literal["A", "B", "C", "D"]


class MCQOption(BaseModel):
    id: OptionId
    text: str


# ---- LLM generation contract (what Gemini must return) -----------------------
class GeneratedQuestion(BaseModel):
    topic: str
    difficulty: Difficulty
    # "predict_output" questions carry a code_snippet and the options are the
    # candidate program outputs — so they are graded deterministically (no runner).
    type: QuestionType = "mcq"
    question: str
    code_snippet: Optional[str] = None
    options: List[MCQOption] = Field(default_factory=list)
    correct_option_id: OptionId
    explanation: str
    concept_tested: str = ""


class GeneratedQuestionBatch(BaseModel):
    questions: List[GeneratedQuestion] = Field(default_factory=list)


# ---- API request models ------------------------------------------------------
class StartQuizRequest(BaseModel):
    mode: Literal["repo-aware", "sandbox", "onboarding"] = "sandbox"
    topics: Optional[List[str]] = Field(
        default=None,
        description="Java topics to draw from. Defaults to the core set when omitted.",
    )
    job_id: Optional[str] = Field(
        default=None,
        description="Optional review job this skill-check runs alongside (for analytics).",
    )
    max_questions: Optional[int] = Field(default=None, ge=1, le=20)


class AnswerQuizRequest(BaseModel):
    qid: str = Field(..., min_length=1)
    chosen_option_id: OptionId
    time_seconds: float = Field(default=0.0, ge=0)


# ---- Persisted result contract (consumed by other teams/services) ------------
class QuizQuestionResult(BaseModel):
    """One answered question inside a completed quiz result."""

    qid: str
    topic: str
    difficulty: Difficulty
    type: QuestionType
    correct: bool
    chosen_option_id: OptionId
    time_seconds: float


class QuizResultRecord(BaseModel):
    """Cross-team contract — one document per COMPLETED quiz, stored in ``quiz_results``.

    Other services should read this collection (or ``quiz_sessions.results``) to consume
    MCQ outcomes. ``topic_performance`` matches ``schemas.QuizPerformance`` exactly, so it
    can be fed directly into ``POST /analyze`` as ``quiz_sessions``.

    Lookup: ``GET /api/v1/quiz/results/{student_id}/latest`` and
    ``GET /api/v1/quiz/results/{student_id}`` (keyed on public or internal student id).
    """

    session_id: str
    student_id: Optional[str] = None
    public_student_id: Optional[str] = None
    mode: str
    job_id: Optional[str] = None
    schema_version: str
    score_percent: float
    correct: int
    total: int
    difficulty_reached: Difficulty = Field(
        ..., description="The hardest difficulty rung the student actually answered."
    )
    topic_performance: List[QuizPerformance]
    questions: List[QuizQuestionResult]
    completed_at: Optional[str] = None
    created_at: Optional[str] = None
    result_id: Optional[str] = None
    # Present only when reconstructed from quiz_sessions because the dedicated
    # quiz_results insert was missing; absent on normal records.
    recovered_from: Optional[str] = None
