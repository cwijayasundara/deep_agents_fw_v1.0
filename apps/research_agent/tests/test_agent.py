import pytest
from agentkit_config import CodePools, SpecErrors, load_agent, read_output
from agentkit_core import ConfigError, ModelRegistry, Settings
from agentkit_deep.testing import ctx, scripted, tool_call
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
    out = await loaded.graph.ainvoke({"messages": [HumanMessage("what is x?")]}, context=ctx())
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


def test_exit_on_spec_errors_prints_only_errors(capsys):
    from agentkit_config.errors import SpecError
    from research_agent.agent import exit_on_spec_errors

    def boom():
        raise SpecErrors(
            [SpecError("f", "a", "bad"), SpecError("f", "b", "meh", severity="warning")]
        )

    with pytest.raises(SystemExit) as ei:
        exit_on_spec_errors(boom)
    assert ei.value.code == 2
    err = capsys.readouterr().err
    assert "bad" in err and "meh" not in err


def test_shipped_agent_loads_without_tavily_key(monkeypatch):
    # Search defaults to DuckDuckGo, so the shipped agent and its researcher need no Tavily key.
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    loaded = load_agent(
        DEFAULT_AGENT,
        settings=Settings(_env_file=None),
        library=lib(CodePools.from_entry_points()),
        overrides={"selection": "off"},
        model=scripted(AIMessage(content="x")),
    )
    assert loaded.graph is not None


@pytest.fixture
def offline_cli(tmp_path, monkeypatch):
    """research/research-eval with the graph build and the run stubbed; records run contexts."""
    import agentkit_config.load as load_mod
    from research_agent import cli, eval_cli

    monkeypatch.setattr(load_mod, "build_deep_agent", lambda **kw: object())
    pools = fake_pools()
    monkeypatch.setattr(CodePools, "from_entry_points", classmethod(lambda cls: pools))
    monkeypatch.setenv("OPENAI_API_KEY", "o")
    monkeypatch.setenv("FIREWORKS_API_KEY", "f")
    monkeypatch.delenv("AGENTKIT_TENANT", raising=False)
    monkeypatch.chdir(tmp_path)
    contexts: list = []

    async def fake_run(agent, inputs, config, *, context, **kw):
        contexts.append(context)
        return {"files": {"/report.md": "# r [1]\n\n## Sources\n[1] https://a.example/x"}}

    monkeypatch.setattr(cli, "run_with_progress", fake_run)
    monkeypatch.setattr(eval_cli, "run_with_progress", fake_run)
    return contexts


def test_help_lists_tenant_user_thread_with_defaults(monkeypatch, capsys):
    from research_agent import cli

    monkeypatch.setattr("sys.argv", ["research", "--help"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 0
    out = " ".join(capsys.readouterr().out.split())
    assert "--tenant TENANT" in out and "(default: default)" in out
    assert "--user USER" in out and "(default: local)" in out
    assert "--thread THREAD" in out and "new uuid4" in out


def test_cli_mints_and_prints_thread_and_runs_under_context(offline_cli, monkeypatch, capsys):
    import uuid

    from agentkit_config.spec import parse_agent
    from research_agent import cli

    monkeypatch.setattr("sys.argv", ["research", "q", "--user", "u1"])
    cli.main()
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("thread: ") and lines[-1] == "wrote report.md"
    thread = lines[0].removeprefix("thread: ")
    uuid.UUID(thread)
    (c,) = offline_cli
    spec = parse_agent(DEFAULT_AGENT)
    assert (c.tenant, c.user_id, c.thread_id) == ("default", "u1", thread)
    assert (c.product, c.team) == ("agentkit", "platform")
    assert (c.agent_name, c.agent_version) == (spec.name, spec.version)


def test_cli_thread_flag_is_used(offline_cli, monkeypatch, capsys):
    from research_agent import cli

    monkeypatch.setattr("sys.argv", ["research", "q", "--tenant", "acme", "--thread", "th-1"])
    cli.main()
    assert capsys.readouterr().out.startswith("thread: th-1\n")
    assert offline_cli[0].tenant == "acme" and offline_cli[0].thread_id == "th-1"


def test_cli_bad_tenant_exits_2_naming_tenant(offline_cli, monkeypatch, capsys):
    from research_agent import cli

    monkeypatch.setattr("sys.argv", ["research", "q", "--tenant", "acme.corp"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2
    assert "--tenant" in capsys.readouterr().err and offline_cli == []


def test_eval_mints_one_thread_per_case(offline_cli, monkeypatch, tmp_path):
    from research_agent import eval_cli

    data = tmp_path / "d.jsonl"
    data.write_text(
        "".join(f'{{"id": "{q}", "question": "{q}", "must_cover": ["x"]}}\n' for q in "abc")
    )

    class Judge:
        def __init__(self, model):
            pass

        async def __call__(self, case, report, retrieved):
            return {"score": 1.0}

    monkeypatch.setattr(eval_cli, "LLMJudge", Judge)
    monkeypatch.setattr(eval_cli, "get_model", lambda spec, settings: None)
    monkeypatch.setattr("sys.argv", ["research-eval", "--dataset", str(data), "--user", "e1"])
    eval_cli.main()
    summary = (tmp_path / "eval_results.json").read_text()
    assert '"completed": 1.0' in summary  # every case ran (errors are swallowed per case)
    threads = [c.thread_id for c in offline_cli]
    assert len(threads) == 3 and len(set(threads)) == 3
    assert {(c.tenant, c.user_id) for c in offline_cli} == {("default", "e1")}


def test_cli_tenant_mismatch_exits_1_with_one_line(offline_cli, monkeypatch, capsys):
    from agentkit_middleware import TenantMismatch
    from research_agent import cli

    async def refused(*a, **kw):
        raise TenantMismatch("run tenant 'other' != deployment tenant 'acme'")

    monkeypatch.setattr(cli, "run_with_progress", refused)
    monkeypatch.setattr("sys.argv", ["research", "q", "--tenant", "other"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "TenantMismatch: run tenant 'other' != deployment tenant 'acme'" in err
    assert "Traceback" not in err
