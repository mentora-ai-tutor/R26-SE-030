import os
import re
import tempfile
import shutil
import subprocess
import logging
from app.config import EXECUTION_TIMEOUT, RUN_TIMEOUT

logger = logging.getLogger(__name__)


def extract_class_name(code: str) -> str:
    match = re.search(r"public\s+class\s+(\w+)", code)
    if match:
        return match.group(1)
    match = re.search(r"\bclass\s+(\w+)", code)
    if match:
        return match.group(1)
    return "Main"


def execute_java_code(code: str, stdin_input: str = None) -> dict:
    tmp_dir = tempfile.mkdtemp(prefix="java-sandbox-")

    try:
        class_name = extract_class_name(code)
        file_path = os.path.join(tmp_dir, f"{class_name}.java")

        with open(file_path, "w") as f:
            f.write(code)

        logger.info(f"Compiling Java code: class={class_name}")

        compile_result = subprocess.run(
            ["javac", file_path],
            capture_output=True,
            text=True,
            timeout=EXECUTION_TIMEOUT,
            cwd=tmp_dir,
        )

        if compile_result.returncode != 0:
            error_output = compile_result.stderr.strip() or "Compilation failed"
            logger.info(f"Compilation error: {error_output[:200]}")
            return {
                "success": False,
                "output": None,
                "error": error_output,
                "is_compilation_error": True,
                "exit_code": compile_result.returncode,
            }

        logger.info("Compilation successful, running code...")

        run_kwargs = {
            "args": ["java", "-cp", tmp_dir, class_name],
            "capture_output": True,
            "text": True,
            "timeout": RUN_TIMEOUT,
            "cwd": tmp_dir,
        }

        if stdin_input is not None:
            run_kwargs["input"] = stdin_input

        run_result = subprocess.run(**run_kwargs)

        stdout = run_result.stdout.strip()
        stderr = run_result.stderr.strip()

        if run_result.returncode != 0:
            error_output = stderr or f"Runtime error (exit code {run_result.returncode})"
            logger.info(f"Runtime error: {error_output[:200]}")
            return {
                "success": False,
                "output": stdout or None,
                "error": error_output,
                "is_compilation_error": False,
                "exit_code": run_result.returncode,
            }

        logger.info(f"Execution successful: output_length={len(stdout)}")
        return {
            "success": True,
            "output": stdout or None,
            "error": None,
            "is_compilation_error": False,
            "exit_code": 0,
        }

    except subprocess.TimeoutExpired:
        logger.error("Code execution timed out")
        return {
            "success": False,
            "output": None,
            "error": "Execution timed out. Check for infinite loops or long-running operations.",
            "is_compilation_error": False,
            "exit_code": None,
        }
    except Exception as e:
        logger.error(f"Code execution failed: {str(e)}")
        return {
            "success": False,
            "output": None,
            "error": f"Execution failed: {str(e)}",
            "is_compilation_error": False,
            "exit_code": None,
        }
    finally:
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            pass
