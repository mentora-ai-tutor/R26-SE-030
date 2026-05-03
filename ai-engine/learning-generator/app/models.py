from pydantic import BaseModel, Field
from typing import Optional, List


class CodeExecuteRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=50000, description="Java source code to execute")
    context: Optional[str] = Field(None, description="Optional context for AI feedback (e.g., 'practice', 'example', 'debug')")
    stdin: Optional[str] = Field(None, description="Stdin input for Scanner or BufferedReader operations")


class CodeExecuteResponse(BaseModel):
    success: bool
    output: Optional[str]
    error: Optional[str]
    is_compilation_error: bool
    exit_code: Optional[int]


class AIFeedbackRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=50000)
    output: Optional[str] = None
    error: Optional[str] = None
    context: Optional[str] = None


class AIFeedbackResponse(BaseModel):
    feedback: str
    model: str


class CombinedResponse(BaseModel):
    execution: CodeExecuteResponse
    feedback: Optional[str] = None
    model: Optional[str] = None


class AIInsightRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=50000)
    topic: Optional[str] = None
    stepType: Optional[str] = None


class AIInsightResponse(BaseModel):
    insight: str
    model: str
    type: str


class ExplainCodeRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=50000, description="The full Java code")
    highlighted_code: str = Field(..., min_length=1, max_length=5000, description="The specific line or block the user highlighted")
    question: Optional[str] = Field(None, description="Optional follow-up question from the user")


class ExplainCodeResponse(BaseModel):
    explanation: str
    model: str


class FixErrorRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=50000)
    error: str = Field(..., min_length=1, max_length=50000)


class FixErrorResponse(BaseModel):
    suggested_fix: str
    fixed_code: str
    explanation: str
    model: str


class CodeReviewRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=50000)
    focus: Optional[str] = Field(None, description="Review focus: 'performance', 'readability', 'best_practices', or 'all'")


class CodeReviewAnnotation(BaseModel):
    line_start: int
    line_end: int
    category: str
    severity: str
    message: str
    suggestion: str


class CodeReviewResponse(BaseModel):
    annotations: List[CodeReviewAnnotation]
    summary: str
    overall_score: int
    model: str


class FlashcardRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=50000)


class Flashcard(BaseModel):
    concept: str
    definition: str
    example: str
    difficulty: str


class FlashcardResponse(BaseModel):
    flashcards: List[Flashcard]
    model: str


class TestGeneratorRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=50000)
    class_name: Optional[str] = Field(None, description="Class name for the test file")


class TestGeneratorResponse(BaseModel):
    test_code: str
    test_explanation: str
    model: str
