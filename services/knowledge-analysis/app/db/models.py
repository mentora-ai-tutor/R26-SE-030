from pydantic import BaseModel


class AnalysisResultRecord(BaseModel):
    student_id: str
    mode: str
    overall_mastery: float
    generated_at: str
