import subprocess

from app.services.executor import extract_class_name, execute_java_code


class FakeResult:
    def __init__(self, returncode, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_extract_class_name_public_class():
    assert extract_class_name("public class HelloWorld { }") == "HelloWorld"


def test_extract_class_name_class_without_public():
    assert extract_class_name("class Calculator { }") == "Calculator"


def test_extract_class_name_fallback_main():
    assert extract_class_name("int x = 1;") == "Main"


def test_execute_success_flow(monkeypatch):
    runs = []
    def fake_run(*a, **kw):
        cmd = a[0] if a else kw.get("args", [])
        runs.append((cmd, kw))
        name = cmd[0] if isinstance(cmd, list) else cmd
        if name == "javac":
            return FakeResult(0)
        return FakeResult(0, stdout="Hello Mentora\n", stderr="")

    import app.services.executor as exec_mod
    monkeypatch.setattr(exec_mod.subprocess, "run", fake_run)

    result = execute_java_code("public class Main { }")
    assert result["success"] is True
    assert result["output"] == "Hello Mentora"
    assert result["exit_code"] == 0

    compile_cmd = runs[0][0]
    run_cmd = runs[1][1]["args"]
    assert compile_cmd[0] == "javac"
    assert run_cmd[0] == "java"
    assert "-cp" in run_cmd
    assert run_cmd[-1] == "Main"


def test_execute_compilation_error(monkeypatch):
    def fake_run(*a, **kw):
        cmd = a[0] if a else kw.get("args", [])
        name = cmd[0] if isinstance(cmd, list) else cmd
        if name == "javac":
            return FakeResult(1, stderr="error: cannot find symbol")
        raise AssertionError("java should not run on compile failure")

    import app.services.executor as exec_mod
    monkeypatch.setattr(exec_mod.subprocess, "run", fake_run)

    result = execute_java_code("public class Bad { }")
    assert result["success"] is False
    assert result["is_compilation_error"] is True
    assert "cannot find symbol" in result["error"]


def test_execute_runtime_error(monkeypatch):
    def fake_run(*a, **kw):
        cmd = a[0] if a else kw.get("args", [])
        name = cmd[0] if isinstance(cmd, list) else cmd
        if name == "javac":
            return FakeResult(0)
        return FakeResult(1, stdout="", stderr="Exception in thread main")

    import app.services.executor as exec_mod
    monkeypatch.setattr(exec_mod.subprocess, "run", fake_run)

    result = execute_java_code("public class Main { }")
    assert result["success"] is False
    assert result["is_compilation_error"] is False
    assert result["exit_code"] == 1
    assert "Exception in thread main" in result["error"]


def test_execute_passes_stdin_to_run(monkeypatch):
    captured = {}
    def fake_run(*a, **kw):
        cmd = a[0] if a else kw.get("args", [])
        if cmd[0] == "javac":
            return FakeResult(0)
        captured["kwargs"] = kw
        return FakeResult(0, stdout="5", stderr="")

    import app.services.executor as exec_mod
    monkeypatch.setattr(exec_mod.subprocess, "run", fake_run)

    execute_java_code("public class Main { }", stdin_input="5 10")
    assert captured["kwargs"].get("input") == "5 10"


def test_execute_timeout_handled(monkeypatch):
    import app.services.executor as exec_mod

    def fake_run(*a, **kw):
        cmd = a[0] if a else kw.get("args", [])
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=kw.get("timeout"))

    monkeypatch.setattr(exec_mod.subprocess, "run", fake_run)

    result = execute_java_code("public class Main { }")
    assert result["success"] is False
    assert "timed out" in result["error"].lower()
