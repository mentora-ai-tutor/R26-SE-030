import logging
from fastapi import APIRouter
from app.models import (
    CodeExecuteRequest, AIFeedbackRequest, AIInsightRequest,
    CodeExecuteResponse, AIFeedbackResponse, AIInsightResponse, CombinedResponse,
    ExplainCodeRequest, ExplainCodeResponse,
    FixErrorRequest, FixErrorResponse,
    CodeReviewRequest, CodeReviewResponse, CodeReviewAnnotation,
    FlashcardRequest, FlashcardResponse, Flashcard,
    TestGeneratorRequest, TestGeneratorResponse,
)
from app.services.executor import execute_java_code
from app.services.ollama_service import (
    generate_feedback, explain_simpler, real_life_analogy,
    explain_highlighted_code, suggest_fix, code_review,
    generate_flashcards, generate_test_cases,
)
from app.config import OLLAMA_MODEL

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/execute", response_model=CodeExecuteResponse)
async def execute_code(req: CodeExecuteRequest):
    result = execute_java_code(req.code, stdin_input=req.stdin)
    return CodeExecuteResponse(**result)


@router.post("/feedback", response_model=AIFeedbackResponse)
async def get_ai_feedback(req: AIFeedbackRequest):
    feedback = await generate_feedback(
        code=req.code,
        output=req.output,
        error=req.error,
        context=req.context,
    )
    return AIFeedbackResponse(feedback=feedback, model=OLLAMA_MODEL)


@router.post("/run-with-feedback", response_model=CombinedResponse)
async def run_with_feedback(req: CodeExecuteRequest):
    result = execute_java_code(req.code, stdin_input=req.stdin)

    execution_resp = CodeExecuteResponse(**result)

    feedback = None
    model = None

    if result["success"] or result["error"]:
        try:
            feedback = await generate_feedback(
                code=req.code,
                output=result["output"],
                error=result["error"],
                context=req.context,
            )
            model = OLLAMA_MODEL
        except Exception as e:
            logger.error(f"AI feedback failed: {str(e)}")
            feedback = "AI feedback unavailable right now."

    return CombinedResponse(
        execution=execution_resp,
        feedback=feedback,
        model=model,
    )


@router.post("/explain-simpler", response_model=AIInsightResponse)
async def explain_code_simpler(req: AIInsightRequest):
    insight = await explain_simpler(content=req.content, topic=req.topic, step_type=req.stepType)
    return AIInsightResponse(insight=insight, model=OLLAMA_MODEL, type="explain_simpler")


@router.post("/analogy", response_model=AIInsightResponse)
async def get_real_life_analogy(req: AIInsightRequest):
    insight = await real_life_analogy(content=req.content, topic=req.topic, step_type=req.stepType)
    return AIInsightResponse(insight=insight, model=OLLAMA_MODEL, type="analogy")


@router.post("/explain-code", response_model=ExplainCodeResponse)
async def explain_highlighted(req: ExplainCodeRequest):
    explanation = await explain_highlighted_code(
        code=req.code,
        highlighted_code=req.highlighted_code,
        question=req.question,
    )
    return ExplainCodeResponse(explanation=explanation, model=OLLAMA_MODEL)


@router.post("/fix-error", response_model=FixErrorResponse)
async def fix_error(req: FixErrorRequest):
    result = await suggest_fix(code=req.code, error=req.error)

    fixed_code = result.get("fixed_code", "")
    suggested_fix = result.get("suggested_fix", "")
    explanation = result.get("explanation", "")

    if isinstance(explanation, list):
        explanation = " ".join(str(e) for e in explanation)
    if isinstance(suggested_fix, list):
        suggested_fix = " ".join(str(s) for s in suggested_fix)

    return FixErrorResponse(
        suggested_fix=str(suggested_fix),
        fixed_code=str(fixed_code),
        explanation=str(explanation),
        model=OLLAMA_MODEL,
    )


@router.post("/code-review", response_model=CodeReviewResponse)
async def review_code(req: CodeReviewRequest):
    result = await code_review(code=req.code, focus=req.focus)
    annotations = [
        CodeReviewAnnotation(**ann) for ann in result.get("annotations", [])
    ]
    return CodeReviewResponse(
        annotations=annotations,
        summary=result.get("summary", ""),
        overall_score=result.get("overall_score", 0),
        model=OLLAMA_MODEL,
    )


@router.post("/flashcards", response_model=FlashcardResponse)
async def get_flashcards(req: FlashcardRequest):
    result = await generate_flashcards(code=req.code)
    flashcards = [Flashcard(**card) for card in result if isinstance(card, dict)]
    return FlashcardResponse(flashcards=flashcards, model=OLLAMA_MODEL)


@router.post("/generate-tests", response_model=TestGeneratorResponse)
async def generate_tests(req: TestGeneratorRequest):
    result = await generate_test_cases(code=req.code, class_name=req.class_name)
    return TestGeneratorResponse(
        test_code=result.get("test_code", ""),
        test_explanation=result.get("test_explanation", ""),
        model=OLLAMA_MODEL,
    )
