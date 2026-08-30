import os
import json
from langchain_openai import ChatOpenAI
from langchain_core.prompts import PromptTemplate

quiz_prompt = PromptTemplate(
    input_variables=["student_id", "topic", "weak_subskill", "misconception", "difficulty"],
    template="""
    You are an expert Java Pedagogy AI.
    Generate a diagnostic evaluation question for student {student_id}.
    
    Student Target Context:
    - Topic: {topic}
    - Weak Subskill: {weak_subskill}
    - Common Misconception: {misconception}
    - Difficulty Level: {difficulty}

    Instructions:
    Generate a Multiple Choice Question (MCQ) or short code trace question designed specifically to test if the student still has this misconception or weak subskill.

    Return EXACTLY in JSON format with keys:
    {{
        "question": "question string",
        "options": ["A", "B", "C", "D"],
        "correct_answer": "correct option text",
        "explanation": "why this is correct and addresses the misconception"
    }}
    """
)

def generate_targeted_quiz(student_id: str, gap: dict):
    topic = gap.get("topic", "Java Concept")
    difficulty = gap.get("suggested_intervention", {}).get("difficulty_level", "beginner")
    
    # Extract weak subskill & misconception
    weak_subskill = gap["weak_subskills"][0]["subskill"] if gap.get("weak_subskills") else "general concept"
    misconception = gap["misconceptions"][0] if gap.get("misconceptions") else "none"

    # API Key එක ලබාගෙන LLM එක Function එක ඇතුළත Initialize කිරීම
    api_key = os.getenv("OPENAI_API_KEY", "dummy_key")

    formatted_prompt = quiz_prompt.format(
        student_id=student_id,
        topic=topic,
        weak_subskill=weak_subskill,
        misconception=misconception,
        difficulty=difficulty
    )

    try:
        # Check if key is actual key before calling OpenAI
        if not api_key or api_key == "dummy_key":
            raise ValueError("No valid API Key provided")

        llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0.7,
            api_key=api_key
        )
        response = llm.invoke(formatted_prompt)
        parsed_quiz = json.loads(response.content.strip("```json\n").strip("```"))
        return parsed_quiz
    except Exception:
        # Fallback if API key missing or LLM call fails
        return {
            "question": f"Identify the correct base case handling for {topic}.",
            "options": ["if (n <= 1) return 1;", "return n * f(n-1);", "n = n - 1;", "None"],
            "correct_answer": "if (n <= 1) return 1;",
            "explanation": "A recursion base case stops infinite execution."
        }