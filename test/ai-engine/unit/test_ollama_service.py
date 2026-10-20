import asyncio
import json

from app.services.ollama_service import (
    _find_balanced_json,
    _fix_llm_json,
    _call_ollama_json,
)


def test_find_balanced_json_object():
    text = 'prefix text {"a": 1, "b": "val"} trailing text'
    result = _find_balanced_json(text)
    assert result == '{"a": 1, "b": "val"}'


def test_find_balanced_json_array():
    text = 'prefix [1, {"k": "v"}, 3] suffix'
    result = _find_balanced_json(text)
    assert result == '[1, {"k": "v"}, 3]'


def test_find_balanced_json_ignores_braces_in_strings():
    text = '{"msg": "brace } inside string", "n": 1}'
    result = _find_balanced_json(text)
    assert result == text
    assert json.loads(result)["msg"] == "brace } inside string"


def test_find_balanced_json_returns_none_when_no_json():
    assert _find_balanced_json("no json here") is None


def test_fix_llm_json_fixes_unescaped_newlines():
    raw = '{"summary": "line one\nline two", "score": 7}'
    fixed = _fix_llm_json(raw)
    assert fixed is not None
    parsed = json.loads(fixed)
    assert parsed["summary"] == "line one\nline two"
    assert parsed["score"] == 7


def test_fix_llm_json_fixes_unescaped_tab():
    raw = '{"note": "a\tb"}'
    fixed = _fix_llm_json(raw)
    assert fixed is not None
    assert json.loads(fixed)["note"] == "a\tb"


def test_call_ollama_json_parses_code_fence(tmp_path, monkeypatch):
    async def fake_call(messages, temperature=0.7, num_predict=300, model=None):
        return '```json\n{"annotations": [], "summary": "ok", "overall_score": 8}\n```'

    import app.services.ollama_service as ollama_mod
    monkeypatch.setattr(ollama_mod, "_call_ollama", fake_call)

    result = asyncio.run(_call_ollama_json([{"role": "user", "content": "x"}]))
    assert result["overall_score"] == 8


def test_call_ollama_json_retries_with_code_model_on_failure(monkeypatch):
    import app.services.ollama_service as ollama_mod
    from app.services.ollama_service import code_review

    calls = []

    async def fake_call(messages, temperature=0.7, num_predict=300, model=None):
        calls.append(model)
        if model == ollama_mod.OLLAMA_MODEL:
            return "not valid json at all"
        return (
            '```json\n{"annotations": [{"line_start": 1, "line_end": 1, '
            '"category": "style", "severity": "low", "message": "m", '
            '"suggestion": "s"}], "summary": "fixed", "overall_score": 9}\n```'
        )

    monkeypatch.setattr(ollama_mod, "_call_ollama", fake_call)

    import asyncio
    result = asyncio.run(code_review("public class A {}"))
    assert isinstance(result, dict)
    assert result["overall_score"] == 9
    assert calls[0] == ollama_mod.OLLAMA_MODEL
    assert calls[1] == ollama_mod.OLLAMA_CODE_MODEL


def test_call_ollama_json_returns_empty_on_all_parsing_failures(monkeypatch):
    import app.services.ollama_service as ollama_mod

    async def fake_call(messages, temperature=0.7, num_predict=300, model=None):
        return "All JSON parsing strategies failed case: !!! no json !!!"

    monkeypatch.setattr(ollama_mod, "_call_ollama", fake_call)

    result = asyncio.run(_call_ollama_json([{"role": "user", "content": "x"}]))
    assert result == {}
