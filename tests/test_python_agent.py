"""Tests for the python_agent sub-agent and the python_execute backend.

Covers the workspace/file-tool improvements:
- python_execute persistent workdir vs. ephemeral behaviour
- configurable stdout offload threshold (max_inline_chars)
- the in-process file tools and their safe-path guard
- the sub-agent loop (plan -> write_file -> read_file -> finish) with a stub LLM
- verify-before-finish rejection of non-existent declared output files
"""

import json
from pathlib import Path

import pytest

from src.services import python_agent as pa
from src.services.python_agent import (
    _resolve_safe_path,
    _tool_list_files,
    _tool_read_file,
    _tool_write_file,
    python_agent,
)
from src.services.python_exec import python_execute

# ---------------------------------------------------------------------------
# python_execute: workspace / threshold behaviour
# ---------------------------------------------------------------------------


class TestPythonExecuteWorkdir:
    def test_workdir_persists_files_across_calls(self, tmp_path):
        ws = tmp_path / "ws"
        # First call writes a file with a relative path.
        r1 = python_execute(
            code="open('data.txt', 'w').write('hello')\nprint('wrote')",
            workdir=str(ws),
        )
        assert r1["success"], r1
        assert (ws / "data.txt").read_text() == "hello"

        # Second, independent subprocess can read it back (same workspace).
        r2 = python_execute(
            code="print(open('data.txt').read())",
            workdir=str(ws),
        )
        assert r2["success"], r2
        assert "hello" in r2["stdout"]

    def test_workdir_does_not_move_outputs_to_tmp_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TMP_DIR", str(tmp_path / "tmp"))
        ws = tmp_path / "ws"
        python_execute(code="open('out.csv', 'w').write('a,b')", workdir=str(ws))
        # File stays in the workspace; it is NOT moved into TMP_DIR.
        assert (ws / "out.csv").exists()
        assert not (tmp_path / "tmp" / "out.csv").exists()

    def test_ephemeral_mode_moves_outputs_to_tmp_dir(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TMP_DIR", str(tmp_path / "tmp"))
        # No workdir -> ephemeral temp CWD, deliverables moved into TMP_DIR.
        r = python_execute(code="open('result.json', 'w').write('{}')")
        assert r["success"], r
        assert (tmp_path / "tmp" / "result.json").exists()

    def test_max_inline_chars_offloads_large_stdout(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TMP_DIR", str(tmp_path / "tmp"))
        r = python_execute(code="print('x' * 500)", max_inline_chars=100)
        assert "output_file" in r
        assert "too large" in r["stdout"].lower()
        assert Path(r["output_file"]).exists()

    def test_small_stdout_stays_inline(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TMP_DIR", str(tmp_path / "tmp"))
        r = python_execute(code="print('hi')", max_inline_chars=100)
        assert "output_file" not in r
        assert r["stdout"].strip() == "hi"


# ---------------------------------------------------------------------------
# File tools + safe-path guard
# ---------------------------------------------------------------------------


class TestFileTools:
    def test_write_then_read(self, tmp_path):
        ws = tmp_path / "ws"
        ws.mkdir()
        tmp_dir = tmp_path / "tmp"
        tmp_dir.mkdir()

        w = _tool_write_file({"path": "report.md", "content": "# Title"}, ws, tmp_dir)
        assert w["success"], w
        assert (ws / "report.md").read_text() == "# Title"

        r = _tool_read_file({"path": "report.md"}, ws, tmp_dir)
        assert r["success"], r
        assert r["content"] == "# Title"

    def test_read_line_range(self, tmp_path):
        ws = tmp_path / "ws"
        ws.mkdir()
        (ws / "f.txt").write_text("l1\nl2\nl3\nl4")
        r = _tool_read_file({"path": "f.txt", "start_line": 2, "end_line": 3}, ws, ws)
        assert r["content"] == "l2\nl3"

    def test_read_truncates_to_max_bytes(self, tmp_path):
        ws = tmp_path / "ws"
        ws.mkdir()
        (ws / "big.txt").write_text("y" * 1000)
        r = _tool_read_file({"path": "big.txt", "max_bytes": 50}, ws, ws)
        assert r["truncated"] is True
        assert len(r["content"]) == 50

    def test_list_files(self, tmp_path):
        ws = tmp_path / "ws"
        ws.mkdir()
        (ws / "a.txt").write_text("a")
        (ws / "sub").mkdir()
        (ws / "sub" / "b.txt").write_text("bb")
        r = _tool_list_files({}, ws, ws)
        names = {f["path"] for f in r["files"]}
        assert "a.txt" in names
        assert str(Path("sub") / "b.txt") in names

    def test_read_allows_tmp_dir_input(self, tmp_path):
        ws = tmp_path / "ws"
        ws.mkdir()
        tmp_dir = tmp_path / "tmp"
        tmp_dir.mkdir()
        (tmp_dir / "input.json").write_text('{"k": 1}')
        # Absolute path under TMP_DIR is allowed for reads (offloaded inputs).
        r = _tool_read_file({"path": str(tmp_dir / "input.json")}, ws, tmp_dir)
        assert r["success"], r
        assert r["content"] == '{"k": 1}'

    def test_safe_path_rejects_outside_roots(self, tmp_path):
        ws = tmp_path / "ws"
        ws.mkdir()
        tmp_dir = tmp_path / "tmp"
        tmp_dir.mkdir()
        with pytest.raises(ValueError):
            _resolve_safe_path("/etc/passwd", ws, tmp_dir, for_write=False)
        # TMP_DIR is read-only scope: writes there must be rejected.
        with pytest.raises(ValueError):
            _resolve_safe_path(str(tmp_dir / "x.txt"), ws, tmp_dir, for_write=True)

    def test_write_rejected_outside_workspace(self, tmp_path):
        ws = tmp_path / "ws"
        ws.mkdir()
        tmp_dir = tmp_path / "tmp"
        tmp_dir.mkdir()
        res = _tool_write_file({"path": "../escape.txt", "content": "x"}, ws, tmp_dir)
        assert res["success"] is False
        assert not (tmp_path / "escape.txt").exists()


# ---------------------------------------------------------------------------
# Stub LLM plumbing for the sub-agent loop
# ---------------------------------------------------------------------------


class _FakeFunction:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments


class _FakeToolCall:
    def __init__(self, name, arguments, call_id="call_1"):
        self.id = call_id
        self.function = _FakeFunction(name, json.dumps(arguments))


class _FakeMessage:
    def __init__(self, tool_calls=None, content=""):
        self.tool_calls = tool_calls
        self.content = content

    def model_dump(self):
        return {"role": "assistant", "content": self.content or ""}


class _FakeChoice:
    def __init__(self, message):
        self.message = message


class _FakeResponse:
    def __init__(self, message):
        self.choices = [_FakeChoice(message)]


class _FakeLLMClient:
    def __init__(self, scripted):
        self._scripted = list(scripted)
        self.calls = 0

    def complete_with_tools(self, messages, tools):
        self.calls += 1
        return _FakeResponse(self._scripted.pop(0))


def _install_fake_llm(monkeypatch, scripted):
    fake = _FakeLLMClient(scripted)
    monkeypatch.setattr("src.core.llm_client.LLMClient", lambda cfg: fake)
    monkeypatch.setattr("src.core.llm_client.LLMConfig.from_settings", lambda ss, **kw: object())
    return fake


class _FakeSettings:
    def get_config_with_fallback(self, key, default=None):
        return default


def _call(name, args, call_id="c"):
    return _FakeMessage(tool_calls=[_FakeToolCall(name, args, call_id)])


@pytest.mark.asyncio
class TestPythonAgentLoop:
    async def test_plan_write_read_finish(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TMP_DIR", str(tmp_path))
        scripted = [
            _call("plan", {"steps": ["write a report"], "role": "writer"}),
            _call("write_file", {"path": "report.txt", "content": "done"}),
            _call("read_file", {"path": "report.txt"}),
            _call("finish", {"summary": "Wrote the report.", "success": True}),
        ]
        _install_fake_llm(monkeypatch, scripted)

        result = await python_agent(goal="Write a report", settings_service=_FakeSettings())

        assert result["success"] is True
        assert result["summary"] == "Wrote the report."
        # The deliverable is auto-discovered by the workspace scan.
        assert any(p.endswith("report.txt") for p in result["output_files"])

    async def test_finish_rejected_when_declared_file_missing(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TMP_DIR", str(tmp_path))
        missing = str(tmp_path / "nope.txt")
        scripted = [
            _call("plan", {"steps": ["x"], "role": "writer"}),
            _call(
                "finish",
                {"summary": "claims a file", "success": True, "output_files": [missing]},
            ),
            # After the rejection nudge, the agent finishes cleanly.
            _call("finish", {"summary": "Done without files.", "success": True}),
        ]
        fake = _install_fake_llm(monkeypatch, scripted)

        result = await python_agent(goal="do it", settings_service=_FakeSettings())

        assert result["success"] is True
        assert result["summary"] == "Done without files."
        # All three scripted responses were consumed (the first finish was rejected).
        assert fake.calls == 3

    async def test_llm_retry_on_transient_failure(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TMP_DIR", str(tmp_path))

        class FlakyClient:
            def __init__(self):
                self.calls = 0

            def complete_with_tools(self, messages, tools):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("transient network error")
                return _FakeResponse(
                    _FakeMessage(
                        tool_calls=[_FakeToolCall("finish", {"summary": "ok", "success": True})]
                    )
                )

        flaky = FlakyClient()
        monkeypatch.setattr("src.core.llm_client.LLMClient", lambda cfg: flaky)
        monkeypatch.setattr(
            "src.core.llm_client.LLMConfig.from_settings", lambda ss, **kw: object()
        )
        # Avoid real backoff sleeps.
        monkeypatch.setattr(pa.asyncio, "sleep", _no_sleep)

        result = await python_agent(goal="do it", settings_service=_FakeSettings())
        assert result["success"] is True
        assert flaky.calls == 2


async def _no_sleep(_seconds):
    return None
