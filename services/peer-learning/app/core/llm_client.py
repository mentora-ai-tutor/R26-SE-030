import httpx
import json
import re
from typing import Optional, Dict, Any
from tenacity import retry, stop_after_attempt, wait_exponential
from loguru import logger
from app.core.config import settings


class OllamaClient:
    """Async client for Ollama LLM (gemma4:latest)."""

    def __init__(self):
        self.base_url = settings.ollama_base_url
        self.model = settings.ollama_model
        self.timeout = settings.ollama_timeout

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def generate(self, prompt: str, system: Optional[str] = None) -> str:
        """Generate text using Ollama API."""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }
        if system:
            payload["system"] = system

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                return data.get("response", "")
            except httpx.TimeoutException:
                logger.error(f"Ollama request timed out after {self.timeout}s")
                raise
            except httpx.HTTPStatusError as e:
                logger.error(f"Ollama HTTP error: {e.response.status_code} - {e.response.text}")
                raise
            except Exception as e:
                logger.error(f"Ollama unexpected error: {e}")
                raise

    def _extract_json(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract JSON from LLM response (handles markdown fences)."""
        # Try direct parse first
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass

        # Try extracting from ```json blocks
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if json_match:
            try:
                return json.loads(json_match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # Try finding first { ... } block
        brace_match = re.search(r"(\{[\s\S]*\})", text)
        if brace_match:
            try:
                return json.loads(brace_match.group(1))
            except json.JSONDecodeError:
                pass

        logger.warning(f"Could not extract JSON from LLM response: {text[:200]}")
        return None

    async def generate_question(
        self,
        topic: str,
        bloom_level: int,
        current_mastery: float,
        misconception: str,
        topic_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Generate a Bloom's taxonomy question for a topic."""
        bloom_descriptions = {
            1: "Remember - Recall facts, definitions, syntax",
            2: "Understand - Explain concepts, summarize, paraphrase",
            3: "Apply - Use concepts to solve problems, write code",
            4: "Analyze - Break down, find patterns, debug code",
            5: "Evaluate - Judge, critique, compare, optimize",
            6: "Create - Design, build, teach others",
        }

        prompt = f"""You are a question generator for programming education using Bloom's Taxonomy.
Topic: {topic}
Bloom's Taxonomy Level: {bloom_level} - {bloom_descriptions.get(bloom_level, 'Apply')}
Student's current mastery: {current_mastery}%
Specific misconception: {misconception}

Generate a JSON response with exactly this structure (no extra text, pure JSON):
{{
  "question_text": "the question",
  "expected_answer": "the correct answer",
  "hints": ["subtle hint", "specific guidance", "almost solution"],
  "time_limit_seconds": 120
}}"""

        raw = await self.generate(prompt)
        parsed = self._extract_json(raw)

        if not parsed:
            # Fallback question
            logger.warning(f"Using fallback question for topic={topic}, level={bloom_level}")
            return self._fallback_question(topic, bloom_level)

        # Validate structure
        required = ["question_text", "expected_answer", "hints", "time_limit_seconds"]
        if not all(k in parsed for k in required):
            return self._fallback_question(topic, bloom_level)

        if not isinstance(parsed.get("hints"), list) or len(parsed["hints"]) < 3:
            parsed["hints"] = [
                "Think about the basic concept.",
                "Consider how this concept applies.",
                "Review the syntax and structure.",
            ]

        return parsed

    async def generate_group_problem(
        self, topic: str, activity_type: str, topic_id: str
    ) -> Optional[Dict[str, Any]]:
        """Generate a collaborative group programming problem."""
        prompt = f"""Generate a collaborative programming problem for 3 students working together.
Topic: {topic}
Activity type: {activity_type}

Provide JSON with exactly this structure (pure JSON, no extra text):
{{
  "problem_statement": "clear description of the problem",
  "explainer_guide": "how to explain this problem to others",
  "solver_starter": "// starter code template\\nfunction solution() {{\\n  // implement here\\n}}",
  "reviewer_checklist": "1. Check edge cases\\n2. Verify time complexity\\n3. Test with examples",
  "expected_solution": "complete solution code"
}}"""

        raw = await self.generate(prompt)
        parsed = self._extract_json(raw)

        if not parsed:
            return self._fallback_group_problem(topic, activity_type)

        required = ["problem_statement", "explainer_guide", "solver_starter", "reviewer_checklist", "expected_solution"]
        if not all(k in parsed for k in required):
            return self._fallback_group_problem(topic, activity_type)

        return parsed

    async def evaluate_answer(
        self, question_text: str, expected_answer: str, student_answer: str, topic: str
    ) -> Dict[str, Any]:
        """Use LLM to evaluate if student answer is correct."""
        prompt = f"""You are evaluating a programming student's answer.
Topic: {topic}
Question: {question_text}
Expected Answer: {expected_answer}
Student Answer: {student_answer}

Evaluate if the student's answer is correct or partially correct.
Respond with pure JSON only:
{{
  "is_correct": true/false,
  "is_partial": true/false,
  "feedback": "brief explanation",
  "score_percentage": 0-100
}}"""

        raw = await self.generate(prompt)
        parsed = self._extract_json(raw)

        if not parsed:
            # Simple fallback: exact match
            is_correct = student_answer.strip().lower() == expected_answer.strip().lower()
            return {
                "is_correct": is_correct,
                "is_partial": False,
                "feedback": "Answer evaluated.",
                "score_percentage": 100 if is_correct else 0,
            }

        return parsed

    def _fallback_question(self, topic: str, bloom_level: int) -> Dict[str, Any]:
        """Fallback question when LLM fails."""
        questions = {
            1: f"What is the definition of {topic}? Provide a basic example.",
            2: f"Explain in your own words how {topic} works and why it is useful.",
            3: f"Write a simple program that demonstrates the use of {topic}.",
            4: f"Analyze the following code that uses {topic} and identify any issues.",
            5: f"Compare two different approaches to implementing {topic} and evaluate which is better.",
            6: f"Design a complete solution using {topic} and explain your design decisions.",
        }
        return {
            "question_text": questions.get(bloom_level, f"Explain {topic} with an example."),
            "expected_answer": f"A correct explanation or implementation of {topic}.",
            "hints": [
                f"Think about the core concept of {topic}.",
                f"Consider how {topic} is typically used in practice.",
                f"Look at basic {topic} examples to guide your answer.",
            ],
            "time_limit_seconds": 120,
        }

    def _fallback_group_problem(self, topic: str, activity_type: str) -> Dict[str, Any]:
        """Fallback group problem when LLM fails."""
        return {
            "problem_statement": f"Work together to implement a solution demonstrating {topic}. Each member should contribute to the design, implementation, and review.",
            "explainer_guide": f"Start by explaining the core concepts of {topic} and how they apply to this problem.",
            "solver_starter": f"// Starter code for {topic}\nfunction solution(input) {{\n  // implement your solution here\n  return result;\n}}",
            "reviewer_checklist": "1. Does the code handle edge cases?\n2. Is the logic correct?\n3. Is the code readable?\n4. Are there any optimizations?",
            "expected_solution": f"// A correct implementation demonstrating {topic}",
        }


# Singleton
llm_client = OllamaClient()
