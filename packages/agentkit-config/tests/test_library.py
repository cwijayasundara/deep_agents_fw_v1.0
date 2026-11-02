from __future__ import annotations

from pathlib import Path

import pytest
from agentkit_config.library import Library


def test_for_file_independent_of_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = tmp_path / "repo"
    app = repo / "apps/x"
    app.mkdir(parents=True)
    (repo / "libraries").mkdir()
    (app / "agent.yaml").write_text("name: x\n")
    (tmp_path / "elsewhere").mkdir()
    monkeypatch.delenv("AGENTKIT_LIBRARY_PATH", raising=False)
    monkeypatch.chdir(tmp_path / "elsewhere")
    lib = Library.for_file(app / "agent.yaml")
    assert list(lib.roots) == [app.resolve(), (repo / "libraries").resolve()]
    assert lib.agents.names() == ["x"]


def test_for_file_env_path_and_missing_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    extra = tmp_path / "extra"
    extra.mkdir()
    monkeypatch.setenv("AGENTKIT_LIBRARY_PATH", f"{extra}:{tmp_path / 'nope'}")
    f = tmp_path / "a" / "agent.yaml"
    f.parent.mkdir()
    lib = Library.for_file(f)
    assert list(lib.roots) == [f.parent.resolve(), extra]
