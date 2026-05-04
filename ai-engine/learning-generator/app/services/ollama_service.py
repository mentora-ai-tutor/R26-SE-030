import httpx
import json
import logging
import re
from app.config import OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_CODE_MODEL

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

SYSTEM_PROMPT_EXPLAIN = """You are Mentora AI, a Java expert who explains specific lines of code to students.

Rules:
- Explain ONLY the highlighted code section
- Start with a one-line summary of what it does
- Break down how each part works in simple terms
- Keep it under 3-4 short paragraphs
- Use plain English, no markdown needed"""

SYSTEM_PROMPT_FIX = """You are Mentora AI, an expert Java developer who fixes student code errors.

Rules:
- Analyze the error and identify the ROOT cause
- Return the COMPLETE fixed code — do not omit any parts
- Add a // FIX: comment on every line you changed, explaining what was wrong and why you fixed it
- Keep the rest of the code exactly as the student wrote it
- Return ONLY valid JSON with no extra text before or after
- Escape all newlines and quotes in the fixed_code string properly"""

SYSTEM_PROMPT_REVIEW = """You are Mentora AI, a senior Java developer conducting a code review.

Rules:
- Analyze the code for performance issues, readability, and Java best practices
- Provide specific line numbers for each annotation
- Be constructive and encouraging
- Give an overall score from 1-10
- Format annotations as JSON array with: line_start, line_end, category, severity (low/medium/high), message, suggestion
- Provide a 2-3 sentence summary"""

SYSTEM_PROMPT_FLASHCARDS = """You are Mentora AI, a Java educator who creates concept flashcards from code.

Rules:
- Identify 3-5 key Java concepts used in the code (e.g., arrays, loops, OOP, exceptions)
- For each concept provide: concept name, simple definition, a mini code example, difficulty (beginner/intermediate/advanced)
- Format as JSON array
- Keep definitions under 2 sentences
- Keep examples under 3 lines"""

SYSTEM_PROMPT_TESTS = """You are Mentora AI, a Java developer who writes JUnit test cases.

Rules:
- Generate complete JUnit 5 test class for the provided code
- Include tests for normal cases, edge cases, and error cases
- Use @Test, @DisplayName, and assertEquals/assertThrows appropriately
- Return valid Java code only (no markdown wrappers)
- Explain each test case in 1-2 sentences
- Use JUnit 5 imports: org.junit.jupiter.api.*"""


async def _call_ollama(messages: list, temperature: float = 0.7, num_predict: int = 300, model: str = None) -> str:
    model = model or OLLAMA_MODEL
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{OLLAMA_BASE_URL}/api/chat",
                json={
                    "model": model,
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


async def _call_ollama_json(messages: list, temperature: float = 0.3, num_predict: int = 800, model: str = None) -> dict:
    model = model or OLLAMA_MODEL
    raw = await _call_ollama(messages, temperature=temperature, num_predict=num_predict, model=model)
    logger.info(f"Raw JSON response [{model}] (first 600): {raw[:600]}")

    # Strategy 1: Extract from code fences
    code_block_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', raw)
    if code_block_match:
        candidate = code_block_match.group(1).strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # Strategy 2: Find the outermost balanced JSON object
    candidate = _find_balanced_json(raw)
    if candidate:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # Strategy 3: Try fixing common LLM JSON issues
    fixed = _fix_llm_json(raw)
    if fixed:
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass

    logger.error(f"All JSON parsing strategies failed. Raw: {raw[:600]}")
    return {}


def _find_balanced_json(text: str) -> str | None:
    # Try both array and object starts
    for start_char, end_char in [('[', ']'), ('{', '}')]:
        start = text.find(start_char)
        if start == -1:
            continue
        depth = 0
        in_string = False
        escape_next = False
        for i in range(start, len(text)):
            ch = text[i]
            if escape_next:
                escape_next = False
                continue
            if ch == '\\':
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == start_char:
                depth += 1
            elif ch == end_char:
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
    return None


def _fix_llm_json(raw: str) -> str | None:
    candidate = _find_balanced_json(raw)
    if not candidate:
        return None
    # Fix unescaped newlines inside strings
    fixed = []
    in_string = False
    escape_next = False
    for i, ch in enumerate(candidate):
        if escape_next:
            escape_next = False
            fixed.append(ch)
            continue
        if ch == '\\':
            escape_next = True
            fixed.append(ch)
            continue
        if ch == '"':
            in_string = not in_string
            fixed.append(ch)
            continue
        if in_string and ch == '\n':
            fixed.append('\\n')
        elif in_string and ch == '\t':
            fixed.append('\\t')
        elif in_string and ch == '"':
            fixed.append('\\"')
        else:
            fixed.append(ch)
    return ''.join(fixed)


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


async def explain_highlighted_code(code: str, highlighted_code: str, question: str = None) -> str:
    messages = [{"role": "system", "content": SYSTEM_PROMPT_EXPLAIN}]

    user_prompt = f"Here is the full code context:\n```java\n{code}\n```\n\n"
    user_prompt += f"The student highlighted this part:\n```java\n{highlighted_code}\n```\n\n"
    if question:
        user_prompt += f"Their question: {question}\n\n"
    user_prompt += "Explain what this highlighted code does in simple terms."

    messages.append({"role": "user", "content": user_prompt})

    result = await _call_ollama(messages, num_predict=400)
    logger.info("Highlighted code explanation generated")
    return result


async def suggest_fix(code: str, error: str) -> dict:
    messages = [{"role": "system", "content": SYSTEM_PROMPT_FIX}]

    user_prompt = f"STUDENT CODE:\n{code}\n\n"
    user_prompt += f"ERROR MESSAGE:\n{error}\n\n"
    user_prompt += "Return ONLY a JSON object with these three keys:\n"
    user_prompt += '"suggested_fix": "2-3 sentences explaining what was wrong and how you fixed it",\n'
    user_prompt += '"fixed_code": "the COMPLETE corrected Java code. On every line you changed, add this comment at the end: // FIX: brief reason",\n'
    user_prompt += '"explanation": "step-by-step breakdown of the error and why the fix works"'

    messages.append({"role": "user", "content": user_prompt})

    result = await _call_ollama_json(messages, num_predict=800)

    if not result or "fixed_code" not in result or not result["fixed_code"].strip():
        logger.warning("Fix endpoint returned empty or invalid result, retrying with stricter prompt")
        retry_messages = [{"role": "system", "content": "You are a JSON-only API. Return ONLY a JSON object. No text before or after. Escape all newlines as \\n and quotes as \\\" inside strings."}]
        retry_messages.append({"role": "user", "content": f'Fix this Java error. Return: {{"suggested_fix":"explanation","fixed_code":"complete code with // FIX comments on changed lines","explanation":"steps"}}\n\nCode: {code}\n\nError: {error}'})
        result = await _call_ollama_json(retry_messages, temperature=0.1, num_predict=800)

    if not result or "fixed_code" not in result or not result["fixed_code"].strip():
        result = {
            "suggested_fix": f"Error: {error[:100]}",
            "fixed_code": code,
            "explanation": "Could not automatically fix this error. Review the error message carefully.",
        }

    logger.info("Error fix suggestion generated")
    return result


async def code_review(code: str, focus: str = None) -> dict:
    messages = [{"role": "system", "content": SYSTEM_PROMPT_REVIEW}]

    user_prompt = f"Review this Java code:\n```java\n{code}\n```\n\n"
    if focus:
        user_prompt += f"Focus specifically on: {focus}\n\n"
    user_prompt += 'Respond ONLY with a JSON object: {"annotations": [{"line_start": N, "line_end": N, "category": "...", "severity": "low/medium/high", "message": "...", "suggestion": "..."}], "summary": "2-3 sentence review", "overall_score": 7}'

    messages.append({"role": "user", "content": user_prompt})

    result = await _call_ollama_json(messages, num_predict=800)
    if isinstance(result, dict) and "annotations" in result:
        logger.info("Code review generated (1st attempt)")
        return result

    # Retry with code model (better at structured output)
    logger.warning("Code review failed with llama3, retrying with code model")
    retry_result = await _call_ollama_json(messages, num_predict=800, model=OLLAMA_CODE_MODEL)
    if isinstance(retry_result, dict) and "annotations" in retry_result:
        logger.info("Code review generated (2nd attempt, code model)")
        return retry_result

    # Final retry with ultra-strict prompt
    strict_system = "You are a JSON API. Return ONLY a JSON object with code review annotations. Nothing else."
    strict_messages = [{"role": "system", "content": strict_system}]
    strict_messages.append({"role": "user", "content": f'Review this Java code. Return JSON: {{"annotations":[{{"line_start":N,"line_end":N,"category":"style/performance/error","severity":"low/medium/high","message":"issue","suggestion":"fix"}}],"summary":"review","overall_score":7}}\n\n```java\n{code}\n```'})
    final_result = await _call_ollama_json(strict_messages, temperature=0.1, num_predict=600, model=OLLAMA_CODE_MODEL)
    if isinstance(final_result, dict) and "annotations" in final_result:
        logger.info("Code review generated (3rd attempt, strict)")
        return final_result

    logger.warning("All code review attempts failed")
    return {
        "annotations": [],
        "summary": "Unable to complete code review. Please try again with different code.",
        "overall_score": 0,
    }


async def generate_flashcards(code: str) -> list:
    messages = [{"role": "system", "content": SYSTEM_PROMPT_FLASHCARDS}]

    user_prompt = f"Analyze this Java code and create concept flashcards:\n```java\n{code}\n```\n\n"
    user_prompt += "Respond ONLY with a JSON array. No text before or after. Example:\n"
    user_prompt += '[{"concept":"Arrays","definition":"Ordered collection of same-type elements","example":"int[] a = {1,2,3};","difficulty":"beginner"}]'

    messages.append({"role": "user", "content": user_prompt})

    result = await _call_ollama_json(messages, num_predict=800)
    if isinstance(result, list) and len(result) > 0:
        return result

    # Retry with code model (better at structured output)
    logger.warning("Flashcard generation failed with llama3, retrying with code model")
    retry_result = await _call_ollama_json(messages, num_predict=800, model=OLLAMA_CODE_MODEL)
    if isinstance(retry_result, list) and len(retry_result) > 0:
        return retry_result

    # Final retry with ultra-strict prompt
    strict_messages = [{"role": "system", "content": "You are a JSON API. Return ONLY a JSON array. Nothing else."}]
    strict_messages.append({"role": "user", "content": f'Extract Java concepts from this code. Return: [{{"concept":"name","definition":"1 sentence","example":"short code","difficulty":"beginner/intermediate/advanced"}}]\n\n{code}'})
    final_result = await _call_ollama_json(strict_messages, temperature=0.1, num_predict=600, model=OLLAMA_CODE_MODEL)
    if isinstance(final_result, list) and len(final_result) > 0:
        return final_result

    logger.warning("All flashcard generation attempts failed")
    return []


async def generate_test_cases(code: str, class_name: str = None) -> dict:
    messages = [{"role": "system", "content": SYSTEM_PROMPT_TESTS}]

    cn = class_name or "Main"
    user_prompt = f"Write JUnit 5 test cases for this Java code:\n```java\n{code}\n```\n\n"
    user_prompt += f"The class name is '{cn}'.\n\n"
    user_prompt += "Respond ONLY with a JSON object. No text before or after. Example:\n"
    user_prompt += '{"test_code":"import org.junit.jupiter.api.*;\\n@Test void testSomething() {...}","test_explanation":"Tests normal input handling"}'

    messages.append({"role": "user", "content": user_prompt})

    result = await _call_ollama_json(messages, num_predict=1500)
    if isinstance(result, dict) and result.get("test_code"):
        return result

    # Retry with code model
    logger.warning("Test generation failed with llama3, retrying with code model")
    retry_result = await _call_ollama_json(messages, num_predict=1500, model=OLLAMA_CODE_MODEL)
    if isinstance(retry_result, dict) and retry_result.get("test_code"):
        return retry_result

    # Final retry with strict prompt
    strict_messages = [{"role": "system", "content": "You are a JSON API. Return ONLY a JSON object with test_code and test_explanation keys. Escape all newlines as \\n."}]
    strict_messages.append({"role": "user", "content": f'Write JUnit 5 tests for: {code}. Return: {{"test_code":"full Java code","test_explanation":"summary"}}'})
    final_result = await _call_ollama_json(strict_messages, temperature=0.1, num_predict=1500, model=OLLAMA_CODE_MODEL)
    if isinstance(final_result, dict) and final_result.get("test_code"):
        return final_result

    logger.warning("All test generation attempts failed")
    return {"test_code": "", "test_explanation": "Unable to generate test cases. Try simplifying the code."}
