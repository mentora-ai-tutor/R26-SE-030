from __future__ import annotations

from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field


class QuizPerformance(BaseModel):
    topic: str
    correct: int
    total: int
    avg_time_seconds: float
    retry_count: int = 0


class SandboxSession(BaseModel):
    topic: str
    compile_attempts: int
    runtime_errors: int
    syntax_errors: int
    logical_errors: int
    time_to_success_seconds: float
    error_correction_latency: float
    keystroke_burst_score: float
    lines_of_code: int


class GitHubCommit(BaseModel):
    timestamp: str
    lines_added: int
    lines_removed: int
    is_big_bang: bool
    refactor_frequency: float
    diff_granularity: float


class LearnerInput(BaseModel):
    student_id: str
    github_enabled: bool = True
    quiz_sessions: List[QuizPerformance]
    sandbox_sessions: List[SandboxSession]
    github_commits: Optional[List[GitHubCommit]] = None


class SubskillDiagnosis(BaseModel):
    subskill: str
    subskill_id: str
    status: Literal["weak", "mastered"]
    evidence: Optional[str] = None
    recommended_content_focus: Optional[str] = None


class SuggestedIntervention(BaseModel):
    primary: str
    secondary: List[str] = Field(default_factory=list)
    difficulty_level: str
    estimated_time_minutes: int
    learning_objectives: List[str] = Field(default_factory=list)


class KnowledgeGap(BaseModel):
    topic: str
    topic_id: str
    gap_type: Literal["FUNDAMENTAL_GAP", "PARTIAL_GAP", "SURFACE_GAP"]
    confidence: float = Field(ge=0, le=1)
    mastery_score: float = Field(ge=0, le=100)
    weak_subskills: List[SubskillDiagnosis] = Field(default_factory=list)
    known_subskills: List[SubskillDiagnosis] = Field(default_factory=list)
    misconceptions: List[str] = Field(default_factory=list)
    observed_error_patterns: dict[str, list[str]] = Field(default_factory=dict)
    evidence_summary: str
    prerequisite_topics: List[str] = Field(default_factory=list)
    related_topics: List[str] = Field(default_factory=list)
    suggested_intervention: SuggestedIntervention


class Strength(BaseModel):
    topic: str
    topic_id: str
    confidence: float = Field(ge=0, le=1)
    mastery_score: float = Field(ge=0, le=100)
    mastery_level: Literal["beginner", "proficient", "advanced"]
    evidence_summary: str
    known_subskills: List[SubskillDiagnosis] = Field(default_factory=list)
    can_teach_others: bool = False


class MasteryProfilePayload(BaseModel):
    overall_mastery_score: float = Field(ge=0, le=100)
    knowledge_gaps: List[KnowledgeGap] = Field(default_factory=list)
    strengths: List[Strength] = Field(default_factory=list)


class CanonicalMasteryOutput(BaseModel):
    schema_version: str
    student_id: str
    analysis_timestamp: str
    data_sources: dict[str, str]
    mastery_profile: MasteryProfilePayload
    recommendations: dict[str, Any]
    overall_mastery_score: float = Field(ge=0, le=100)
    knowledge_gaps: List[KnowledgeGap] = Field(default_factory=list)
    strengths: List[Strength] = Field(default_factory=list)
    gap_topic_ids: List[str] = Field(default_factory=list)
    raw_analysis_payload: dict[str, Any] = Field(default_factory=dict)
