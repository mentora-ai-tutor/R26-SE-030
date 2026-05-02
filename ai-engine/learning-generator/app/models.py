from pydantic import BaseModel, Field
from typing import Optional


class CodeExecuteRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=50000, description="Java source code to execute")
    context: Optional[str] = Field(None, description="Optional context for AI feedback (e.g., 'practice', 'example', 'debug')")


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
    code: str = Field(..., min_length=1, max_length=50000)
    topic: Optional[str] = None


class AIInsightResponse(BaseModel):
    insight: str
    model: str
    type: str
