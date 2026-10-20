"""
LLM provider layer with tiered fallback.

Public API:
    get_router() -> LLMRouter
    LLMRouter.generate_json(prompt, schema, task, **kw) -> dict

Tiers (in order of attempt for any given task):
    0  gemini-3.1-pro-preview               (Vertex AI, preview)
    0t gemini-3.1-pro-preview-customtools   (Vertex AI, preview; tool-calling)
    1  gemini-2.5-pro                       (Vertex AI, GA)
    2  gemini-2.5-flash                     (Vertex AI, GA, cheap+fast)
    3  ollama:llama3                        (local, last-resort)

Per-task primary tier is defined in `router.TASK_TIER_MAP` so we don't waste
preview-SKU budget on cheap classification work.
"""
from app.services.llm.router import LLMRouter, get_router, Task

__all__ = ["LLMRouter", "get_router", "Task"]
