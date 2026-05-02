import httpx
import logging
from app.config import OLLAMA_BASE_URL, OLLAMA_MODEL

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are Mentora AI, an expert Java programming tutor. Analyze the student's code and provide helpful, encouraging feedback.

Rules:
- Keep responses concise (3-5 sentences max)
- Be encouraging and positive
- If there's an error, explain what it means in simple terms and hint at how to fix it
- If the code is correct, praise them and suggest one way to improve or experiment
- Never give away the full solution for practice challenges
- Use plain English, no markdown formatting needed"""

SYSTEM_PROMPT_SIMPLE = """You are Mentora AI, a Java tutor who explains concepts to complete beginners. Your job is to simplify complex code.

Rules:
- Explain like the student is 12 years old
- Use very simple words and short sentences
- Avoid technical jargon — replace terms like "recursion" with "calling itself"
- Break down what the code does line by line if needed
- Keep it under 5-6 short paragraphs"""

SYSTEM_PROMPT_ANALOGY = """You are Mentora AI, a creative Java tutor who explains programming using real-world comparisons.

Rules:
- Give exactly one clear, creative real-world analogy
- Connect the analogy directly to how the code works
- Keep it under 3-4 short paragraphs
- After the analogy, briefly map the real-world elements back to the code (e.g., "The factory worker = the method, the blueprint = the class")"""


async def _call_ollama(messages: list, temperature: float = 0.7, num_predict: int = 300) -> str:
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": OLLAMA_MODEL,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": temperature,
                        "num_predict": num_predict,
                    },
                },
            )
            response.raise_for_status()
            data = response.json()
            return data.get("message", {}).get("content", "").strip()
    except httpx.TimeoutException:
        logger.error("Ollama request timed out")
        return "Response is taking longer than usual. Please try again."
    except Exception as e:
        logger.error(f"Ollama request failed: {str(e)}")
        return "Unable to generate response right now. Please try again."


async def generate_feedback(code: str, output: str = None, error: str = None, context: str = None) -> str:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    user_prompt = "Student submitted this Java code:\n\n"
    user_prompt += f"```java\n{code}\n```\n\n"

    if error:
        user_prompt += f"This code produced an error:\n{error}\n\n"
        user_prompt += "Explain the error in simple terms and give a hint on how to fix it."
    elif output:
        user_prompt += f"The output was:\n{output}\n\n"
        if context:
            user_prompt += f"Context: {context}\n\n"
        user_prompt += "Provide feedback on their solution. Is it correct? What could they improve?"
    else:
        user_prompt += "Review this code and give helpful feedback."

    messages.append({"role": "user", "content": user_prompt})

    result = await _call_ollama(messages)
    logger.info("AI feedback generated successfully")
    return result


async def explain_simpler(content: str, topic: str = None, step_type: str = None) -> str:
    messages = [{"role": "system", "content": SYSTEM_PROMPT_SIMPLE}]

    step_labels = {
        "intro": "introduction section",
        "concepts": "concept explanation",
        "guide": "step-by-step guide",
        "example": "code example",
        "mistakes": "common mistakes section",
        "practice": "practice challenge",
        "debug": "debugging exercise",
    }
    step_label = step_labels.get(step_type, "section") if step_type else "section"

    if step_type in ["example", "practice", "debug"]:
        user_prompt = f"Here is some Java code from the {step_label}:\n\n```java\n{content}\n```\n\n"
    else:
        user_prompt = f"Here is a {step_label} from a Java tutorial about {topic}:\n\n{content}\n\n"

    if topic:
        user_prompt += f"This is about: {topic}\n\n"
    user_prompt += "Explain what this does in the simplest way possible."

    messages.append({"role": "user", "content": user_prompt})

    result = await _call_ollama(messages)
    logger.info("Simpler explanation generated")
    return result


async def real_life_analogy(content: str, topic: str = None, step_type: str = None) -> str:
    messages = [{"role": "system", "content": SYSTEM_PROMPT_ANALOGY}]

    step_labels = {
        "intro": "introduction section",
        "concepts": "concept explanation",
        "guide": "step-by-step guide",
        "example": "code example",
        "mistakes": "common mistakes section",
        "practice": "practice challenge",
        "debug": "debugging exercise",
    }
    step_label = step_labels.get(step_type, "section") if step_type else "section"

    if step_type in ["example", "practice", "debug"]:
        user_prompt = f"Here is some Java code from the {step_label}:\n\n```java\n{content}\n```\n\n"
    else:
        user_prompt = f"Here is a {step_label} from a Java tutorial about {topic}:\n\n{content}\n\n"

    if topic:
        user_prompt += f"This concept is about: {topic}\n\n"
    user_prompt += "Give me a creative real-world analogy that helps me understand how this works."

    messages.append({"role": "user", "content": user_prompt})

    result = await _call_ollama(messages)
    logger.info("Real-life analogy generated")
    return result
