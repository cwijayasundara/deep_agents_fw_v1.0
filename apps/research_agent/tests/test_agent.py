import pytest
from agentkit_config import CodePools, SpecErrors, load_agent, read_output
from agentkit_core import ConfigError, ModelRegistry, Settings
from agentkit_deep.testing import scripted, tool_call
from agentkit_tools import Page, Source, make_fetch_tool, make_web_search_tool
from langchain_core.messages import AIMessage, HumanMessage
from research_agent import DEFAULT_AGENT


class FakeSearch:
    async def search(self, query, k=5):
        return [Source("https://a.example/x", "A", "fact about x")]


class FakeFetch:
    async def fetch(self, url):
        return Page(url, "A", "body")


def fake_pools() -> CodePools:
    return CodePools.from_entry_points().override(
        tools={
            "web_search": lambda ctx, **kw: make_web_search_tool(FakeSearch()),
            "fetch_url": lambda ctx, **kw: make_fetch_tool(FakeFetch()),
        }
    )


def lib(pools=None):
    from agentkit_config import Library

    return Library.for_file(DEFAULT_AGENT, pools or fake_pools())


def test_every_registry_entry_loads_with_model_override():
    for name in ModelRegistry.default().names():
        loaded = load_agent(
            DEFAULT_AGENT,
            settings=Settings(_env_file=None),
            library=lib(),
            overrides={"model": name, "selection": "off"},
            model=scripted(AIMessage(content="x")),
        )
        assert loaded.graph is not None
        assert loaded.spec.model == name


async def test_end_to_end_report_with_citation():
    report = "# R\nX is true [1]\n\n## Sources\n[1] https://a.example/x"
    model = scripted(
        tool_call("web_search", {"query": "x"}, "1"),
        tool_call("write_file", {"file_path": "/report.md", "content": report}, "2"),
        AIMessage(content="done"),
    )
    loaded = load_agent(
        DEFAULT_AGENT,
        settings=Settings(_env_file=None),
        library=lib(),
        overrides={"model": "anthropic", "selection": "off"},
        model=model,
    )
    out = await loaded.graph.ainvoke({"messages": [HumanMessage("what is x?")]})
    text = read_output(out, loaded.spec.output)
    assert "https://a.example/x" in text and "[1]" in text
    tool_msgs = [m.content for m in out["messages"] if m.type == "tool"]
    assert any("https://a.example/x" in str(c) for c in tool_msgs)  # citation was retrieved


def test_decisions_selection_requires_openai_key():
    with pytest.raises(ConfigError, match="OPENAI_API_KEY"):
        load_agent(
            DEFAULT_AGENT,
            settings=Settings(_env_file=None, tavily_api_key="t"),
            library=lib(),
            overrides={"model": "anthropic"},
        )


def test_decisions_selection_builds_with_keys():
    s = Settings(_env_file=None, tavily_api_key="t", openai_api_key="o", anthropic_api_key="a")
    loaded = load_agent(DEFAULT_AGENT, settings=s, library=lib(), overrides={"model": "anthropic"})
    assert loaded.graph is not None


def test_shipped_agent_enables_decisions():
    from agentkit_config.spec import parse_agent

    spec = parse_agent(DEFAULT_AGENT)
    assert spec.selection == "decisions" and spec.output == "/report.md"


def test_unknown_model_override_lists_registry():
    with pytest.raises(SpecErrors, match="anthropic"):
        load_agent(
            DEFAULT_AGENT,
            settings=Settings(_env_file=None),
            library=lib(),
            overrides={"model": "nope"},
        )


async def test_cli_from_other_cwd(tmp_path, monkeypatch):
    import agentkit_config.load as load_mod
    from research_agent import cli

    built: dict = {}
    monkeypatch.setattr(load_mod, "build_deep_agent", lambda **kw: built.update(kw) or object())
    pools = fake_pools()
    monkeypatch.setattr(CodePools, "from_entry_points", classmethod(lambda cls: pools))
    monkeypatch.setenv("OPENAI_API_KEY", "o")
    monkeypatch.setenv("FIREWORKS_API_KEY", "f")
    monkeypatch.chdir(tmp_path)

    async def fake_run(agent, inputs, config, **kw):
        return {"files": {"/report.md": "# r"}}

    monkeypatch.setattr(cli, "run_with_progress", fake_run)
    assert await cli.run("q", str(DEFAULT_AGENT), {}) == "# r"
    assert built["name"] == "research_agent"


def test_cli_bad_model_exits_2_with_error_text(monkeypatch, capsys):
    from research_agent import cli

    monkeypatch.setattr("sys.argv", ["research", "q", "--model", "nope"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "nope" in err and "anthropic" in err and "Traceback" not in err
