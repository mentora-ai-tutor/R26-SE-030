import logging
import os
from typing import Any, Dict

from openai import OpenAI

logger = logging.getLogger("workspace_assistant")


class WorkspaceAssistantAgent:
    """AI study/coding assistant scoped to a collaborative project workspace.

    Reuses the platform's existing OpenAI configuration with a graceful
    fallback when no API key is configured.
    """

    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            self.client = OpenAI(api_key=api_key)
            self.model_name = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
            logger.info("WorkspaceAssistantAgent initialized with OpenAI API.")
        else:
            self.client = None
            logger.warning("OPENAI_API_KEY not found. Workspace assistant running in fallback mode.")

    def ask(self, question: str, context: str = "", student_id: str = "guest") -> Dict[str, Any]:
        if not self.client:
            return {
                "status": "error",
                "student_id": student_id,
                "reply": "The AI assistant is not configured. Please set OPENAI_API_KEY.",
            }

        if not question or not question.strip():
            return {
                "status": "error",
                "student_id": student_id,
                "reply": "Please provide a question.",
            }

        system_content = (
            "You are an expert Java programming tutor embedded in a collaborative project workspace. "
            "Help the team understand code, debug errors, explain concepts, suggest approaches, and plan tasks. "
            "Be concise, structured, and reference the workspace context when relevant. "
            "Match the language of the user's prompt."
        )

        user_content = question
        if context:
            user_content = f"Workspace context:\n{context}\n\nQuestion:\n{question}"

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.3,
                max_tokens=500,
            )
            return {
                "status": "success",
                "student_id": student_id,
                "reply": response.choices[0].message.content.strip(),
            }
        except Exception as e:
            logger.error(f"Workspace assistant error: {e}")
            return {
                "status": "error",
                "student_id": student_id,
                "reply": "The AI assistant is temporarily unavailable. Please try again shortly.",
            }


workspace_assistant = WorkspaceAssistantAgent()
