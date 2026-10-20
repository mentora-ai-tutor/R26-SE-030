import os
import re
import tempfile
import subprocess
import logging
from typing import Dict, Any, Optional, Tuple, List

logger = logging.getLogger("assessment_agent")


class AssessmentAgent:
    def __init__(self):
        self.javac_available = self._check_javac_installed()
        if self.javac_available:
            logger.info("JDK (javac) detected. Native compilation validation enabled.")
        else:
            logger.warning("JDK (javac) not found. Falling back to strict structural validation.")

    def _check_javac_installed(self) -> bool:
        try:
            result = subprocess.run(
                ["javac", "-version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False

    def evaluate_java_code(
        self, student_id: str, code: str, topic_id: Optional[str] = None
    ) -> Dict[str, Any]:
        clean_code = code.strip() if code else ""

        # 1. Empty Code Check
        if not clean_code:
            return self._build_response(
                student_id=student_id,
                is_valid=False,
                feedback="Code submission cannot be empty.",
                complexity="N/A",
                passed_tests=False,
                errors=["Empty code payload received."],
                suggestions=["Please write a valid Java class with a main method."]
            )

        # 2. Class Declaration Check
        if "class" not in clean_code:
            return self._build_response(
                student_id=student_id,
                is_valid=False,
                feedback="Invalid Java syntax: Missing 'class' keyword.",
                complexity="N/A",
                passed_tests=False,
                errors=["Submission does not contain a valid Java class structure."],
                suggestions=["Wrap your code inside 'public class Main { ... }'."]
            )

        # 3. Compilation / Fallback Validation
        if self.javac_available:
            compile_success, compile_errors = self._compile_with_javac(clean_code)
            if not compile_success:
                return self._build_response(
                    student_id=student_id,
                    is_valid=False,
                    feedback="Java compilation failed due to syntax errors.",
                    complexity="N/A",
                    passed_tests=False,
                    errors=compile_errors,
                    suggestions=["Fix the compilation errors listed in the error log."]
                )
        else:
            fallback_valid, fallback_errors = self._fallback_syntax_check(clean_code)
            if not fallback_valid:
                return self._build_response(
                    student_id=student_id,
                    is_valid=False,
                    feedback="Java syntax validation failed.",
                    complexity="N/A",
                    passed_tests=False,
                    errors=fallback_errors,
                    suggestions=["Check for missing semicolons ';', curly braces '{ }', or parentheses."]
                )

        # 4. Success Response
        return self._build_response(
            student_id=student_id,
            is_valid=True,
            feedback="Code syntax and structure are correct.",
            complexity=self._estimate_complexity(clean_code),
            passed_tests=True,
            errors=[],
            suggestions=["Great job! Your Java code passed all syntax checks."]
        )

    def _compile_with_javac(self, code: str) -> Tuple[bool, List[str]]:
        class_match = re.search(r'(?:public\s+)?class\s+([A-Za-z0-9_]+)', code)
        class_name = class_match.group(1) if class_match else "Main"

        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = os.path.join(temp_dir, f"{class_name}.java")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(code)

            try:
                res = subprocess.run(
                    ["javac", file_path],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if res.returncode == 0:
                    return True, []

                raw_errors = res.stderr.strip().split("\n")
                clean_errors = [e.strip() for e in raw_errors if e.strip() and not e.startswith("Note:")]
                return False, clean_errors if clean_errors else [res.stderr.strip()]

            except subprocess.TimeoutExpired:
                return False, ["Compilation timed out (exceeded 10 seconds)."]
            except Exception as e:
                return False, [f"Compiler error: {str(e)}"]

    def _fallback_syntax_check(self, code: str) -> Tuple[bool, List[str]]:
        errors = []

        # 1. Bracket Matching Check
        if code.count("{") != code.count("}"):
            errors.append("Mismatched curly braces '{' and '}'.")
        if code.count("(") != code.count(")"):
            errors.append("Mismatched parentheses '(' and ')'.")
        if code.count("[") != code.count("]"):
            errors.append("Mismatched square brackets '[' and ']'.")

        # 2. Main Method Check
        if "main" not in code or "void" not in code:
            errors.append("Missing main method block (e.g., 'public static void main(String[] args)').")

        # 3. Clean string literals
        clean = re.sub(r'"([^"\\]|\\.)*"', '""', code)

        # 4. Strict Semicolon Check (Matches single-line statements missing ';')
        missing_semicolon_pattern = r'(\b(?:int|double|float|long|short|byte|char|boolean|String|var|[A-Z]\w*)\s+[a-zA-Z_]\w*(?:\s*=[^;{}]+)?)\s*(?=[\}\n\r])'

        matches = re.finditer(missing_semicolon_pattern, clean)
        for match in matches:
            stmt = match.group(1).strip()
            errors.append(f"Missing semicolon ';' after statement: '{stmt}'")

        if errors:
            return False, errors
        return True, []

    def _estimate_complexity(self, code: str) -> str:
        loops = len(re.findall(r'\b(for|while)\b', code))
        if loops == 0:
            return "O(1)"
        elif loops == 1:
            return "O(n)"
        else:
            return f"O(n^{loops})"

    def _build_response(
        self, student_id: str, is_valid: bool, feedback: str, complexity: str,
        passed_tests: bool, errors: List[str], suggestions: List[str]
    ) -> Dict[str, Any]:
        return {
            "status": "success",
            "student_id": student_id,
            "language": "java",
            "evaluation": {
                "is_valid": is_valid,
                "feedback": feedback,
                "complexity": complexity,
                "passed_tests": passed_tests,
                "errors": errors,
                "suggestions": suggestions
            }
        }


# Global Assessment Agent Instance
assessment_agent = AssessmentAgent()