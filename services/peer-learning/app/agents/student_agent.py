import os
from typing import List, Optional
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

# Load API key from .env file
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# Pydantic Schema for Structured OpenAI Response
class QuizItemSchema(BaseModel):
    question: str
    options: List[str]
    correct_answer: str
    explanation: str


class DiagnosticCodingTaskSchema(BaseModel):
    task_type: str
    task_description: str
    starter_code: str
    requirements: List[str]
    hints: List[str]
    evaluation_criteria: str


class CodingGradeSchema(BaseModel):
    grade: str
    feedback: str
    sample_approach: str


class PeerCodingTaskSchema(BaseModel):
    task_type: str
    task_description: str
    starter_code: str
    requirements: List[str]
    hints: List[str]
    evaluation_criteria: Optional[str] = ""


class PeerCodingTaskListSchema(BaseModel):
    tasks: List[PeerCodingTaskSchema]


def generate_diagnostic_quiz(
    topic_id: str, topic: str, subskill: str
) -> dict:
    """Uses OpenAI GPT model to dynamically generate a targeted Java Quiz item

    based on the student's specific weak subskill.
    """
    prompt = f"""
    You are an expert Java Pedagogy AI Agent.
    Generate a multiple-choice diagnostic quiz item for a student who has a knowledge gap in:
    
    - Java Topic: {topic}
    - Specific Weak Subskill: {subskill}

    Strict Requirements:
    1. The question MUST directly test the concept of '{subskill}' in {topic}.
    2. Provide exactly 4 distinct options.
    3. State the correct answer (it must exactly match one of the 4 options).
    4. Provide a clear 1-sentence explanation of why that answer is correct.
    """

    try:
        response = client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a specialized Java Diagnostic Assessment Generator.",
                },
                {"role": "user", "content": prompt},
            ],
            response_format=QuizItemSchema,
        )

        quiz_data = response.choices[0].message.parsed

        return {
            "topic_id": topic_id,
            "topic": topic,
            "target_subskill": subskill,
            "quiz_item": quiz_data.model_dump(),
        }

    except Exception as e:
        print(f"⚠️ OpenAI Generation Error: {str(e)}")
        # Fallback Quiz Structure if API key missing or network fails
        return {
            "topic_id": topic_id,
            "topic": topic,
            "target_subskill": subskill,
            "quiz_item": {
                "question": f"Which core rule applies to {subskill} in {topic}?",
                "options": [
                    f"Proper implementation of {subskill}",
                    f"Incorrect syntax for {subskill}",
                    f"Ignoring memory allocation in {subskill}",
                    "None of the above",
                ],
                "correct_answer": f"Proper implementation of {subskill}",
                "explanation": f"Understanding {subskill} is crucial for mastering {topic}.",
            },
        }


def generate_diagnostic_coding_task(
    topic_id: str, topic: str, subskill: str
) -> dict:
    """Generate a single practical Java coding task for diagnostic assessment.

    No MCQ — the student must write, fix, or debug actual Java code.
    """
    prompt = f"""
    You are an expert Java Pedagogy AI Agent.
    Generate a single practical Java coding diagnostic task for a student who has a knowledge gap in:

    - Java Topic: {topic}
    - Specific Weak Subskill: {subskill}

    Strict Requirements:
    1. The task MUST directly test the concept of '{subskill}' in {topic}.
    2. Choose one task type from: write_code, fix_incorrect_code, debug_error, complete_missing_code.
    3. Provide a clear task_description explaining what the student must do.
    4. Provide starter_code with TODO comments or buggy code depending on task type.
    5. Provide 2-4 requirements the solution must meet.
    6. Provide 1-2 hints that guide without giving the answer.
    7. Provide evaluation_criteria describing what a correct solution looks like.
    8. Do NOT include multiple-choice options or the correct answer in the task itself.
    """

    try:
        response = client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a specialized Java Diagnostic Coding Task Generator.",
                },
                {"role": "user", "content": prompt},
            ],
            response_format=DiagnosticCodingTaskSchema,
        )

        task_data = response.choices[0].message.parsed

        return {
            "topic_id": topic_id,
            "topic": topic,
            "target_subskill": subskill,
            "coding_task": task_data.model_dump(),
        }

    except Exception as e:
        print(f"⚠️ OpenAI Diagnostic Coding Task Error: {str(e)}")
        return {
            "topic_id": topic_id,
            "topic": topic,
            "target_subskill": subskill,
            "coding_task": {
                "task_type": "write_code",
                "task_description": (
                    f"Write a complete Java program that demonstrates correct use of "
                    f"'{subskill}' in the context of {topic}."
                ),
                "starter_code": (
                    f"public class {subskill.replace('-', '').replace(' ', '')}Diagnostic {{\n"
                    f"    public static void main(String[] args) {{\n"
                    f"        // TODO: Implement {subskill} for {topic}\n"
                    f"    }}\n"
                    f"}}"
                ),
                "requirements": [
                    f"Demonstrate proper use of {subskill}",
                    "Handle edge cases appropriately",
                    "Include meaningful output or comments",
                ],
                "hints": [
                    f"Think about how {subskill} works in {topic}",
                    "Consider what happens with invalid or empty input",
                ],
                "evaluation_criteria": (
                    f"The code must correctly demonstrate '{subskill}' in {topic}, "
                    f"compile without errors, and handle basic edge cases."
                ),
            },
        }


def grade_coding_submission(
    topic: str,
    subskill: str,
    task_description: str,
    evaluation_criteria: str,
    submitted_code: str,
) -> dict:
    """Grade a student's submitted code against the task requirements.

    Returns pass/fail with detailed feedback.
    """
    prompt = f"""
    You are a Java Pedagogy AI Agent grading a student's coding submission.

    Task Context:
    - Topic: {topic}
    - Subskill: {subskill}
    - Task: {task_description}
    - Evaluation Criteria: {evaluation_criteria}

    Student's Submitted Code:
    ```java
    {submitted_code}
    ```

    Grade the submission based on:
    1. Does the code compile correctly?
    2. Does it address the task requirements?
    3. Does it demonstrate understanding of {subskill}?

    Respond with:
    - grade: "pass" if the code meets the criteria, "fail" if it does not
    - feedback: specific explanation of what was done well or what needs improvement
    - sample_approach: a brief description of how the problem could be solved (not full code)
    """

    try:
        response = client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": "You are a specialized Java Code Grading Agent.",
                },
                {"role": "user", "content": prompt},
            ],
            response_format=CodingGradeSchema,
        )

        grade_data = response.choices[0].message.parsed
        return grade_data.model_dump()

    except Exception as e:
        print(f"⚠️ OpenAI Grading Error: {str(e)}")
        return {
            "grade": "fail",
            "feedback": f"Unable to grade submission automatically: {str(e)}. Manual review required.",
            "sample_approach": f"A correct solution would demonstrate proper use of {subskill} in {topic}.",
        }


def generate_all_diagnostic_coding_tasks(
    topic_id: str, topic: str, subskill: str, difficulty_level: Optional[str] = None
) -> List[dict]:
    """Generate exactly 7 practical Java coding tasks for diagnostic assessment.

    One task per type, all targeting the same weak subskill.
    Task types in order: write_code, complete_missing_code, fix_incorrect_code,
    debug_error, predict_and_correct_behavior, implement_method, improve_solution.
    """
    if not difficulty_level:
        difficulty_level = "moderate"

    prompt = f"""
    You are an expert Java Pedagogy AI Agent for diagnostic assessment.

    Generate exactly 7 practical Java coding tasks for a student who has a knowledge gap.
    Each task must be a DIFFERENT type. All tasks must target the SAME subskill.

    Student Profile:
    - Knowledge Gap Topic: {topic}
    - Weak Subskill: {subskill}
    - Difficulty Level: {difficulty_level}

    Generate exactly these 7 tasks IN ORDER:

    Task 1 — "write_code":
    Write a complete Java program from scratch that demonstrates the subskill.
    The starter_code should be a minimal class skeleton with a TODO comment.

    Task 2 — "complete_missing_code":
    Provide a partial Java program with TODO markers where code is missing.
    The student must fill in the missing logic.

    Task 3 — "fix_incorrect_code":
    Provide Java code that has a logic error or incorrect implementation.
    The student must identify and fix the bug.

    Task 4 — "debug_error":
    Provide Java code that will throw an exception or produce an error.
    The student must debug and fix it.

    Task 5 — "predict_and_correct_behavior":
    Provide Java code and ask the student to predict the output,
    then modify the code so it behaves correctly.

    Task 6 — "implement_method":
    Provide a class with method signatures and TODO comments.
    The student must implement the methods.

    Task 7 — "improve_solution":
    Provide working but suboptimal Java code.
    The student must refactor and improve it.

    STRICT RULES:
    1. ALL 7 tasks must target '{subskill}' in {topic}. Do NOT vary the topic.
    2. Do NOT generate any multiple-choice questions. Every task requires writing/editing Java code.
    3. Do NOT include the complete solution or answer in any task.
    4. Provide starter_code for every task. Use "// TODO: your code here" markers.
    5. Provide 2-4 requirements per task.
    6. Provide 1-2 hints per task that guide without giving the answer.
    7. Provide evaluation_criteria for every task describing what a correct solution looks like.
    8. Make each task progressively more challenging.
    """

    try:
        response = client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a specialized Java Diagnostic Assessment Generator. "
                        "Generate exactly 7 practical coding challenges, never MCQs. "
                        "Each task must be a different type, all targeting the same subskill."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            response_format=PeerCodingTaskListSchema,
        )

        task_list_data = response.choices[0].message.parsed

        coding_tasks = []
        for idx, task in enumerate(task_list_data.tasks):
            coding_tasks.append({
                "task_number": idx + 1,
                "task_type": task.task_type,
                "task_description": task.task_description,
                "starter_code": task.starter_code,
                "requirements": task.requirements,
                "hints": task.hints,
                "evaluation_criteria": f"The code must correctly demonstrate '{subskill}' in {topic} and meet the task requirements.",
            })

        return coding_tasks

    except Exception as e:
        print(f"⚠️ OpenAI Diagnostic Tasks Generation Error: {str(e)}")
        return _fallback_diagnostic_tasks(topic, subskill, difficulty_level)


def _fallback_diagnostic_tasks(topic: str, subskill: str, difficulty_level: str) -> List[dict]:
    """Fallback 7 diagnostic tasks when OpenAI is unavailable."""
    task_types = [
        "write_code",
        "complete_missing_code",
        "fix_incorrect_code",
        "debug_error",
        "predict_and_correct_behavior",
        "implement_method",
        "improve_solution",
    ]
    tasks = []
    for idx, task_type in enumerate(task_types):
        tasks.append({
            "task_number": idx + 1,
            "task_type": task_type,
            "task_description": (
                f"Complete this {task_type} task demonstrating '{subskill}' in {topic}."
            ),
            "starter_code": (
                f"public class DiagnosticTask{idx + 1} {{\n"
                f"    public static void main(String[] args) {{\n"
                f"        // TODO: Implement {subskill} for {topic}\n"
                f"    }}\n"
                f"}}"
            ),
            "requirements": [
                f"Demonstrate proper use of {subskill}",
                "Handle edge cases appropriately",
                "Include meaningful output or comments",
            ],
            "hints": [
                f"Think about how {subskill} works in {topic}",
                "Consider what happens with invalid or empty input",
            ],
            "evaluation_criteria": (
                f"The code must correctly demonstrate '{subskill}' in {topic} "
                f"and meet the task requirements."
            ),
        })
    return tasks


def generate_peer_coding_tasks(
    topic: str,
    subskill: str,
    mastery_score: int = 0,
    misconception: Optional[str] = None,
    difficulty_level: Optional[str] = None,
) -> List[dict]:
    """Generate exactly 7 practical Java coding tasks for a peer learning session.

    One task per type, all targeting the same learner knowledge gap.
    No MCQs — only hands-on coding challenges.
    """
    if not difficulty_level:
        if mastery_score >= 70:
            difficulty_level = "intermediate"
        elif mastery_score >= 40:
            difficulty_level = "moderate"
        else:
            difficulty_level = "beginner"

    misconception_text = ""
    if misconception:
        misconception_text = (
            f"\n- Common misconception to address: {misconception}"
        )

    task_types = [
        "write_code",
        "complete_missing_code",
        "fix_incorrect_code",
        "debug_error",
        "predict_and_correct_behavior",
        "implement_method",
        "improve_solution",
    ]

    prompt = f"""
    You are an expert Java Pedagogy AI Agent for peer collaborative learning.

    Generate exactly 7 practical Java coding tasks for a learner who has a knowledge gap.
    Each task must be a DIFFERENT type. All tasks must target the SAME subskill.

    Learner Profile:
    - Knowledge Gap Topic: {topic}
    - Weak Subskill: {subskill}
    - Current Mastery Score: {mastery_score}/100
    - Difficulty Level: {difficulty_level}{misconception_text}

    Generate exactly these 7 tasks IN ORDER:

    Task 1 — "write_code":
    Write a complete Java program from scratch that demonstrates the subskill.
    The starter_code should be a minimal class skeleton with a TODO comment.

    Task 2 — "complete_missing_code":
    Provide a partial Java program with TODO markers where code is missing.
    The learner must fill in the missing logic.

    Task 3 — "fix_incorrect_code":
    Provide Java code that has a logic error or incorrect implementation.
    The learner must identify and fix the bug.

    Task 4 — "debug_error":
    Provide Java code that will throw an exception or produce an error.
    The learner must debug and fix it.

    Task 5 — "predict_and_correct_behavior":
    Provide Java code and ask the learner to predict the output,
    then modify the code so it behaves correctly.

    Task 6 — "implement_method":
    Provide a class with method signatures and TODO comments.
    The learner must implement the methods.

    Task 7 — "improve_solution":
    Provide working but suboptimal Java code.
    The learner must refactor and improve it.

    STRICT RULES:
    1. ALL 7 tasks must target '{subskill}' in {topic}. Do NOT vary the topic.
    2. Do NOT generate any multiple-choice questions. Every task requires writing/editing Java code.
    3. Do NOT include the complete solution or answer in any task.
    4. Provide starter_code for every task. Use "// TODO: your code here" markers.
    5. Provide 2-4 requirements per task.
    6. Provide 1-2 hints per task that guide without giving the answer.
    7. Each task should be completable in a short collaborative session.
    8. Make each task progressively more challenging.
    """

    try:
        response = client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a specialized Java Peer Learning Task Generator. "
                        "Generate exactly 7 practical coding challenges, never MCQs. "
                        "Each task must be a different type, all targeting the same subskill."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            response_format=PeerCodingTaskListSchema,
        )

        task_list_data = response.choices[0].message.parsed

        coding_tasks = []
        for idx, task in enumerate(task_list_data.tasks):
            coding_tasks.append({
                "task_number": idx + 1,
                "task_type": task.task_type,
                "task_description": task.task_description,
                "starter_code": task.starter_code,
                "requirements": task.requirements,
                "hints": task.hints,
            })

        return coding_tasks

    except Exception as e:
        print(f"⚠️ OpenAI Peer Coding Tasks Generation Error: {str(e)}")
        return _fallback_coding_tasks(topic, subskill, difficulty_level)


def _fallback_coding_tasks(topic: str, subskill: str, difficulty_level: str) -> List[dict]:
    """Fallback 7 coding tasks when OpenAI is unavailable."""
    return [
        {
            "task_number": 1,
            "task_type": "write_code",
            "task_description": (
                f"Write a complete Java program that demonstrates correct use of "
                f"'{subskill}' in the context of {topic}. The program should handle "
                f"edge cases and follow best practices."
            ),
            "starter_code": (
                f"public class {subskill.replace('-', '').replace(' ', '')}Demo {{\n"
                f"    public static void main(String[] args) {{\n"
                f"        // TODO: Implement {subskill} for {topic}\n"
                f"    }}\n"
                f"}}"
            ),
            "requirements": [
                f"Demonstrate proper use of {subskill}",
                "Handle edge cases appropriately",
                "Include meaningful output or comments",
            ],
            "hints": [
                f"Think about how {subskill} works in {topic}",
                "Consider what happens with invalid or empty input",
            ],
        },
        {
            "task_number": 2,
            "task_type": "complete_missing_code",
            "task_description": (
                f"Complete the missing parts of this Java program that uses "
                f"{subskill} for {topic}. Fill in all TODO sections."
            ),
            "starter_code": (
                f"public class Incomplete {{\n"
                f"    // TODO: Add necessary imports\n\n"
                f"    public static void main(String[] args) {{\n"
                f"        // TODO: Create input and call the method below\n"
                f"    }}\n\n"
                f"    // TODO: Implement a method that demonstrates {subskill}\n"
                f"}}"
            ),
            "requirements": [
                f"Implement all TODO sections to use {subskill}",
                "Ensure the program compiles and runs correctly",
                "Add appropriate error handling",
            ],
            "hints": [
                "Start with the method implementation first",
                "Make sure to handle all possible exceptions",
            ],
        },
        {
            "task_number": 3,
            "task_type": "fix_incorrect_code",
            "task_description": (
                f"The following Java code attempts to use {subskill} but contains bugs. "
                f"Find and fix all the errors."
            ),
            "starter_code": (
                f"public class BuggyCode {{\n"
                f"    public static void main(String[] args) {{\n"
                f"        // This code has errors - find and fix them\n"
                f"        String input = null;\n"
                f"        int result = Integer.parseInt(input); // Bug 1\n"
                f"        System.out.println(result);\n"
                f"    }}\n"
                f"}}"
            ),
            "requirements": [
                "Identify all bugs in the code",
                "Fix each bug while maintaining the program's intent",
                "Explain what was wrong with each bug",
            ],
            "hints": [
                "Check what happens when null is passed to parseInt",
                "Consider using proper {subskill} to handle this",
            ],
        },
        {
            "task_number": 4,
            "task_type": "debug_error",
            "task_description": (
                f"This Java program throws a runtime error. Debug the code, "
                f"understand the error, and make it work correctly using {subskill}."
            ),
            "starter_code": (
                f"public class Debug {{\n"
                f"    public static void main(String[] args) {{\n"
                f"        int[] numbers = {{1, 2, 3}};\n"
                f"        // This will throw an exception - debug and fix it\n"
                f"        for (int i = 0; i <= numbers.length; i++) {{\n"
                f"            System.out.println(numbers[i]);\n"
                f"        }}\n"
                f"    }}\n"
                f"}}"
            ),
            "requirements": [
                "Identify the cause of the error",
                "Fix the code so it runs without exceptions",
                "Explain the root cause of the error",
            ],
            "hints": [
                "Check the loop boundary condition",
                "Consider what happens when i equals numbers.length",
            ],
        },
        {
            "task_number": 5,
            "task_type": "predict_and_correct_behavior",
            "task_description": (
                f"First predict what this Java program outputs, then modify "
                f"the code so it behaves correctly using {subskill}."
            ),
            "starter_code": (
                f"public class Predict {{\n"
                f"    public static void main(String[] args) {{\n"
                f"        String s = \"Hello\";\n"
                f"        String result = s.substring(1, 10); // What happens here?\n"
                f"        System.out.println(result);\n"
                f"    }}\n"
                f"}}"
            ),
            "requirements": [
                "State what you predict the output will be",
                "Explain why the program behaves this way",
                "Modify the code to handle the edge case correctly",
            ],
            "hints": [
                "What is the length of the string?",
                "What does substring do when the end index exceeds the string length?",
            ],
        },
        {
            "task_number": 6,
            "task_type": "implement_method",
            "task_description": (
                f"Implement the method below that demonstrates {subskill} "
                f"for {topic}. The method should handle all edge cases."
            ),
            "starter_code": (
                f"public class MethodImpl {{\n"
                f"    // TODO: Implement this method\n"
                f"    // It should safely parse a string to an integer\n"
                f"    // and return a default value if parsing fails\n"
                f"    public static int safeParse(String input, int defaultValue) {{\n"
                f"        // TODO: your code here\n"
                f"    }}\n\n"
                f"    public static void main(String[] args) {{\n"
                f"        // Test your method with these cases:\n"
                f"        System.out.println(safeParse(\"42\", 0));     // Should print 42\n"
                f"        System.out.println(safeParse(\"abc\", -1));   // Should print -1\n"
                f"        System.out.println(safeParse(null, 0));      // Should print 0\n"
                f"    }}\n"
                f"}}"
            ),
            "requirements": [
                "Handle null input gracefully",
                "Handle non-numeric input gracefully",
                "Return the default value when parsing fails",
                "All three test cases must produce correct output",
            ],
            "hints": [
                "Use try-catch to handle NumberFormatException",
                "Check for null before calling methods on the string",
            ],
        },
        {
            "task_number": 7,
            "task_type": "improve_solution",
            "task_description": (
                f"The following code works but is poorly written. Refactor and improve it "
                f"using best practices for {subskill} in {topic}."
            ),
            "starter_code": (
                f"public class Improve {{\n"
                f"    public static int divide(int a, int b) {{\n"
                f"        return a / b; // Works but no error handling\n"
                f"    }}\n\n"
                f"    public static void main(String[] args) {{\n"
                f"        System.out.println(divide(10, 2));\n"
                f"        System.out.println(divide(10, 0)); // Crashes!\n"
                f"    }}\n"
                f"}}"
            ),
            "requirements": [
                "Add proper error handling for division by zero",
                "Improve the method with meaningful return values or exceptions",
                "Add input validation and clear documentation",
                "Make the main method safe to run",
            ],
            "hints": [
                "Consider returning an Optional or throwing a descriptive exception",
                "Use proper {subskill} to handle the error case",
            ],
        },
    ]
