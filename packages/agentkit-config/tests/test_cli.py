from __future__ import annotations

from pathlib import Path

import pytest
from agentkit_config.cli import main

REPO = Path(__file__).resolve().parents[3]


def _write(tmp_path: Path, name: str, text: str) -> str:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return str(p)


def _agent(tools: str = "[web_search]") -> str:
    return (
        "apiVersion: agentkit/v1\nkind: Agent\nname: a\nmodel: fireworks-glm\n"
        f"prompt: research/orchestrator\ntools: {tools}\n"
    )


@pytest.fixture
def lib(tmp_path: Path) -> Path:
    d = tmp_path / "libraries" / "prompts" / "research"
    d.mkdir(parents=True)
    (d / "orchestrator.md").write_text("You are {{agent_name}}.", encoding="utf-8")
    return tmp_path


def test_valid_agent_exit_0(lib: Path, capsys: pytest.CaptureFixture[str]) -> None:
    f = _write(lib, "agent.yaml", _agent())
    assert main(["validate", f]) == 0
    assert "checked 1 file(s): 0 error(s)" in capsys.readouterr().out


def test_bad_tool_exit_1_and_prints_path(lib: Path, capsys: pytest.CaptureFixture[str]) -> None:
    f = _write(lib, "agent.yaml", _agent("[nope]"))
    assert main(["validate", f]) == 1
    out = capsys.readouterr().out
    assert f"{f}:tools[0]" in out and "nope" in out


def test_warning_only_exit_0(capsys: pytest.CaptureFixture[str]) -> None:
    f = str(REPO / "libraries/subagents/researcher.yaml")
    assert main(["validate", f]) == 0
    out = capsys.readouterr().out
    assert "response_schema" in out and "1 warning(s)" in out


def test_unmatched_glob_skipped(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate", "apps/*/flows/*.yaml"]) == 0
    assert "checked 0 file(s)" in capsys.readouterr().out


def test_runs_without_keys(
    lib: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import os

    for k in [k for k in os.environ if k.endswith("_API_KEY")]:
        monkeypatch.delenv(k)
    assert main(["validate", _write(lib, "agent.yaml", _agent())]) == 0


def test_bad_kind_and_syntax_no_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    a = _write(tmp_path, "a.yaml", "kind: Wat\n")
    b = _write(tmp_path, "b.yaml", "x: [\n")
    assert main(["validate", a, b]) == 1
    assert "2 error(s)" in capsys.readouterr().out


def test_flow_not_supported_and_usage(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    f = _write(tmp_path, "f.yaml", "kind: Flow\n")
    assert main(["validate", f]) == 1
    assert "flows not supported yet" in capsys.readouterr().out
    assert main([]) == 2
    assert main(["frob"]) == 2
