import pytest
from pydantic import ValidationError

from app.models import (
    CodeExecuteRequest,
    AIFeedbackRequest,
    CodeReviewRequest,
    CodeReviewAnnotation,
    CodeExecuteResponse,
)


def test_code_execute_request_valid():
    req = CodeExecuteRequest(code="public class A {}", stdin="x", context="practice")
    assert req.code == "public class A {}"
    assert req.stdin == "x"


def test_code_execute_request_rejects_empty_code():
    with pytest.raises(ValidationError):
        CodeExecuteRequest(code="")


def test_feedback_request_allows_optional_fields():
    req = AIFeedbackRequest(code="class A {}", output="hi", error=None)
    assert req.output == "hi"
    assert req.error is None


def test_code_review_annotation_valid():
    ann = CodeReviewAnnotation(
        line_start=1, line_end=2, category="style",
        severity="low", message="m", suggestion="s",
    )
    assert ann.line_start >= 0
    assert ann.severity == "low"


def test_code_review_request_rejects_missing_code():
    with pytest.raises(ValidationError):
        CodeReviewRequest()


def test_code_execute_response_roundtrip():
    resp = CodeExecuteResponse(
        success=True, output="ok", error=None,
        is_compilation_error=False, exit_code=0,
    )
    assert resp.model_dump()["success"] is True
