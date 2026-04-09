# backend/services/question_service.py
import httpx
import json
import os

OLLAMA_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

async def generate_question(topic: str, misconceptions: list, difficulty: str = "beginner") -> dict:
    """
    Call Ollama (local LLM) to generate a question about the weak topic.
    Returns a structured dict with question, answer, hints, and a follow-up.
    """
    prompt = f"""You are a Java programming tutor. Generate a {difficulty} question about: {topic}

The student has these misconceptions: {', '.join(misconceptions)}

Return ONLY a JSON object (no extra text) with this exact structure:
{{
  "question": "the question text, can include a code snippet",
  "expected_answer": "the correct answer explanation",
  "hints": [
    "vague hint — just direct attention",
    "more specific hint — suggest an approach",
    "very specific hint — nearly the answer"
  ],
  "similar_question": "a different question testing the same concept",
  "concept_tested": "the specific sub-concept being tested"
}}"""

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": "llama3",
                "prompt": prompt,
                "stream": False
            }
        )
    
    raw = response.json()["response"]
    
    # Strip any markdown fences if LLM wraps in ```json
    raw = raw.strip().removeprefix("```json").removesuffix("```").strip()
    
    return json.loads(raw)

async def evaluate_answer(question: str, student_answer: str, expected_answer: str) -> dict:
    """Ask the LLM to grade the student's answer."""
    prompt = f"""Grade this programming answer.

Question: {question}
Expected answer: {expected_answer}
Student answer: {student_answer}

Return ONLY a JSON object:
{{
  "correct": true or false,
  "score": 0-100,
  "feedback": "1-2 sentences of constructive feedback",
  "concept_understood": true or false
}}"""

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": "llama3", "prompt": prompt, "stream": False}
        )
    
    raw = response.json()["response"].strip().removeprefix("```json").removesuffix("```").strip()
    return json.loads(raw)