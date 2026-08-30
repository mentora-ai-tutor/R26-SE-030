import json
import logging
import os
import re
from typing import Any, Dict
from fastapi import APIRouter, HTTPException, status
from langchain_core.prompts import PromptTemplate
from langchain_openai import ChatOpenAI

from app.models.schemas import RecommendationRequest, RecommendationResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/rag-content", tags=["RAG Content Recommendation"])


# ==========================================
# Pure English A-Z Prompt Template
# ==========================================
rag_prompt_template = PromptTemplate(
    input_variables=["topic", "weak_subskill", "misconception", "difficulty_level", "rag_context"],
    template="""
    You are an expert Java Pedagogy AI Agent.
    Generate an IN-DEPTH, STEP-BY-STEP study guide in strictly CLEAR ENGLISH for a student learning Java.
    
    IMPORTANT FORMATTING REQUIREMENTS:
    - Language: STRICTLY ENGLISH ONLY. Do NOT use Sinhala or mixed language words anywhere.
    - Readability: Use clear paragraph spacing (`\n\n`) to break dense text. Avoid walls of text.

    Student Context:
    - Topic: {topic}
    - Weak Subskill: {weak_subskill}
    - Student Misconception: {misconception}
    - Difficulty Level: {difficulty_level}

    Reference Context:
    {rag_context}

    INSTRUCTIONS FOR GENERATING CONTENT:
    1. 'tutorial_title': Clear title such as "Java Masterclass: {topic} ({weak_subskill})"
    
    2. 'concept_summary': Structure this into clear spaced paragraphs using `\n\n`:
       - Core Concept: What is this concept in plain English?
       - Real-World Analogy: A practical real-world analogy.
       - Execution Flow: Step-by-step breakdown of how Java processes this logic.

    3. 'key_highlights': 4 distinct, spaced bullet points covering core keywords, syntax rules, and mechanics.
    
    4. 'common_pitfalls': 3 detailed common student mistakes with specific explanations of why they happen.
    
    5. 'practice_code_snippet': A full, executable Java program with clear line-by-line comments explaining the execution flow.
    
    6. 'suggested_exercise': A structured, step-by-step coding challenge for hands-on practice.

    Return ONLY a valid JSON object matching this schema strictly:
    {{
        "tutorial_title": "Java Masterclass: {topic} ({weak_subskill})",
        "concept_summary": "Paragraph 1...\n\nParagraph 2...\n\nParagraph 3...",
        "key_highlights": [
            "Point 1...",
            "Point 2...",
            "Point 3...",
            "Point 4..."
        ],
        "common_pitfalls": [
            "Mistake 1...",
            "Mistake 2...",
            "Mistake 3..."
        ],
        "practice_code_snippet": "public class JavaDemo {{\n    public static void main(String[] args) {{\n        // Executable Java Code\n    }}\n}}",
        "suggested_exercise": "Step 1: ...\n\nStep 2: ...\n\nStep 3: ..."
    }}
    """
)


def extract_json_from_text(text: str) -> Dict[str, Any]:
    json_match = re.search(r"\{.*\}", text, re.DOTALL)
    if json_match:
        json_str = json_match.group(0)
        return json.loads(json_str)
    raise json.JSONDecodeError("No JSON object found", text, 0)


@router.post("/recommend", response_model=RecommendationResponse)
def recommend_learning_materials(request: RecommendationRequest):
    try:
        subskill = request.weak_subskill or request.target_subskill or request.topic
        api_key = os.getenv("OPENAI_API_KEY", "dummy_key")

        # Fallback Mode for Testing (Pure English + Spaced Layout)
        if not api_key or api_key == "dummy_key" or "sk-dummy" in api_key:
            return generate_english_fallback_response(request, subskill)

        rag_context = f"Java concepts for topic '{request.topic}' and subskill '{subskill}'."

        formatted_prompt = rag_prompt_template.format(
            topic=request.topic,
            weak_subskill=subskill,
            misconception=request.misconception or "None",
            difficulty_level=request.difficulty_level or "beginner",
            rag_context=rag_context
        )

        llm = ChatOpenAI(
            model="gpt-4o-mini", 
            temperature=0.3, 
            api_key=api_key,
            model_kwargs={"response_format": {"type": "json_object"}}
        )
        llm_response_text = llm.invoke(formatted_prompt).content.strip()

        try:
            parsed_data: Dict[str, Any] = json.loads(llm_response_text)
        except json.JSONDecodeError:
            parsed_data = extract_json_from_text(llm_response_text)

        return RecommendationResponse(
            status="success",
            student_id=request.student_id,
            topic=request.topic,
            weak_subskill=subskill,
            tutorial_title=parsed_data.get("tutorial_title", f"Java Masterclass: {request.topic}"),
            concept_summary=parsed_data.get("concept_summary", "Study notes generated successfully."),
            key_highlights=parsed_data.get("key_highlights", []),
            common_pitfalls=parsed_data.get("common_pitfalls", []),
            practice_code_snippet=parsed_data.get("practice_code_snippet", "// Code snippet unavailable"),
            suggested_exercise=parsed_data.get("suggested_exercise", None)
        )

    except Exception as e:
        logger.error(f"Error in RAG service: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while generating study notes: {str(e)}"
        )


def generate_english_fallback_response(request: RecommendationRequest, subskill: str) -> RecommendationResponse:
    """
    Pure English fallback with structured spacing and clean formatting.
    """
    summary = (
        "Core Concept Overview:\n"
        "Java Exception Handling is a mechanism designed to catch and manage runtime errors so that the execution flow of the application continues without abrupt crashing.\n\n"
        "Real-World Analogy:\n"
        "Think of exception handling like carrying a spare tire in your car. If a tire goes flat (an exception occurs), you use the spare tire (catch block) to fix the issue and keep driving, instead of abandoning the trip on the highway.\n\n"
        "Execution Mechanism:\n"
        "1. Try Block: Wraps potentially risky code that might throw an error.\n"
        "2. Throwing Exception: Java instantiates an exception object when an error occurs.\n"
        "3. Catch Block: Intercepts the exception object and handles it gracefully.\n"
        "4. Finally Block: Executes mandatory cleanup tasks regardless of whether an error occurred."
    )

    highlights = [
        "Try Block: Encloses the risky code statements that could throw runtime exceptions.",
        "Catch Block: Specifies the exception type to handle and executes recovery logic.",
        "Finally Block: Guarantees execution of critical cleanup operations such as closing scanners or file streams.",
        "Checked vs Unchecked: Unchecked exceptions (like ArithmeticException) occur at runtime, whereas Checked exceptions are verified during compilation."
    ]

    pitfalls = [
        "Swallowing Exceptions: Leaving catch blocks empty masks critical runtime bugs and complicates debugging.",
        "Incorrect Catch Order: Catching a generic 'Exception' class before specific subclasses blocks the subclass handlers from triggering.",
        "Resource Leaks: Failing to close external resources inside a 'finally' block or using try-with-resources."
    ]

    code = (
        "import java.util.InputMismatchException;\n"
        "import java.util.Scanner;\n\n"
        "public class ExceptionHandlingDemo {\n"
        "    public static void main(String[] args) {\n"
        "        Scanner scanner = new Scanner(System.in);\n"
        "        System.out.println(\"=== Java Exception Handling Demonstration ===\\n\");\n\n"
        "        try {\n"
        "            // Step 1: Read inputs from user\n"
        "            System.out.print(\"Enter Dividend (Integer): \");\n"
        "            int dividend = scanner.nextInt();\n\n"
        "            System.out.print(\"Enter Divisor (Integer): \");\n"
        "            int divisor = scanner.nextInt();\n\n"
        "            // Step 2: Perform division (Risky line)\n"
        "            int result = dividend / divisor;\n"
        "            System.out.println(\"\\nSuccess: Result = \" + result);\n\n"
        "        } catch (ArithmeticException e) {\n"
        "            // Handles division by zero\n"
        "            System.out.println(\"\\nError: Cannot divide an integer by zero.\");\n\n"
        "        } catch (InputMismatchException e) {\n"
        "            // Handles non-numeric inputs\n"
        "            System.out.println(\"\\nError: Invalid input type. Please enter integers only.\");\n\n"
        "        } catch (Exception e) {\n"
        "            // Fallback for unexpected exceptions\n"
        "            System.out.println(\"\\nUnexpected Error: \" + e.getMessage());\n\n"
        "        } finally {\n"
        "            // Step 3: Cleanup scanner resource\n"
        "            scanner.close();\n"
        "            System.out.println(\"Resource Cleanup: Scanner stream closed.\");\n"
        "        }\n\n"
        "        System.out.println(\"Program finished execution smoothly.\");\n"
        "    }\n"
        "}"
    )

    exercise = (
        "Step 1: Declare an integer array containing 5 elements (e.g., scores = {85, 90, 78, 92, 88}).\n\n"
        "Step 2: Prompt the user to enter an array index to retrieve.\n\n"
        "Step 3: Wrap the array access inside a try block and display the requested score.\n\n"
        "Step 4: Add a catch block for ArrayIndexOutOfBoundsException to handle invalid index entries.\n\n"
        "Step 5: Add a catch block for InputMismatchException to handle non-integer user input.\n\n"
        "Step 6: Implement a finally block that outputs a completion message."
    )

    return RecommendationResponse(
        status="success",
        student_id=request.student_id,
        topic=request.topic,
        weak_subskill=subskill,
        tutorial_title=f"Java Masterclass: {request.topic} ({subskill})",
        concept_summary=summary,
        key_highlights=highlights,
        common_pitfalls=pitfalls,
        practice_code_snippet=code,
        suggested_exercise=exercise
    )