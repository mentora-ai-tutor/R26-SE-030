from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


# ─── Enums ───────────────────────────────────────────────────────────────────

class GapType(str, Enum):
    FUNDAMENTAL_GAP = "FUNDAMENTAL_GAP"
    PARTIAL_GAP = "PARTIAL_GAP"


class MasteryLevel(str, Enum):
    ADVANCED = "advanced"
    PROFICIENT = "proficient"
    BEGINNER = "beginner"


class SessionStatus(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"
    WAITING = "waiting"


class PairingType(str, Enum):
    RECIPROCAL = "RECIPROCAL"
    ONE_WAY = "ONE_WAY"


class GroupRole(str, Enum):
    EXPLAINER = "EXPLAINER"
    SOLVER = "SOLVER"
    REVIEWER = "REVIEWER"


class ActivityType(str, Enum):
    CODING = "coding"
    DEBUGGING = "debugging"
    MINI_PROJECT = "mini_project"


class NotificationStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class StudentStatus(str, Enum):
    ACTIVE = "active"
    IN_SESSION = "in_session"
    COMPLETE = "complete"


# ─── Input Models (from JSON import) ─────────────────────────────────────────

class KnowledgeGap(BaseModel):
    topic: str
    topic_id: str
    gap_type: GapType
    confidence: float
    mastery_score: Optional[float] = 0.0
    completed: bool = False


class Strength(BaseModel):
    topic: str
    topic_id: str
    confidence: float
    mastery_level: MasteryLevel
    can_teach_others: bool


class MasteryProfile(BaseModel):
    overall_mastery_score: float
    knowledge_gaps: List[KnowledgeGap] = []
    strengths: List[Strength] = []


class DataSources(BaseModel):
    github: Optional[str] = None
    sandbox: Optional[str] = None
    quizzes: Optional[str] = None

    model_config = {"extra": "allow"}


class StudentImport(BaseModel):
    student_id: str
    analysis_timestamp: Optional[datetime] = None
    data_sources: Optional[DataSources] = None
    mastery_profile: MasteryProfile

    model_config = {"extra": "ignore"}


# ─── DB Models ────────────────────────────────────────────────────────────────

class StudentDB(BaseModel):
    student_id: str
    analysis_timestamp: Optional[datetime] = None
    data_sources: Optional[Dict[str, Any]] = None
    mastery_profile: MasteryProfile
    current_weak_topic: Optional[str] = None
    current_session_id: Optional[str] = None
    session_history: List[str] = []
    improved_topics: List[str] = []
    mastered_topics: List[str] = []
    status: StudentStatus = StudentStatus.ACTIVE
    initial_mastery_score: Optional[float] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class QuestionLog(BaseModel):
    question_id: str
    bloom_level: int
    correct: bool
    hints_used: int
    time_taken_seconds: Optional[int] = None
    asked_teacher: bool = False
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class PairSession(BaseModel):
    session_id: str
    teacher_id: str
    learner_id: str
    topic_id: str
    topic_name: str
    pairing_type: PairingType = PairingType.ONE_WAY
    status: SessionStatus = SessionStatus.ACTIVE
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    questions_asked: int = 0
    correct_answers: int = 0
    hints_used_by_learner: int = 0
    hints_used_by_teacher: int = 0
    help_requests: int = 0
    question_log: List[QuestionLog] = []
    performance_score: Optional[float] = None
    current_bloom_level: int = 1
    consecutive_correct: int = 0
    consecutive_incorrect: int = 0
    current_question_id: Optional[str] = None
    learner_initial_mastery: float = 0.0
    teacher_score: Optional[float] = None


class GroupMember(BaseModel):
    student_id: str
    role: GroupRole
    score: Optional[float] = None


class GroupSession(BaseModel):
    session_id: str
    topic_id: str
    topic_name: str
    members: List[GroupMember]
    activity_type: ActivityType
    status: SessionStatus = SessionStatus.ACTIVE
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    problem_statement: Optional[str] = None
    explainer_guide: Optional[str] = None
    solver_starter: Optional[str] = None
    reviewer_checklist: Optional[str] = None
    expected_solution: Optional[str] = None
    session_number: int = 1
    group_average_score: Optional[float] = None
    chat_log: List[Dict[str, Any]] = []
    sandbox_code: Optional[str] = None


class ImprovedPoolEntry(BaseModel):
    student_id: str
    topic_id: str
    topic_name: str
    mastery_score: float
    added_at: datetime = Field(default_factory=datetime.utcnow)
    teaching_ability: str = "not_yet"
    consecutive_group_sessions_above_threshold: int = 0
    group_session_ids: List[str] = []


class VerifiedPoolEntry(BaseModel):
    student_id: str
    topic_id: str
    topic_name: str
    verification_date: datetime = Field(default_factory=datetime.utcnow)
    final_mastery_score: float
    teaching_certified: bool = True


class WaitingQueueEntry(BaseModel):
    queue_id: str
    student_id: str
    topic_id: str
    topic_name: str
    gap_type: GapType
    waiting_since: datetime = Field(default_factory=datetime.utcnow)
    priority_score: float = 0.0
    attempts: int = 0
    status: str = "waiting"


class Notification(BaseModel):
    notification_id: str
    student_id: str
    teacher_id: str
    topic_id: str
    topic_name: str
    message: str
    expires_at: datetime
    status: NotificationStatus = NotificationStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Question(BaseModel):
    question_id: str
    question_text: str
    bloom_level: int
    expected_answer: str
    hints: List[str]
    time_limit_seconds: int = 120
    topic_id: str
    topic_name: str
    difficulty: int
    session_id: str
    session_type: str = "pair"
    generated_by: str = "gemma4"
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    used_count: int = 1
    success_rate: float = 0.0
    average_hints_used: float = 0.0
    average_time_taken: float = 0.0
    flagged_for_review: bool = False


class BatchPairingRecord(BaseModel):
    batch_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    topics_processed: List[str] = []
    sessions_created: int = 0
    students_paired: int = 0
    students_queued: int = 0
    details: List[Dict[str, Any]] = []


# ─── API Request/Response Models ──────────────────────────────────────────────

class ImportRequest(BaseModel):
    students: List[StudentImport]


class AnswerSubmission(BaseModel):
    answer: str
    time_taken_seconds: Optional[int] = None


class TeacherMessage(BaseModel):
    message: str
    sandbox_code: Optional[str] = None


class GroupSubmission(BaseModel):
    role: GroupRole
    task_completion_score: float = Field(ge=0, le=100)
    collaboration_score: float = Field(ge=0, le=100)
    communication_score: float = Field(ge=0, le=100)


class PerformanceReport(BaseModel):
    student_id: str
    topic_id: str
    topic_name: str
    pair_sessions: List[Dict[str, Any]]
    group_sessions: List[Dict[str, Any]]
    teaching_sessions: List[Dict[str, Any]]
    final_mastery: Optional[float]
    verification_date: Optional[datetime]


class CompletionReport(BaseModel):
    student_id: str
    initial_overall_mastery: float
    final_overall_mastery: float
    topics_mastered: List[Dict[str, Any]]
    pair_sessions_completed: int
    group_sessions_completed: int
    topics_can_teach: List[str]
    total_time_seconds: Optional[int]
    completion_date: datetime