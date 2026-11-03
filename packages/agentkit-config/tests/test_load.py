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
from agentkit_deep.testing import ctx, scripted, tool_call
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool

SETTINGS = Settings(_env_file=None, deployment_tenant="default")  # built at import: pin tenant


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
    out = await loaded.graph.ainvoke({"messages": [HumanMessage("what is x?")]}, context=ctx())
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
    assert names == ["SelectionMiddleware", "MwA", "MwB"]  # selection outermost, then unknown types


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


def test_subagent_model_without_tier_uses_parent_tier(tmp_path, monkeypatch):
    import agentkit_config.resolve as resolve_mod

    seen: list[Any] = []
    monkeypatch.setattr(resolve_mod, "get_model", lambda spec, settings: seen.append(spec) or spec)
    p = _write(tmp_path, sub="model: openai\n")
    spec = parse_agent(p).model_copy(update={"tier": "fast"})
    tiers = {"fast": "m-fast", "default": "m-default", "strong": "m-strong"}
    reg = ModelRegistry({"anthropic": tiers, "openai": tiers})
    resolve_agent(spec, _lib(tmp_path), reg, SETTINGS, model=scripted())
    assert [s.model_id for s in seen] == ["m-fast"]


def test_bad_override_value_is_spec_errors(tmp_path):
    spec = parse_agent(_write(tmp_path))
    with pytest.raises(SpecErrors, match="selection"):
        apply_overrides(spec, {"selection": "foo"})
    with pytest.raises(SpecErrors, match="tier"):
        apply_overrides(spec, {"tier": 3})  # type: ignore[dict-item]


def _with_skill(tmp_path: Path) -> Path:
    p = _write(tmp_path, "skills: [alpha]\n")
    d = tmp_path / "skills" / "alpha"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text("---\nname: alpha\ndescription: Alpha skill\n---\n\n# Alpha\n")
    return p


def test_persistence_absorbs_skills_into_the_memory_backend(tmp_path):
    from agentkit_deep.testing import memory_persistence

    p = memory_persistence()
    spec = parse_agent(_with_skill(tmp_path))
    kw = resolve_agent(
        spec, _lib(tmp_path), ModelRegistry.default(), SETTINGS, model=scripted(), persistence=p
    )
    assert kw["persistence"] is p
    assert set(kw["backend"].routes) == {"/skills/demo/", "/org/", "/memories/"}
    assert [r.paths for r in kw["permissions"]] == [["/skills/**"]]
    assert kw["skills"] == ["/skills/demo/"]


def test_persistence_without_skills_leaves_the_backend_to_the_factory(tmp_path):
    from agentkit_deep.testing import memory_persistence

    spec = parse_agent(_write(tmp_path))
    p = memory_persistence()
    kw = resolve_agent(
        spec, _lib(tmp_path), ModelRegistry.default(), SETTINGS, model=scripted(), persistence=p
    )
    assert kw["persistence"] is p and "backend" not in kw


def test_no_persistence_keeps_the_plain_skills_mount(tmp_path):
    spec = parse_agent(_with_skill(tmp_path))
    kw = resolve_agent(spec, _lib(tmp_path), ModelRegistry.default(), SETTINGS, model=scripted())
    assert "persistence" not in kw
    assert set(kw["backend"].routes) == {"/skills/demo/"}


async def test_load_agent_with_persistence_keeps_skills_and_memory(tmp_path):
    from agentkit_deep.testing import memory_persistence

    p = memory_persistence()
    model = scripted(
        tool_call("write_file", {"file_path": "/memories/AGENTS.md", "content": "n"}, "1"),
        AIMessage(content="done"),
    )
    loaded = load_agent(
        _with_skill(tmp_path),
        settings=SETTINGS,
        library=_lib(tmp_path),
        model=model,
        persistence=p,
    )
    assert loaded.graph.checkpointer is p.saver
    await loaded.graph.ainvoke(
        {"messages": [HumanMessage("x")]},
        context=ctx(),
        config={"configurable": {"thread_id": "t"}},
    )
    ns = ("default", "agentkit", "platform", "local", "memories")
    assert (await p.store.aget(ns, "/AGENTS.md")) is not None


def test_yaml_cannot_name_the_guard(tmp_path):
    """The guards are installed by build_deep_agent, never configured: no pool offers them."""
    p = _write(tmp_path, "middleware:\n  - {type: agentkit_guards}\n")
    lib = Library.from_roots([tmp_path], CodePools.from_entry_points())
    with pytest.raises(SpecErrors, match="unknown middleware 'agentkit_guards'"):
        load_agent(p, settings=SETTINGS, library=lib, model=scripted())
