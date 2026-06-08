"""Generation contract for LLM-authored sandbox coding challenges.

Gemini returns a `reference_solution` (a complete runnable program) alongside the
student-facing `starter_code`. The backend runs that reference solution through the
ai-engine to capture the *real* stdout — that becomes the authoritative
`expected_output`, so a hallucinated expected value can never reach a student.
"""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

ChallengeDifficulty = Literal["easy", "medium", "hard"]


class GeneratedChallenge(BaseModel):
    title: str
    topic: str
    difficulty: ChallengeDifficulty
    prompt: str
    starter_code: str
    reference_solution: str
    stdin: Optional[str] = None


class GeneratedChallengeBatch(BaseModel):
    challenges: List[GeneratedChallenge] = Field(default_factory=list)
