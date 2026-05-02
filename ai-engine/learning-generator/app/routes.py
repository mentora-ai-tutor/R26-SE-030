import logging
from fastapi import APIRouter
from app.models import CodeExecuteRequest, AIFeedbackRequest, AIInsightRequest, CodeExecuteResponse, AIFeedbackResponse, AIInsightResponse, CombinedResponse
from app.services.executor import execute_java_code
from app.services.ollama_service import generate_feedback, explain_simpler, real_life_analogy
from app.config import OLLAMA_MODEL

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/execute", response_model=CodeExecuteResponse)
async def execute_code(req: CodeExecuteRequest):
    result = execute_java_code(req.code)
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
    result = execute_java_code(req.code)

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
