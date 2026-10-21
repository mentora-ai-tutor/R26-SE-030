"""Workspace AI study assistant and the Java execution sandbox interface.

The assistant coaches with hints instead of handing over full solutions, in line
with the peer-learning platform's pedagogy goals. It reuses the existing
OpenAI-compatible ``support_agent`` used across the service.

The Java run/compile layer is intentionally a stub. Executing arbitrary learner
code on the API host is unsafe; the interface below documents the security
requirements a real executor must satisfy before the stub is replaced.
"""

import logging
from typing import Any, Dict, Optional

from app.agents.support_agent import support_agent

logger = logging.getLogger(__name__)

MAX_CODE_CONTEXT_CHARS = 20_000

COACHING_SYSTEM_HINT = (
    "You are a study coach embedded in a group project workspace for Java learners. "
    "Coach the student: give hints, point out the concept they are missing, and ask a "
    "guiding question before revealing anything. Never paste a complete solution; show "
    "at most 3-5 lines of illustrative code. Keep answers short and readable."
)


def build_assistant_prompt(
    question: str,
    code: Optional[str] = None,
    file_path: Optional[str] = None,
) -> str:
    """Composes the coaching prompt sent to the shared support agent."""
    parts = [COACHING_SYSTEM_HINT, "", f"Student question: {question.strip()}"]
    if code:
        label = f"Selected code from {file_path}:" if file_path else "Selected code:"
        parts.extend(
            [
                "",
                label,
                "```java",
                code[:MAX_CODE_CONTEXT_CHARS],
                "```",
            ]
        )
    return "\n".join(parts)


def ask_assistant(
    question: str,
    student_id: str,
    code: Optional[str] = None,
    file_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Ask the coaching assistant; returns the support-agent result envelope."""
    prompt = build_assistant_prompt(question, code=code, file_path=file_path)
    result = support_agent.get_response(prompt, student_id=student_id)
    if result.get("status") != "success":
        logger.warning("Workspace assistant unavailable for student %s", student_id)
    return result


# ---------------------------------------------------------------------------
# Sandboxed Java execution (stub)
# ---------------------------------------------------------------------------

SANDBOX_SECURITY_REQUIREMENTS = """
Replacing this stub with a real executor MUST satisfy all of the following:

1. Run every compilation/execution inside a throwaway Docker container
   (e.g. ``openjdk:17-alpine``) created per request and removed afterwards.
2. Network must be disabled for the container (``--network=none``).
3. Hard resource limits: CPUs (``--cpus=0.5``), memory (``--memory=128m``,
   ``--memory-swap=128m``), pids limit (``--pids-limit=64``) and a wall-clock
   timeout (10s) enforced by the host, killing the container on expiry.
4. Run as a non-root user, with a read-only root filesystem and no extra
   capabilities (``--cap-drop=ALL``, ``--security-opt=no-new-privileges``).
5. Mount only a tmpfs scratch directory for sources/classes; never mount the
   host workspace or any secrets.
6. Sanitize/escape stdout/stderr before streaming to clients; cap output size.
7. Rate-limit run requests per student and per workspace.
"""


class JavaSandboxStub:
    """Interface-compatible stub for the sandboxed Java runner.

    It validates the request and explains that execution is disabled instead of
    running any learner code. See ``SANDBOX_SECURITY_REQUIREMENTS``.
    """

    enabled = False

    def run(self, code: str, stdin: str = "", language: str = "java") -> Dict[str, Any]:
        if (language or "java").lower() != "java":
            return {
                "status": "unsupported",
                "language": language,
                "message": "Only Java execution is supported in project workspaces.",
            }
        return {
            "status": "stub",
            "language": "java",
            "stdout": "",
            "stderr": "",
            "exit_code": None,
            "compile_output": "",
            "duration_ms": 0,
            "message": (
                "Code execution is not enabled on this deployment. "
                "The sandbox interface is ready; see the workspace README section "
                "for the Docker isolation requirements needed to enable it."
            ),
        }


java_sandbox = JavaSandboxStub()
