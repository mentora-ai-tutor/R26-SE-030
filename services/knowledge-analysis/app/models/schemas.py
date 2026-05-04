from typing import List, Optional

from pydantic import BaseModel


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
