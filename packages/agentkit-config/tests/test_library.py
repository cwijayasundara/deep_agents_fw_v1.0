from __future__ import annotations

import os
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


def test_roots_resolved_and_deduplicated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_libs = Path(__file__).resolve().parents[3] / "libraries"
    monkeypatch.setenv("AGENTKIT_LIBRARY_PATH", f"{repo_libs}{os.pathsep}{repo_libs}/../libraries")
    lib = Library.for_file(repo_libs.parent / "apps" / "research_agent" / "agent.yaml")
    assert len(set(lib.roots)) == len(lib.roots)
    assert lib.prompts.names()


def test_from_roots_dedupes(tmp_path: Path) -> None:
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "p.md").write_text("x")
    lib = Library.from_roots([tmp_path, tmp_path / "." / "prompts" / ".."])
    assert lib.roots == (tmp_path.resolve(),)
