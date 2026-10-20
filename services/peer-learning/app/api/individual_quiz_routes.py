import json
import logging
import os
import random
import re
import uuid
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI

from app.api.student_routes import get_latest_student_analysis, verify_jwt_student
from app.models.schemas import (
    AnswerFeedbackResponse,
    IndividualQuizStartRequest,
    IndividualQuizStartResponse,
    OpenQuestionItem,
    QuizSummaryResponse,
    SubmitAnswerRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/individual-quiz", tags=["Individual Quiz System"])

# In-Memory Session Storage
QUIZ_SESSIONS: Dict[str, Dict[str, Any]] = {}
# Tracks the active quiz session per student (student_id -> session_id)
CURRENT_SESSIONS: Dict[str, str] = {}

# 1. Code-Based Questions & Hints සදන Prompt Template එක
quiz_gen_prompt = PromptTemplate(
    input_variables=["topic", "difficulty"],
    template="""
    You are an expert Java Pedagogy AI Agent.
    Generate exactly 7 distinct, CODE-BASED practical questions for a Java quiz on the specified topic.
    Do NOT generate general essay/theory questions. Focus entirely on code snippets, bug detection, output prediction, or short code writing.

    Constraints:
    - Topic: {topic}
    - Difficulty Level: {difficulty}
    - Language: English Only
    - Question Types: Code Snippet Output Tracing, Bug Identification/Fixing, Completing Code Logic.
    - Output Format: Strictly JSON

    JSON Structure:
    {{
        "questions": [
            {{
                "id": 1,
                "question": "Given code snippet or coding prompt asking to write/fix code.",
                "hint": "A subtle technical clue/hint helping the student think in the right direction without giving away the full answer.",
                "expected_answer": "Key code snippet or expected output/logic in student's response.",
                "explanation": "Detailed step-by-step code execution explanation."
            }}
        ]
    }}
    """
)

# 2. Student ගේ Code / Answer එක Evaluate කරන Prompt Template එක
answer_eval_prompt = PromptTemplate(
    input_variables=["question", "expected_answer", "student_answer"],
    template="""
    You are an automated Java Code Assessor.
    Evaluate the student's code or technical answer against the expected answer/logic.

    Question: {question}
    Expected Answer: {expected_answer}
    Student's Answer: {student_answer}

    Evaluation Criteria:
    - Focus on logical correctness, correct API/syntax usage, and code outcome.
    - Be forgiving of minor formatting issues or trailing semicolons if the underlying code logic is correct.

    Output Format: Strictly JSON
    {{
        "is_correct": true,
        "feedback": "Constructive code review feedback explaining why the code logic succeeds or fails."
    }}
    """
)


@router.post("/start", response_model=IndividualQuizStartResponse)
def start_individual_quiz(
    token_student_id: str = Depends(verify_jwt_student),
    request: Optional[IndividualQuizStartRequest] = None,
):
    try:
        # When no request body is supplied, auto-fetch the student's data from
        # the JWT + latest mastery analysis and generate a fresh quiz session.
        if request is None:
            return start_auto_quiz_session(token_student_id)

        session_id = str(uuid.uuid4())
        questions = generate_random_7_questions(request.topic, request.difficulty_level)

        QUIZ_SESSIONS[session_id] = {
            "student_id": request.student_id,
            "topic": request.topic,
            "questions": questions,
            "current_index": 0,
            "score": 0,
            "answers_history": []
        }
        CURRENT_SESSIONS[request.student_id] = session_id

        # පළමු ප්‍රශ්නය සමඟ Hint එකද යවයි
        first_q = OpenQuestionItem(
            id=questions[0]["id"],
            question=questions[0]["question"],
            hint=questions[0].get("hint", "")
        )

        return IndividualQuizStartResponse(
            status="success",
            session_id=session_id,
            total_questions=7,
            question_index=0,
            first_question=first_q
        )

    except Exception as e:
        logger.error(f"Error starting code-based quiz session: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/submit-answer", response_model=AnswerFeedbackResponse)
def submit_quiz_answer(
    request: SubmitAnswerRequest,
    token_student_id: str = Depends(verify_jwt_student),
):
    # Auto-resolve the student's active quiz session and current question index.
    session_id = CURRENT_SESSIONS.get(token_student_id)
    if not session_id:
        raise HTTPException(
            status_code=404,
            detail="No active quiz session found. Start one at /api/individual-quiz/start first.",
        )
    session = QUIZ_SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Quiz session not found or expired.")

    questions = session["questions"]
    curr_idx = session["current_index"]

    if curr_idx < 0 or curr_idx >= len(questions):
        raise HTTPException(status_code=400, detail="Invalid question index.")

    current_q = questions[curr_idx]
    
    # Student Code Answer Evaluation
    eval_result = evaluate_student_answer(
        question=current_q["question"],
        expected_answer=current_q["expected_answer"],
        student_answer=request.student_answer
    )

    is_correct = eval_result.get("is_correct", False)
    ai_feedback = eval_result.get("feedback", current_q["explanation"])

    if is_correct:
        session["score"] += 1

    session["answers_history"].append({
        "question_id": current_q["id"],
        "question_text": current_q["question"],
        "student_answer": request.student_answer,
        "expected_answer": current_q["expected_answer"],
        "is_correct": is_correct,
        "feedback": ai_feedback
    })

    next_idx = curr_idx + 1
    next_question = None
    is_completed = False

    if next_idx < len(questions):
        session["current_index"] = next_idx
        next_question = OpenQuestionItem(
            id=questions[next_idx]["id"],
            question=questions[next_idx]["question"],
            hint=questions[next_idx].get("hint", "")
        )
    else:
        is_completed = True

    return AnswerFeedbackResponse(
        status="success",
        is_correct=is_correct,
        correct_answer=current_q["expected_answer"],
        explanation=ai_feedback,
        next_question=next_question,
        is_quiz_completed=is_completed
    )


@router.get("/summary/{session_id}", response_model=QuizSummaryResponse)
def get_quiz_summary(session_id: str):
    session = QUIZ_SESSIONS.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Quiz session not found.")

    total_q = len(session["questions"])
    correct_count = session["score"]
    score_percentage = round((correct_count / total_q) * 100, 2)

    return QuizSummaryResponse(
        status="success",
        session_id=session_id,
        student_id=session["student_id"],
        topic=session["topic"],
        total_questions=total_q,
        correct_answers=correct_count,
        score_percentage=score_percentage,
        detailed_history=session["answers_history"]
    )


# ============================================================================
# Helper Functions
# ============================================================================

def start_auto_quiz_session(student_id: str) -> IndividualQuizStartResponse:
    """Start a quiz using the authenticated student's analysis data, without a request body."""
    analysis = get_latest_student_analysis(student_id)
    gaps = (
        analysis.get("knowledge_gaps")
        or analysis.get("mastery_profile", {}).get("knowledge_gaps")
        or []
    )
    if not gaps:
        raise HTTPException(
            status_code=404,
            detail="No knowledge gaps found in the imported analysis to build a quiz.",
        )

    first_gap = gaps[0]
    topic = first_gap.get("topic") or "Java Programming"
    mastery_score = (
        analysis.get("mastery_profile", {}).get("overall_mastery_score")
        or analysis.get("overall_mastery_score")
    )
    difficulty = derive_difficulty_level(mastery_score)

    session_id = str(uuid.uuid4())
    questions = generate_random_7_questions(topic, difficulty)

    QUIZ_SESSIONS[session_id] = {
        "student_id": student_id,
        "topic": topic,
        "difficulty_level": difficulty,
        "questions": questions,
        "current_index": 0,
        "score": 0,
        "answers_history": []
    }
    CURRENT_SESSIONS[student_id] = session_id

    first_q = OpenQuestionItem(
        id=questions[0]["id"],
        question=questions[0]["question"],
        hint=questions[0].get("hint", "")
    )

    return IndividualQuizStartResponse(
        status="success",
        session_id=session_id,
        total_questions=7,
        question_index=0,
        first_question=first_q
    )


def derive_difficulty_level(mastery_score: Any) -> str:
    """Map the student's overall mastery score to a quiz difficulty level."""
    try:
        score = float(mastery_score)
    except (TypeError, ValueError):
        return "beginner"
    if score < 40:
        return "beginner"
    if score <= 70:
        return "intermediate"
    return "advanced"


def generate_random_7_questions(topic: str, difficulty: str) -> list:
    api_key = os.getenv("OPENAI_API_KEY", "dummy_key")

    if not api_key or api_key == "dummy_key":
        return get_fallback_7_code_questions(topic)

    try:
        random_seed = random.randint(1000, 99999)
        dynamic_prompt = (
            f"{quiz_gen_prompt.format(topic=topic, difficulty=difficulty)}\n"
            f"Randomization Seed: {random_seed}. Ensure distinct code snippets and accurate hints."
        )

        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.7, api_key=api_key)
        res = llm.invoke(dynamic_prompt).content.strip()

        json_match = re.search(r"\{.*\}", res, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(0))
            questions = data.get("questions", [])
            if len(questions) >= 7:
                return questions[:7]
    except Exception as e:
        logger.warning(f"Failed to generate code questions via LLM, using fallback. Error: {str(e)}")

    return get_fallback_7_code_questions(topic)


def evaluate_student_answer(question: str, expected_answer: str, student_answer: str) -> dict:
    api_key = os.getenv("OPENAI_API_KEY", "dummy_key")

    if not api_key or api_key == "dummy_key":
        s_ans = student_answer.strip().lower()
        e_words = [w.lower() for w in expected_answer.split() if len(w) > 3]
        match_count = sum(1 for word in e_words if word in s_ans)
        is_correct = (match_count / max(len(e_words), 1)) >= 0.3 if s_ans else False
        return {
            "is_correct": is_correct,
            "feedback": "Correct code solution!" if is_correct else "Code solution misses essential keywords or logic."
        }

    try:
        formatted_prompt = answer_eval_prompt.format(
            question=question,
            expected_answer=expected_answer,
            student_answer=student_answer
        )
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.0, api_key=api_key)
        res = llm.invoke(formatted_prompt).content.strip()

        json_match = re.search(r"\{.*\}", res, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(0))
    except Exception as e:
        logger.warning(f"LLM Answer Evaluation failed: {str(e)}")

    return {"is_correct": False, "feedback": "Unable to evaluate code solution automatically."}


def get_fallback_7_code_questions(topic: str) -> list:
    """Fallback list containing strictly Code-Based questions with hints."""
    return [
        {
            "id": 1,
            "question": f"What will be the output of the following Java code related to {topic}?\n\ntry {{\n    int val = 10 / 0;\n}} catch (ArithmeticException e) {{\n    System.out.print(\"Caught \");\n}} finally {{\n    System.out.print(\"Cleaned\");\n}}",
            "hint": "Remember that the finally block always executes after catch.",
            "expected_answer": "Caught Cleaned",
            "explanation": "The catch block handles the division by zero, printing 'Caught ', followed by the finally block printing 'Cleaned'."
        },
        {
            "id": 2,
            "question": f"Fix the compilation bug in this code involving {topic}:\n\npublic void process() {{\n    throw new Exception(\"Error occurred\");\n}}",
            "hint": "Checked exceptions must be handled with try-catch or declared in the method signature.",
            "expected_answer": "Add 'throws Exception' to the method signature or wrap in try-catch.",
            "explanation": "Exception is a checked exception and must be declared in the method header using 'throws'."
        },
        {
            "id": 3,
            "question": f"Write a single-line Java code snippet to throw an IllegalArgumentException with the message \"Invalid Input\" for {topic}.",
            "expected_answer": "throw new IllegalArgumentException(\"Invalid Input\");",
            "hint": "Use the 'throw' keyword followed by instantiation of the exception class.",
            "explanation": "Syntactically, explicit throwing requires 'throw new ExceptionClass(\"message\")'."
        },
        {
            "id": 4,
            "question": f"Complete the missing code block (marked with ???) to handle null pointers gracefully when processing {topic}:\n\nString text = null;\ntry {{\n    System.out.println(text.length());\n}} ??? {{\n    System.out.println(\"Handled Null\");\n}}",
            "expected_answer": "catch (NullPointerException e)",
            "hint": "Specify the appropriate exception type that matches null reference access.",
            "explanation": "Accessing methods on a null reference throws NullPointerException, which must be caught by catch(NullPointerException e)."
        },
        {
            "id": 5,
            "question": f"What is wrong with the order of catch blocks in this {topic} code snippet?\n\ntry {{\n    // code\n}} catch (Exception e) {{\n}} catch (ArithmeticException e) {{\n}}",
            "expected_answer": "Subclass exception (ArithmeticException) must come before parent class exception (Exception).",
            "hint": "Parent exception classes catch everything, making subsequent subclass catch blocks unreachable.",
            "explanation": "Unreachable code compilation error occurs when a broader exception type precedes a narrower one."
        },
        {
            "id": 6,
            "question": f"Write a custom exception class declaration named Invalid{topic.replace(' ', '')}Exception that extends Exception.",
            "expected_answer": f"public class Invalid{topic.replace(' ', '')}Exception extends Exception {{ }}",
            "hint": "Use the standard Java class extension syntax inheriting from Exception.",
            "explanation": "Custom checked exceptions inherit directly from java.lang.Exception."
        },
        {
            "id": 7,
            "question": f"What does this try-with-resources code guarantee when handling resource streams for {topic}?\n\ntry (Scanner sc = new Scanner(System.in)) {{\n    // operation\n}}",
            "expected_answer": "The Scanner resource 'sc' is automatically closed at the end of the statement.",
            "hint": "Think about how AutoCloseable resources behave without an explicit finally block.",
            "explanation": "Try-with-resources automatically invokes close() on resources implementing AutoCloseable."
        }
    ]