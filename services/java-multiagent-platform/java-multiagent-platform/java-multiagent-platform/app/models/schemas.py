from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

# ==========================================
# 1. Knowledge Gap & Onboarding Schemas
# ==========================================

class WeakSubskill(BaseModel):
    subskill: str
    subskill_id: str
    status: str
    evidence: Optional[str] = None
    recommended_content_focus: Optional[str] = None


class SuggestedIntervention(BaseModel):
    primary: str
    secondary: List[str]
    difficulty_level: str
    estimated_time_minutes: int
    learning_objectives: List[str]


class KnowledgeGap(BaseModel):
    topic: str
    topic_id: str
    gap_type: str
    confidence: float
    mastery_score: int
    weak_subskills: List[WeakSubskill]
    misconceptions: List[str]
    suggested_intervention: SuggestedIntervention


class StudentMasteryProfile(BaseModel):
    overall_mastery_score: int
    knowledge_gaps: List[KnowledgeGap]


class OnboardingJSONRequest(BaseModel):
    student_id: str
    mastery_profile: StudentMasteryProfile


# ==========================================
# 2. Diagnostic Quiz Evaluation Schemas
# ==========================================

class StudentAnswer(BaseModel):
    topic_id: str
    selected_option: str
    correct_option: str


class QuizEvaluationRequest(BaseModel):
    student_id: str
    initial_mastery_score: int
    answers: List[StudentAnswer]


# ==========================================
# 3. Peer Matching Schemas
# ==========================================

class PeerMatchRequest(BaseModel):
    student_id: str
    topic: str
    target_role: Optional[str] = "peer_learner"


class PeerMatchResponse(BaseModel):
    status: str
    matched_peer_id: Optional[str] = None
    match_score: float
    message: str
    room_id: Optional[str] = None
    notification_id: Optional[str] = None


# ==========================================
# 4. Code Assessment Schemas
# ==========================================

class CodeReviewRequest(BaseModel):
    student_id: str
    code: str
    language: Optional[str] = "java"


class CodeReviewResponse(BaseModel):
    status: str
    score: int
    feedback: str


# ==========================================
# 5. RAG Content Recommendation Schemas
# ==========================================

class RecommendationRequest(BaseModel):
    student_id: str
    topic: str
    weak_subskill: Optional[str] = None
    target_subskill: Optional[str] = None  # Backwards Compatibility
    misconception: Optional[str] = "None"
    difficulty_level: Optional[str] = "beginner"


class RecommendationResponse(BaseModel):
    status: str
    student_id: str
    topic: str
    weak_subskill: str
    tutorial_title: str
    concept_summary: str
    key_highlights: List[str]
    common_pitfalls: List[str]
    practice_code_snippet: str
    suggested_exercise: Optional[str] = None


# ==========================================
# 6. Individual Quiz System Schemas (Code-Based & Hints)
# ==========================================

class IndividualQuizStartRequest(BaseModel):
    student_id: str
    topic: str
    difficulty_level: Optional[str] = "beginner"


class OpenQuestionItem(BaseModel):
    """Open-ended Code-based Quiz එකේ ප්‍රශ්නය සහ Hint එක"""
    id: int
    question: str
    hint: Optional[str] = Field(None, description="ප්‍රශ්නය විසඳීමට ලබාදෙන තාක්ෂණික ඉඟිය (Hint)")


class IndividualQuizStartResponse(BaseModel):
    status: str
    session_id: str
    total_questions: int = 7
    question_index: int = 0
    first_question: OpenQuestionItem


class SubmitAnswerRequest(BaseModel):
    student_answer: str = Field(..., description="ශිෂ්‍යයා ලබාදුන් Code හෝ Text පිළිතුර")


class AnswerFeedbackResponse(BaseModel):
    status: str
    is_correct: bool
    correct_answer: str
    explanation: str
    next_question: Optional[OpenQuestionItem] = None
    is_quiz_completed: bool = False


class QuizSummaryResponse(BaseModel):
    status: str
    session_id: str
    student_id: str
    topic: str
    total_questions: int
    correct_answers: int
    score_percentage: float
    detailed_history: List[Dict[str, Any]]