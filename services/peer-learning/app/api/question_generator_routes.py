import os
import json
from typing import Dict, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from openai import OpenAI

from app.api.student_routes import get_latest_student_analysis, verify_jwt_student

# Initialize the API Router with prefix and tags for Swagger documentation
router = APIRouter(prefix="/api/question-generator", tags=["Question Generator"])

# Initialize OpenAI Client (Requires OPENAI_API_KEY set in environment variables or .env file)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Stores the last generated challenge per student (student_id -> challenge dict)
LAST_GENERATED_QUESTION: Dict[str, dict] = {}

# Pydantic model for Question Request
class QuestionRequest(BaseModel):
    topic: str         # Target Java topic (e.g., "Variables", "Loops", "Arrays", "OOP")
    difficulty: str    # Target difficulty level ("Beginner", "Intermediate", "Advanced")

# Pydantic model for Code Evaluation Request
class CodeEvaluationRequest(BaseModel):
    student_code: str  # The Java code written by the student

# ---------------------------------------------------------------------------
# 1. GENERATE QUESTION ENDPOINT
# ---------------------------------------------------------------------------
@router.post("/generate")
async def generate_java_question(
    token_student_id: str = Depends(verify_jwt_student),
    req: Optional[QuestionRequest] = None,
):
    """
    POST Endpoint to generate a randomized Java programming challenge with progressive hints.
    When no JSON body is supplied, the topic and difficulty are auto-fetched from the
    authenticated student's latest mastery analysis.
    """
    if req is None:
        topic, difficulty = fetch_analysis_topic_and_difficulty(token_student_id)
    else:
        topic, difficulty = req.topic, req.difficulty

    prompt = f"""
    You are a creative Java Coding Challenge Creator for students.
    Generate a completely RANDOM, unique, and practical Java coding challenge based on:
    - Topic: {topic}
    - Difficulty: {difficulty}

    Ensure the story scenario is creative and different every time (e.g., Space station, Supermarket, Gaming app, Library, Robot control).

    Return ONLY a raw JSON object (NO Markdown formatting, NO ```json wrappers):
    {{
        "title": "Short Unique Challenge Title",
        "topic": "{topic}",
        "difficulty": "{difficulty}",
        "story_context": "A short, fun scenario for the problem.",
        "task_description": "Clear step-by-step instructions for the student to implement.",
        "input_output_example": "Example Input and Expected Output",
        "starter_code": "public class Main {{\n    public static void main(String[] args) {{\n        // Write your solution here\n    }}\n}}",
        "hints": [
            "Hint 1 (High-Level Concept): Broad idea of how to think about the solution.",
            "Hint 2 (Logic Structure): Specific Java logic required (loops, arrays, conditions, etc.).",
            "Hint 3 (Code/Syntax Help): Partial code structure or syntax tip."
        ]
    }}
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You output strictly valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.9
        )

        content = response.choices[0].message.content.strip()
        clean_json = content.replace("```json", "").replace("```", "").strip()
        generated_question = json.loads(clean_json)

        # Store for the /evaluate endpoint to auto-fetch the task description.
        LAST_GENERATED_QUESTION[token_student_id] = generated_question
        return generated_question

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OpenAI Question Generation Failed: {str(e)}")


# ---------------------------------------------------------------------------
# 2. EVALUATE CODE ENDPOINT (නව එන්ඩ්පොයින්ට් එක)
# ---------------------------------------------------------------------------
@router.post("/evaluate")
async def evaluate_student_code(
    req: CodeEvaluationRequest,
    token_student_id: str = Depends(verify_jwt_student),
):
    """
    POST Endpoint to evaluate student's Java code logic using OpenAI.
    The task description is auto-fetched from the last generated question,
    so the JSON body only needs the student's code.
    """
    stored = LAST_GENERATED_QUESTION.get(token_student_id)
    task_description = stored.get("task_description") if stored else None
    if not task_description:
        raise HTTPException(
            status_code=404,
            detail="No generated question found. Call /api/question-generator/generate first.",
        )

    prompt = f"""
    You are an expert Java Code Evaluator for students.
    
    Task Description:
    {task_description}

    Student's Java Code:
    ```java
    {req.student_code}
    ```

    Evaluate whether the code correctly solves the task description logic.
    Check for syntax errors, logical correctness, and handling of basic edge cases.
    
    Return ONLY a raw JSON object (NO Markdown, NO ```json wrappers):
    {{
        "is_correct": true,
        "status": "Passed",
        "score": 90,
        "feedback": "Clear explanation of what the student did well or what logic is missing.",
        "suggestions": "Short tip to make the code cleaner or optimized."
    }}
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You output strictly valid JSON for code evaluation."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2  # Low temperature ensures consistent and strict evaluation
        )

        content = response.choices[0].message.content.strip()
        clean_json = content.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_json)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Code Evaluation Failed: {str(e)}")


# ---------------------------------------------------------------------------
# 3. AUTO-FETCH HELPER
# ---------------------------------------------------------------------------
def fetch_analysis_topic_and_difficulty(student_id: str):
    """Derive a topic and difficulty from the student's latest mastery analysis."""
    analysis = get_latest_student_analysis(student_id)
    gaps = (
        analysis.get("knowledge_gaps")
        or analysis.get("mastery_profile", {}).get("knowledge_gaps")
        or []
    )
    if not gaps:
        raise HTTPException(
            status_code=404,
            detail="No knowledge gaps found in the imported analysis to build a question.",
        )

    topic = gaps[0].get("topic") or "Java Programming"
    mastery_score = (
        analysis.get("mastery_profile", {}).get("overall_mastery_score")
        or analysis.get("overall_mastery_score")
    )
    return topic, derive_difficulty_level(mastery_score)


def derive_difficulty_level(mastery_score) -> str:
    """Map the student's overall mastery score to a difficulty level."""
    try:
        score = float(mastery_score)
    except (TypeError, ValueError):
        return "beginner"
    if score < 40:
        return "beginner"
    if score <= 70:
        return "intermediate"
    return "advanced"