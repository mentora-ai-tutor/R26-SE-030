"""Sandboxed Java compile/execute used by the Project Workspace module.

The sandbox never passes user input to a shell: every child process is started
with an argument vector, a throwaway working directory, a hard wall-clock
timeout, bounded memory, and truncated output.  Compilation and execution are
separate steps so that the caller can compile without running code when
``WORKSPACE_CODE_RUN_ENABLED`` is false.
"""

import logging
import os
import re
import shutil
import subprocess
import time
from typing import Dict, List, Optional

logger = logging.getLogger("code_sandbox")

COMPILE_TIMEOUT_SECONDS = 20
RUN_TIMEOUT_SECONDS = 10

MAX_FILES = 25
MAX_SOURCE_BYTES = 400_000
MAX_OUTPUT_CHARS = 40_000
MAX_STDIN_BYTES = 20_000

JVM_MEMORY_FLAGS = ["-Xmx128m", "-Xss1m", "-XX:MaxMetaspaceSize=64m"]

# Matched against the whole file so nested/inner classes do not confuse us.
_CLASS_RE = re.compile(r"\bclass\s+([A-Za-z_$][\w$]*)")
_PUBLIC_CLASS_RE = re.compile(r"\bpublic\s+(?:final\s+|abstract\s+)*class\s+([A-Za-z_$][\w$]*)")
_MAIN_METHOD_RE = re.compile(r"\bpublic\s+static\s+void\s+main\s*\(")
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._$-]")

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if os.name == "nt" else 0


def _clip(text: str) -> str:
    if len(text) <= MAX_OUTPUT_CHARS:
        return text
    return text[:MAX_OUTPUT_CHARS] + f"\n... [output truncated at {MAX_OUTPUT_CHARS} characters]"


def safe_source_name(name: str) -> Optional[str]:
    """Map an arbitrary workspace filename onto a safe, flat ``.java`` filename."""
    base = (name or "").replace("\\", "/").rstrip("/").split("/")[-1].strip()
    if not base:
        return None
    base = _SAFE_NAME_RE.sub("_", base)
    if base in {".", ".."} or base.startswith("."):
        base = "_" + base
    if not base.lower().endswith(".java"):
        base += ".java"
    return base[:120]


def detect_main_class(sources: Dict[str, str]) -> str:
    """Pick the JVM entry point: a class declaring main(), else the first file's class."""
    fallback = os.path.splitext(next(iter(sources)))[0] if sources else "Main"
    for filename, code in sources.items():
        stem = os.path.splitext(filename)[0]
        classes = [match.group(1) for match in _CLASS_RE.finditer(code)]
        if _MAIN_METHOD_RE.search(code):
            if stem in classes:
                return stem
            if classes:
                return classes[0]
            return stem
    for filename, code in sources.items():
        stem = os.path.splitext(filename)[0]
        public = [match.group(1) for match in _PUBLIC_CLASS_RE.finditer(code)]
        if stem in public:
            return stem
    return fallback


def _posix_resource_limiter():
    """CPU/memory/fork caps where the OS supports them (no-op on Windows)."""

    def _limit() -> None:  # pragma: no cover - exercised only on POSIX
        try:
            import resource

            hard = RUN_TIMEOUT_SECONDS + 5
            resource.setrlimit(resource.RLIMIT_CPU, (hard, hard))
            resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
            resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
            resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_SOURCE_BYTES, MAX_SOURCE_BYTES))
        except Exception:  # pragma: no cover - best effort
            pass

    return _limit if os.name != "nt" else None


def _run(cmd: List[str], *, cwd: str, timeout: int, stdin_data: str = "") -> Dict[str, object]:
    """Run a command in the sandbox workdir and normalise the outcome."""
    started = time.time()
    try:
        completed = subprocess.run(
            cmd,
            cwd=cwd,
            input=stdin_data,
            capture_output=True,
            text=True,
            timeout=timeout,
            preexec_fn=_posix_resource_limiter(),
            creationflags=_CREATE_NO_WINDOW,
        )
        return {
            "ran": True,
            "exit_code": completed.returncode,
            "stdout": _clip(completed.stdout or ""),
            "stderr": _clip(completed.stderr or ""),
            "duration_ms": int((time.time() - started) * 1000),
            "command": " ".join(cmd),
        }
    except FileNotFoundError:
        return {
            "ran": False,
            "exit_code": None,
            "stdout": "",
            "stderr": f"{cmd[0]} not found on the server.",
            "duration_ms": int((time.time() - started) * 1000),
            "command": " ".join(cmd),
        }
    except subprocess.TimeoutExpired as exc:
        partial_out = exc.output or ""
        partial_err = exc.stderr or ""
        if isinstance(partial_out, bytes):
            partial_out = partial_out.decode("utf-8", "replace")
        if isinstance(partial_err, bytes):
            partial_err = partial_err.decode("utf-8", "replace")
        return {
            "ran": False,
            "exit_code": None,
            "stdout": _clip(partial_out),
            "stderr": _clip(partial_err + f"\n{cmd[0]} timed out after {timeout} seconds."),
            "duration_ms": int((time.time() - started) * 1000),
            "command": " ".join(cmd),
            "timed_out": True,
        }


def compile_and_run(
    sources: Dict[str, str],
    *,
    main_class: Optional[str] = None,
    stdin_data: str = "",
    execute: bool = True,
) -> Dict[str, object]:
    """Compile ``sources`` and, when allowed, run the detected entry point."""
    result: Dict[str, object] = {
        "compiled": False,
        "compile_errors": [],
        "output": "",
        "error": "",
        "exit_code": None,
        "command": "",
        "compile_command": "",
        "run_command": "",
        "main_class": main_class,
        "scope": "file",
        "files_compiled": len(sources),
        "duration_ms": 0,
    }

    if not sources:
        result["error"] = "No Java sources to compile."
        result["compile_errors"] = ["No Java sources to compile."]
        return result

    if len(sources) > MAX_FILES:
        result["error"] = f"Too many source files (limit {MAX_FILES})."
        result["compile_errors"] = [f"Too many source files (limit {MAX_FILES})."]
        return result

    total_bytes = sum(len(code.encode("utf-8")) for code in sources.values())
    if total_bytes > MAX_SOURCE_BYTES:
        result["error"] = f"Sources exceed the {MAX_SOURCE_BYTES // 1000} KB limit."
        result["compile_errors"] = [f"Sources exceed the {MAX_SOURCE_BYTES // 1000} KB limit."]
        return result

    if shutil.which("javac") is None:
        message = "javac not found on the server. Install a JDK to compile and run Java."
        result["error"] = message
        result["compile_errors"] = [message]
        return result

    safe_names = []
    written: Dict[str, str] = {}
    for name, code in sources.items():
        safe = safe_source_name(name)
        if not safe:
            continue
        if safe in written:
            stem = os.path.splitext(safe)[0]
            suffix = 1
            while f"{stem}_{suffix}.java" in written:
                suffix += 1
            safe = f"{stem}_{suffix}.java"
        written[safe] = code
        safe_names.append(safe)

    if not written:
        result["error"] = "No valid .java source files to compile."
        result["compile_errors"] = ["No valid .java source files to compile."]
        return result

    workdir = os.path.realpath(_make_workdir())
    try:
        for safe, code in written.items():
            with open(os.path.join(workdir, safe), "w", encoding="utf-8") as handle:
                handle.write(code)

        compile_cmd = ["javac", "-encoding", "UTF-8", "-nowarn", *sorted(written)]
        result["compile_command"] = " ".join(compile_cmd)
        result["command"] = result["compile_command"]
        compile_run = _run(compile_cmd, cwd=workdir, timeout=COMPILE_TIMEOUT_SECONDS)

        if not compile_run["ran"] or compile_run["exit_code"] != 0:
            errors = _format_compile_errors(str(compile_run["stderr"] or ""), sorted(written))
            result["compiled"] = False
            result["compile_errors"] = errors
            result["output"] = str(compile_run["stdout"] or "")
            result["error"] = str(compile_run["stderr"] or "")
            result["exit_code"] = compile_run["exit_code"]
            result["command"] = str(compile_run["command"])
            result["duration_ms"] = compile_run["duration_ms"]
            return result

        result["compiled"] = True
        result["compile_errors"] = []
        result["output"] = ""
        result["error"] = ""
        result["command"] = str(compile_run["command"])
        result["duration_ms"] = compile_run["duration_ms"]

        if not execute:
            return result

        entry_point = main_class or detect_main_class(written)
        result["main_class"] = entry_point

        if shutil.which("java") is None:
            result["error"] = "java not found on the server. Install a JDK runtime to execute programs."
            return result

        run_cmd = ["java", *JVM_MEMORY_FLAGS, "-cp", ".", entry_point]
        run_result = _run(
            run_cmd,
            cwd=workdir,
            timeout=RUN_TIMEOUT_SECONDS,
            stdin_data=stdin_data[:MAX_STDIN_BYTES],
        )
        result["output"] = str(run_result["stdout"] or "")
        result["error"] = str(run_result["stderr"] or "")
        result["exit_code"] = run_result["exit_code"]
        result["run_command"] = str(run_result["command"])
        result["command"] = str(run_result["command"])
        result["duration_ms"] = int(result["duration_ms"]) + int(run_result["duration_ms"])
        return result
    finally:
        _cleanup(workdir)


def _make_workdir() -> str:
    import tempfile

    return tempfile.mkdtemp(prefix="ws_sandbox_")


def _cleanup(workdir: str) -> None:
    try:
        shutil.rmtree(workdir, ignore_errors=True)
    except Exception as exc:  # pragma: no cover - best effort
        logger.warning("Sandbox cleanup failed for %s: %s", workdir, exc)


def _format_compile_errors(stderr: str, filenames: List[str]) -> List[str]:
    """Return javac's diagnostics as lines, adding context when a file is unmentioned."""
    lines = [line.rstrip() for line in (stderr or "").strip().splitlines() if line.strip()]
    if not lines:
        return ["Compilation failed."]
    if len(filenames) > 1:
        mentioned = [name for name in filenames if name.lower() in (stderr or "").lower()]
        if not mentioned:
            lines.append("")
            lines.append("Compiled files: " + ", ".join(filenames))
    return lines
