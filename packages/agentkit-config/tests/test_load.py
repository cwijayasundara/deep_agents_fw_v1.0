from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from agentkit_config import CodePools, Library, SpecErrors, load_agent, read_output
from agentkit_config.load import apply_overrides
from agentkit_config.registry import Registry
from agentkit_config.resolve import resolve_agent
from agentkit_config.spec import parse_agent
from agentkit_core import ConfigError, ModelRegistry, Settings
from agentkit_deep.testing import scripted, tool_call
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool

SETTINGS = Settings(_env_file=None)


def _search(ctx: Any, **_: Any) -> Any:
    @tool
    def web_search(query: str) -> str:
        """Search the web."""
        return "fact [https://a.example/x]"

    return web_search


def _other(ctx: Any, **_: Any) -> Any:
    @tool
    def other(query: str) -> str:
        """Other."""
        return "o"

    return other


class MwA(AgentMiddleware):
    pass


class MwB(AgentMiddleware):
    pass


class MwC(AgentMiddleware):
    pass


def _pools() -> CodePools:
    return CodePools(
        Registry("tool", {"web_search": _search, "other": _other}),
        Registry(
            "middleware",
            {"a": lambda ctx: MwA(), "b": lambda ctx: MwB(), "c": lambda ctx: MwC()},
        ),
        Registry("node", {}),
        Registry("schema", {}),
    )


def _write(tmp_path: Path, agent_extra: str = "", sub: str = "") -> Path:
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "main.md").write_text("I am {{agent_name}}.")
    (tmp_path / "subagents").mkdir()
    (tmp_path / "subagents" / "r.yaml").write_text(
        "apiVersion: agentkit/v1\nkind: SubAgent\nname: r\ndescription: d\nprompt: main\n"
        "tools: [other]\n" + sub
    )
    p = tmp_path / "agent.yaml"
    p.write_text(
        "apiVersion: agentkit/v1\nkind: Agent\nname: demo\nmodel: anthropic\nprompt: main\n"
        "tools: [web_search]\nsubagents: [r]\noutput: null\n" + agent_extra
    )
    return p


def _lib(tmp_path: Path) -> Library:
    return Library.from_roots([tmp_path], _pools())


async def test_end_to_end_yaml_agent_writes_output(tmp_path):
    p = _write(tmp_path).read_text().replace("output: null", "output: /report.md")
    path = tmp_path / "agent.yaml"
    path.write_text(p.replace("output: /report.md\n", ""))
    report = "# R\nX [1]\n\n## Sources\n[1] https://a.example/x"
    model = scripted(
        tool_call("web_search", {"query": "x"}, "1"),
        tool_call("write_file", {"file_path": "/report.md", "content": report}, "2"),
        AIMessage(content="done"),
    )
    loaded = load_agent(path, settings=SETTINGS, library=_lib(tmp_path), model=model)
    out = await loaded.graph.ainvoke({"messages": [HumanMessage("what is x?")]})
    assert "https://a.example/x" in read_output(out, "/report.md")
    assert read_output(out, None) == "done"


def test_unknown_model_override_fails_before_build(tmp_path, monkeypatch):
    import agentkit_config.load as load_mod

    def boom(**_: Any) -> Any:
        raise AssertionError("build_deep_agent must not be called")

    monkeypatch.setattr(load_mod, "build_deep_agent", boom)
    p = _write(tmp_path)
    with pytest.raises(SpecErrors, match="anthropic"):
        load_agent(p, settings=SETTINGS, library=_lib(tmp_path), overrides={"model": "nope"})


def test_override_rejects_unknown_key(tmp_path):
    spec = parse_agent(_write(tmp_path))
    with pytest.raises(SpecErrors, match="prompt"):
        apply_overrides(spec, {"prompt": "x"})


def test_selection_off_override(tmp_path):
    p = _write(tmp_path, "selection: decisions\n")
    spec = parse_agent(p)
    assert spec.selection == "decisions"
    assert apply_overrides(spec, {"selection": "off"}).selection is None
    assert apply_overrides(spec, {"tier": "fast"}).tier == "fast"


def test_decisions_requires_openai_key(tmp_path):
    p = _write(tmp_path, "selection: decisions\n")
    with pytest.raises(ConfigError, match="OPENAI_API_KEY"):
        load_agent(p, settings=SETTINGS, library=_lib(tmp_path), model=scripted())


def test_middleware_order(tmp_path):
    p = _write(
        tmp_path,
        "middleware:\n  - {type: a}\n  - {type: c, enabled: false}\n  - {type: b}\n"
        "selection: decisions\n",
    )
    from pydantic import SecretStr

    s = Settings(_env_file=None, openai_api_key=SecretStr("k"))
    spec = parse_agent(p)
    kw = resolve_agent(spec, _lib(tmp_path), ModelRegistry.default(), s, model=scripted())
    names = [type(m).__name__ for m in kw["middleware"]]
    assert names == ["MwA", "MwB", "SelectionMiddleware"]


def test_subagent_tools_replace_parent(tmp_path):
    spec = parse_agent(_write(tmp_path))
    kw = resolve_agent(spec, _lib(tmp_path), ModelRegistry.default(), SETTINGS, model=scripted())
    assert [t.name for t in kw["tools"]] == ["web_search"]
    (sub,) = kw["subagents"]
    assert [t.name for t in sub["tools"]] == ["other"]
    assert "model" not in sub and "skills" not in sub


def test_prompt_rendered_with_agent_name(tmp_path):
    spec = parse_agent(_write(tmp_path))
    kw = resolve_agent(spec, _lib(tmp_path), ModelRegistry.default(), SETTINGS, model=scripted())
    assert kw["system_prompt"] == "I am demo."
    assert kw["subagents"][0]["system_prompt"] == "I am r."
    assert "skills" not in kw and "backend" not in kw


def test_subagent_tier_uses_parent_entry(tmp_path):
    p = _write(tmp_path, sub="tier: fast\n")
    spec = parse_agent(p)
    from pydantic import SecretStr

    s = Settings(_env_file=None, anthropic_api_key=SecretStr("k"))
    kw = resolve_agent(spec, _lib(tmp_path), ModelRegistry.default(), s, model=scripted())
    assert "model" in kw["subagents"][0]
