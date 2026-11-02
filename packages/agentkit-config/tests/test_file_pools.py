from __future__ import annotations

from pathlib import Path

import pytest
from agentkit_config.errors import SpecErrors
from agentkit_config.pools import (
    AgentFileRegistry,
    PromptRegistry,
    SkillRegistry,
    SubagentRegistry,
)
from agentkit_config.pools.prompts import ALLOWED_VARS, render, variables


def _w(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_duplicate_across_roots_is_error(tmp_path: Path) -> None:
    a = _w(tmp_path / "r1/prompts/a.md", "x")
    b = _w(tmp_path / "r2/prompts/a.md", "y")
    with pytest.raises(SpecErrors) as ei:
        PromptRegistry.from_roots([tmp_path / "r1", tmp_path / "r2"])
    assert str(a) in str(ei.value) and str(b) in str(ei.value)


def test_unknown_lists_known(tmp_path: Path) -> None:
    _w(tmp_path / "prompts/a.md", "x")
    reg = PromptRegistry.from_roots([tmp_path])
    with pytest.raises(SpecErrors, match="known: a"):
        reg.get("b", file="f", path="p")


def test_prompt_name_from_relative_path(tmp_path: Path) -> None:
    _w(tmp_path / "prompts/research/orchestrator.md", "hello\n\n")
    reg = PromptRegistry.from_roots([tmp_path])
    assert reg.names() == ["research/orchestrator"]
    assert reg.get("research/orchestrator", file="f", path="p").text == "hello"


def test_prompt_front_matter_stripped(tmp_path: Path) -> None:
    _w(tmp_path / "prompts/a.md", "---\ntitle: T\n---\nbody line\n")
    assert PromptRegistry.from_roots([tmp_path]).get("a", file="f", path="p").text == "body line"


def test_render_vars(tmp_path: Path) -> None:
    _w(tmp_path / "prompts/a.md", "hi {{agent_name}} on {{ date }}")
    p = PromptRegistry.from_roots([tmp_path]).get("a", file="f", path="p")
    assert variables(p.text) == {"agent_name", "date"} == ALLOWED_VARS
    assert render(p, agent_name="bot", date="2026-01-01") == "hi bot on 2026-01-01"


def test_skill_tools_from_metadata_and_allowed_tools(tmp_path: Path) -> None:
    _w(
        tmp_path / "skills/alpha/SKILL.md",
        "---\nname: alpha\nallowed-tools: read_file  grep\n"
        "metadata:\n  include_tools: [web_search]\n---\nBody\n",
    )
    skill = SkillRegistry.from_roots([tmp_path]).get("alpha", file="f", path="p")
    assert skill.tools == frozenset({"read_file", "grep", "web_search"})
    assert skill.dir == tmp_path / "skills/alpha"


def test_skill_name_mismatch(tmp_path: Path) -> None:
    md = _w(tmp_path / "skills/alpha/SKILL.md", "---\nname: beta\n---\nBody\n")
    with pytest.raises(SpecErrors) as ei:
        SkillRegistry.from_roots([tmp_path])
    assert str(md) in str(ei.value)


def test_subagent_pool_keyed_by_name(tmp_path: Path) -> None:
    _w(
        tmp_path / "subagents/file_name.yaml",
        "apiVersion: agentkit/v1\nkind: SubAgent\nname: searcher\ndescription: d\nprompt: p\n",
    )
    reg = SubagentRegistry.from_roots([tmp_path])
    assert reg.names() == ["searcher"]


def test_agent_pool_finds_agent_yaml_and_agents_dir(tmp_path: Path) -> None:
    _w(tmp_path / "agent.yaml", "name: main_agent\n")
    other = _w(tmp_path / "agents/x.yaml", "name: other\n")
    reg = AgentFileRegistry.from_roots([tmp_path])
    assert reg.names() == ["main_agent", "other"]
    assert reg.get("other", file="f", path="p") == other


def test_agent_pool_missing_name(tmp_path: Path) -> None:
    _w(tmp_path / "agent.yaml", "name: 3\n")
    with pytest.raises(SpecErrors) as ei:
        AgentFileRegistry.from_roots([tmp_path])
    assert ei.value.errors[0].path == "name"


def test_non_utf8_prompt_is_spec_error(tmp_path: Path) -> None:
    p = tmp_path / "r/prompts/a.md"
    p.parent.mkdir(parents=True)
    p.write_bytes(b"\xff\xfe bad")
    with pytest.raises(SpecErrors) as ei:
        PromptRegistry.from_roots([tmp_path / "r"])
    assert str(p) in str(ei.value) and "UTF-8" in str(ei.value)


def test_non_utf8_skill_is_spec_error(tmp_path: Path) -> None:
    p = tmp_path / "r/skills/s/SKILL.md"
    p.parent.mkdir(parents=True)
    p.write_bytes(b"\xff\xfe bad")
    with pytest.raises(SpecErrors) as ei:
        SkillRegistry.from_roots([tmp_path / "r"])
    assert str(p) in str(ei.value) and "UTF-8" in str(ei.value)
