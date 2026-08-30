import os
import logging
from typing import Dict, Any
from openai import OpenAI

logger = logging.getLogger("support_agent")


class SupportAgent:
    """
    Support Agent that handles student doubts, Java syntax help,
    and platform guidance using the system's existing OpenAI API configuration.
    """

    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")

        if api_key:
            self.client = OpenAI(api_key=api_key)
            self.model_name = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
            logger.info("SupportAgent successfully initialized with OpenAI API.")
        else:
            self.client = None
            logger.warning("OPENAI_API_KEY environment variable not found. Running in fallback mode.")

    def get_response(self, user_message: str, student_id: str = "guest", knowledge_gap_context: str = None) -> Dict[str, Any]:
        """
        Processes student input and generates an AI-powered response.
        When knowledge_gap_context is provided, the AI references the student's
        weak areas to ask targeted questions and give focused guidance.
        """
        if not self.client:
            return {
                "status": "error",
                "student_id": student_id,
                "reply": "API configuration missing. Please ensure OPENAI_API_KEY is set in your environment file."
            }

        if not user_message or not user_message.strip():
            return {
                "status": "error",
                "student_id": student_id,
                "reply": "Please provide a valid question or message."
            }

        system_content = (
            "You are an encouraging and expert Java Pedagogy AI Assistant. "
            "Help students understand Java concepts, debug syntax errors, "
            "and navigate the learning platform effectively. "
            "Keep responses concise, well-structured, clear, and easy to read. "
            "Match the language of the student's prompt."
        )

        if knowledge_gap_context:
            system_content += (
                "\n\nThe student has the following knowledge gaps and weak areas. "
                "Reference these when asking questions or giving guidance — "
                "focus on strengthening these specific topics:\n\n"
                f"{knowledge_gap_context}"
            )

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {
                        "role": "system",
                        "content": system_content,
                    },
                    {
                        "role": "user",
                        "content": user_message
                    }
                ],
                temperature=0.7,
                max_tokens=400
            )

            reply_text = response.choices[0].message.content.strip()

            return {
                "status": "success",
                "student_id": student_id,
                "reply": reply_text
            }

        except Exception as e:
            logger.error(f"OpenAI API Error in SupportAgent: {str(e)}")
            return {
                "status": "error",
                "student_id": student_id,
                "reply": "An error occurred while processing your request with OpenAI. Please try again shortly."
            }


# Export a single global instance for use across application routes
support_agent = SupportAgent()