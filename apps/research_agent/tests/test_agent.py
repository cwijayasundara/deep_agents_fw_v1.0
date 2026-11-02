import pytest
from agentkit_config import CodePools, SpecErrors, load_agent, read_output
from agentkit_core import ConfigError, ModelRegistry, Settings
from agentkit_deep.testing import ctx, scripted, tool_call
from agentkit_telemetry import CostLedger
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
            settings=Settings(_env_file=None, fireworks_api_key="f"),
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
        settings=Settings(_env_file=None, fireworks_api_key="f"),
        library=lib(),
        overrides={"model": "anthropic", "selection": "off"},
        model=model,
    )
    out = await loaded.graph.ainvoke({"messages": [HumanMessage("what is x?")]}, context=ctx())
    text = read_output(out, loaded.spec.output)
    assert "https://a.example/x" in text and "[1]" in text
    tool_msgs = [m.content for m in out["messages"] if m.type == "tool"]
    assert any("https://a.example/x" in str(c) for c in tool_msgs)  # citation was retrieved


async def test_default_run_config_lets_the_call_limits_bound_a_long_run():
    """Each middleware hook is a graph step, so the stack multiplies steps per model call. The
    default recursion limit must not end a run the stack's own call limits would still allow."""
    from agentkit_deep import agent_prompt_hash
    from agentkit_telemetry import run_config

    report = "# R\nX [1]\n\n## Sources\n[1] https://a.example/x"
    searches = [tool_call("web_search", {"query": f"x{i}"}, str(i)) for i in range(30)]
    model = scripted(
        *searches,
        tool_call("write_file", {"file_path": "/report.md", "content": report}, "w"),
        AIMessage(content="done"),
    )
    loaded = load_agent(
        DEFAULT_AGENT,
        settings=Settings(_env_file=None, fireworks_api_key="f"),
        library=lib(),
        overrides={"selection": "off"},
        model=model,
    )
    c = ctx()
    config = run_config(c, agent_prompt_hash(loaded.graph), CostLedger())
    out = await loaded.graph.ainvoke(
        {"messages": [HumanMessage("what is x?")]}, config=dict(config), context=c
    )
    assert "https://a.example/x" in read_output(out, loaded.spec.output)


async def test_tool_budget_never_blocks_writing_the_report():
    """A run that spends its whole search/fetch budget must still be able to save /report.md."""
    from agentkit_deep import agent_prompt_hash
    from agentkit_telemetry import run_config

    report = "# R\nX [1]\n\n## Sources\n[1] https://a.example/x"
    calls = [tool_call("web_search", {"query": f"x{i}"}, f"s{i}") for i in range(24)]
    calls += [tool_call("fetch_url", {"url": "https://a.example/x"}, f"f{i}") for i in range(28)]
    model = scripted(
        *calls,
        tool_call("write_file", {"file_path": "/report.md", "content": report}, "w"),
        AIMessage(content="done"),
    )
    loaded = load_agent(
        DEFAULT_AGENT,
        settings=Settings(_env_file=None, fireworks_api_key="f"),
        library=lib(),
        overrides={"selection": "off"},
        model=model,
    )
    c = ctx()
    config = run_config(c, agent_prompt_hash(loaded.graph), CostLedger())
    out = await loaded.graph.ainvoke(
        {"messages": [HumanMessage("what is x?")]}, config=dict(config), context=c
    )
    assert read_output(out, loaded.spec.output) == report
    blocked = [m for m in out["messages"] if m.type == "tool" and m.status == "error"]
    assert blocked  # the budget did bite on search/fetch


async def test_a_reply_that_only_announces_more_work_is_sent_back_to_finish_the_report():
    """Live glm runs sometimes end on "Let me delegate ..." with no tool call; the run goes on."""
    report = "# R\nX [1]\n\n## Sources\n[1] https://a.example/x"
    model = scripted(
        tool_call("web_search", {"query": "x"}, "1"),
        AIMessage(content="I still need more detail. Let me delegate the remaining gaps."),
        tool_call("write_file", {"file_path": "/report.md", "content": report}, "2"),
        AIMessage(content="done"),
    )
    loaded = load_agent(
        DEFAULT_AGENT,
        settings=Settings(_env_file=None, fireworks_api_key="f"),
        library=lib(),
        overrides={"selection": "off"},
        model=model,
    )
    out = await loaded.graph.ainvoke({"messages": [HumanMessage("what is x?")]}, context=ctx())
    assert read_output(out, loaded.spec.output) == report


def test_decisions_selection_requires_openai_key():
    with pytest.raises(ConfigError, match="OPENAI_API_KEY"):
        load_agent(
            DEFAULT_AGENT,
            settings=Settings(_env_file=None, tavily_api_key="t", fireworks_api_key="f"),
            library=lib(),
            overrides={"model": "anthropic"},
        )


def test_decisions_selection_builds_with_keys():
    s = Settings(
        _env_file=None,
        tavily_api_key="t",
        openai_api_key="o",
        anthropic_api_key="a",
        fireworks_api_key="f",
    )
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
            settings=Settings(_env_file=None, fireworks_api_key="f"),
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
        settings=Settings(_env_file=None, fireworks_api_key="f"),
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
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)
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


def test_cli_thread_flag_is_used(offline_cli, fake_persistence, monkeypatch, capsys):
    from research_agent import cli

    monkeypatch.setenv("AGENTKIT_TENANT", "acme")
    monkeypatch.setattr(cli, "resumed_step", _no_step)
    argv = ["research", "q", "--tenant", "acme", "--thread", "th-1", "--persist"]
    monkeypatch.setattr("sys.argv", argv)
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


async def test_run_called_directly_prints_its_minted_thread(offline_cli, capsys):
    from research_agent import cli

    await cli.run("q", str(DEFAULT_AGENT), {})
    first, *rest = capsys.readouterr().out.splitlines()
    assert first == f"thread: {offline_cli[0].thread_id}"
    assert rest == ["usage: 0 runs, 0 model calls, input 0 (cached 0), output 0, decisions input 0"]


@pytest.fixture
def fake_persistence(monkeypatch):
    """--persist on an in-memory saver/store: records every thread_lock acquisition."""
    from contextlib import asynccontextmanager

    from agentkit_deep.testing import memory_persistence
    from research_agent import persist, telemetry

    p = memory_persistence()
    locks: list[str] = []

    @asynccontextmanager
    async def fake_open(settings):
        yield p

    @asynccontextmanager
    async def fake_lock(persistence, thread_id):
        assert persistence is p
        locks.append(thread_id)
        yield

    async def fake_ledger(persistence):
        assert persistence is p
        ledgers.append(CostLedger())  # no Postgres: the agentkit_usage table is not created
        return ledgers[-1]

    ledgers: list = []
    monkeypatch.setattr(persist.PersistenceSettings, "from_env", classmethod(lambda cls: None))
    monkeypatch.setattr(persist, "open_persistence", fake_open)
    monkeypatch.setattr(persist, "thread_lock", fake_lock)
    monkeypatch.setattr(telemetry, "persistent_ledger", fake_ledger)
    return p, locks


def _scripted_cli(monkeypatch, model):
    """research's load_agent on the fake tool pools and a scripted model (persistence kept)."""
    from research_agent import cli

    loaded: list = []

    def load(path, *, settings, overrides, persistence=None):
        loaded.append(
            load_agent(
                path,
                settings=Settings(_env_file=None, fireworks_api_key="f"),
                library=lib(),
                overrides={"model": "anthropic", "selection": "off"},
                model=model,
                persistence=persistence,
            )
        )
        return loaded[-1]

    monkeypatch.setattr(cli, "load_agent", load)
    return loaded


async def test_persist_resumes_a_thread_and_sees_turn_one(
    fake_persistence, monkeypatch, capsys, tmp_path
):
    from research_agent import cli

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("AGENTKIT_TENANT", raising=False)
    p, locks = fake_persistence
    report = "# R\nX [1]\n\n## Sources\n[1] https://a.example/x"
    report2 = "# R2\nY [1]\n\n## Sources\n[1] https://a.example/y"
    loaded = _scripted_cli(
        monkeypatch,
        scripted(
            tool_call("write_file", {"file_path": "/report.md", "content": report}, "1"),
            AIMessage(content="done"),
            # turn 2 must write its own report: require_output ignores turn one's /report.md
            tool_call("write_file", {"file_path": "/report.md", "content": report2}, "2"),
            AIMessage(content="follow-up answered"),
        ),
    )
    assert await cli.run("turn one", str(DEFAULT_AGENT), {}, thread="th-r", persist=True) == report
    first = capsys.readouterr().out
    assert "resumed thread" not in first
    assert await cli.run("turn two", str(DEFAULT_AGENT), {}, thread="th-r", persist=True) == report2
    out = capsys.readouterr().out
    assert "resumed thread th-r at step " in out
    n = int(out.split("resumed thread th-r at step ")[1].split()[0])
    assert n > 0
    state = await loaded[-1].graph.aget_state({"configurable": {"thread_id": "th-r"}})
    humans = [m.content for m in state.values["messages"] if m.type == "human"]
    assert humans == ["turn one", "turn two"]
    assert locks == ["th-r", "th-r"]


def test_thread_without_persist_is_rejected(offline_cli, monkeypatch, capsys):
    from research_agent import cli

    monkeypatch.setattr("sys.argv", ["research", "q", "--thread", "th-1"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "--thread" in err and "--persist" in err and offline_cli == []


def test_persist_without_database_url_exits_2_naming_it(offline_cli, monkeypatch, capsys):
    from research_agent import cli

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("LANGGRAPH_AES_KEY", "k" * 16)
    monkeypatch.setattr("sys.argv", ["research", "q", "--persist"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "DATABASE_URL" in err and "Traceback" not in err and offline_cli == []


def test_persist_checks_the_tenant_before_any_run(
    fake_persistence, offline_cli, monkeypatch, capsys
):
    """Ruling P4: a mismatched run would write its input to the checkpoint before the guard."""
    from research_agent import cli

    _, locks = fake_persistence
    monkeypatch.setattr("sys.argv", ["research", "q", "--persist", "--tenant", "other"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 1
    assert "run tenant 'other' != deployment tenant 'default'" in capsys.readouterr().err
    assert offline_cli == [] and locks == []


def test_persist_runs_the_turn_in_the_thread_lock_with_the_thread_config(
    fake_persistence, offline_cli, monkeypatch, capsys
):
    from research_agent import cli

    _, locks = fake_persistence
    configs: list = []

    async def fake_run(agent, inputs, config, *, context, **kw):
        configs.append(config)
        offline_cli.append(context)
        return {"files": {"/report.md": "# r"}}

    monkeypatch.setattr(cli, "run_with_progress", fake_run)
    monkeypatch.setattr(cli, "resumed_step", _no_step)
    monkeypatch.setattr("sys.argv", ["research", "q", "--persist", "--thread", "th-9"])
    cli.main()
    assert locks == ["th-9"]
    assert configs[0]["configurable"] == {"thread_id": "th-9"}
    assert offline_cli[0].thread_id == "th-9"


async def _no_step(graph, thread):
    return None


def test_help_describes_thread_resume_and_persist(monkeypatch, capsys):
    from research_agent import cli

    monkeypatch.setattr("sys.argv", ["research", "--help"])
    with pytest.raises(SystemExit):
        cli.main()
    out = " ".join(capsys.readouterr().out.split())
    assert "--persist" in out and "DATABASE_URL" in out
    assert "--thread THREAD" in out and "resume" in out


def test_eval_persist_locks_one_thread_per_case(
    fake_persistence, offline_cli, monkeypatch, tmp_path
):
    from research_agent import eval_cli

    _, locks = fake_persistence
    monkeypatch.setattr(eval_cli, "resumed_step", _no_step, raising=False)
    data = tmp_path / "d.jsonl"
    data.write_text(
        "".join(f'{{"id": "{q}", "question": "{q}", "must_cover": ["x"]}}\n' for q in "ab")
    )

    class Judge:
        def __init__(self, model):
            pass

        async def __call__(self, case, report, retrieved):
            return {"score": 1.0}

    monkeypatch.setattr(eval_cli, "LLMJudge", Judge)
    monkeypatch.setattr(eval_cli, "get_model", lambda spec, settings: None)
    monkeypatch.setattr("sys.argv", ["research-eval", "--dataset", str(data), "--persist"])
    eval_cli.main()
    threads = [c.thread_id for c in offline_cli]
    assert len(set(threads)) == 2 and sorted(locks) == sorted(threads)


def test_cli_user_global_is_rejected_exit_2(offline_cli, monkeypatch, capsys):
    from research_agent import cli

    monkeypatch.setattr("sys.argv", ["research", "q", "--user", "global"])
    with pytest.raises(SystemExit) as exc:
        cli.main()
    assert exc.value.code == 2
    err = capsys.readouterr().err
    errors = [line for line in err.splitlines() if "error" in line]
    assert len(errors) == 1 and "--user" in errors[0] and "reserved" in errors[0]
    assert "Traceback" not in err and offline_cli == []


def _eval_main(monkeypatch, tmp_path, *args):
    from research_agent import eval_cli

    data = tmp_path / "d.jsonl"
    data.write_text('{"id": "a", "question": "a", "must_cover": ["x"]}\n')

    class Judge:
        def __init__(self, model):
            pass

        async def __call__(self, case, report, retrieved):
            return {"score": 1.0}

    monkeypatch.setattr(eval_cli, "LLMJudge", Judge)
    monkeypatch.setattr(eval_cli, "get_model", lambda spec, settings: None)
    monkeypatch.setattr("sys.argv", ["research-eval", "--dataset", str(data), *args])
    eval_cli.main()


def test_eval_persist_runs_each_invocation_as_a_fresh_user(
    fake_persistence, offline_cli, monkeypatch, tmp_path, capsys
):
    """Ruling P9: earlier /memories/ must not leak into eval prompts."""
    import re

    _eval_main(monkeypatch, tmp_path, "--persist")
    _eval_main(monkeypatch, tmp_path, "--persist")
    first, second = (c.user_id for c in offline_cli)
    assert first != second
    assert all(re.fullmatch(r"eval-[0-9a-f]{8}", u) for u in (first, second))
    out = capsys.readouterr().out
    assert out.count(f"eval user: {first}") == 1 and out.count(f"eval user: {second}") == 1


def test_eval_persist_honours_an_explicit_user(
    fake_persistence, offline_cli, monkeypatch, tmp_path
):
    _eval_main(monkeypatch, tmp_path, "--persist", "--user", "e1")
    assert [c.user_id for c in offline_cli] == ["e1"]


def test_eval_without_persist_keeps_the_local_default(offline_cli, monkeypatch, tmp_path):
    _eval_main(monkeypatch, tmp_path)
    assert [c.user_id for c in offline_cli] == ["local"]


def test_cli_runs_with_the_telemetry_run_config_and_prints_usage(offline_cli, monkeypatch, capsys):
    from research_agent import cli

    configs: list = []

    async def fake_run(agent, inputs, config, *, context, **kw):
        configs.append(config)
        offline_cli.append(context)
        return {"files": {"/report.md": "# r"}}

    monkeypatch.setattr(cli, "run_with_progress", fake_run)
    monkeypatch.setattr("sys.argv", ["research", "q", "--user", "u1"])
    cli.main()
    (config,) = configs
    thread = offline_cli[0].thread_id
    md = config["metadata"]
    assert (md["tenant"], md["user_id"], md["thread_id"]) == ("default", "u1", thread)
    assert md["langfuse_session_id"] == thread and "prompt_hash" in md
    assert config["configurable"] == {"thread_id": thread}
    assert any(isinstance(cb, CostLedger) for cb in config["callbacks"])
    lines = capsys.readouterr().out.splitlines()
    assert lines[-2].startswith("usage: ") and lines[-1] == "wrote report.md"


def test_cli_persist_creates_the_usage_table_and_writes_through_persistence(
    fake_persistence, offline_cli, monkeypatch
):
    from research_agent import cli, telemetry

    created: list = []

    async def ledger(p):
        created.append(p)
        return CostLedger(p)

    monkeypatch.setattr(telemetry, "persistent_ledger", ledger)
    monkeypatch.setattr(cli, "resumed_step", _no_step)
    monkeypatch.setattr("sys.argv", ["research", "q", "--persist"])
    cli.main()
    assert created == [fake_persistence[0]]


def test_eval_json_holds_run_id_trace_id_and_usage_per_case(offline_cli, monkeypatch, tmp_path):
    import json
    import uuid

    _eval_main(monkeypatch, tmp_path)
    summary = json.loads((tmp_path / "eval_results.json").read_text())
    (case,) = summary["cases"]
    assert case["case_id"] == "a" and set(case) >= {"run_id", "trace_id", "usage"}
    uuid.UUID(case["run_id"])
    assert case["trace_id"] is None  # tracing off: no OTEL_EXPORTER_OTLP_ENDPOINT


def test_eval_checks_the_tenant_up_front_without_persist(
    offline_cli, monkeypatch, tmp_path, capsys
):
    """A wrong tenant fails before any case runs, persisted or not."""
    with pytest.raises(SystemExit) as exc:
        _eval_main(monkeypatch, tmp_path, "--tenant", "other")
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "run tenant 'other' != deployment tenant 'default'" in err and "Traceback" not in err
    assert offline_cli == [] and not (tmp_path / "eval_results.md").exists()


def test_shipped_agent_has_standard_stack():
    from agentkit_config.resolve import resolve_agent
    from agentkit_config.spec import parse_agent

    s = Settings(_env_file=None, openai_api_key="o", anthropic_api_key="a", fireworks_api_key="f")
    kw = resolve_agent(
        parse_agent(DEFAULT_AGENT),
        lib(),
        ModelRegistry.default(),
        s,
        model=scripted(AIMessage(content="x")),
    )
    names = [type(m).__name__ for m in kw["middleware"]]
    assert names == [
        "SelectionMiddleware",
        "ModelFallbackMiddleware",
        "ModelRetryMiddleware",
        "RequireOutputMiddleware",
        "ModelCallLimitMiddleware",
        "ToolCallLimitMiddleware",
        "ToolCallLimitMiddleware",
        "PIIMiddleware",
        "PIIMiddleware",
    ]
    (sub,) = kw["subagents"]
    # YAML lists call_limit before model_retry; canonical order puts retry first
    assert [type(m).__name__ for m in sub["middleware"]] == [
        "ModelRetryMiddleware",
        "ModelCallLimitMiddleware",
        "ToolCallLimitMiddleware",
    ]


@pytest.fixture
def gate_env(offline_cli, monkeypatch, tmp_path):
    """Offline eval with a fixed-score judge, a 2-case dataset and a gates file."""
    import json as _json

    from research_agent import eval_cli

    data = tmp_path / "d.jsonl"
    data.write_text(
        "".join(f'{{"id": "{q}", "question": "{q}", "must_cover": ["x"]}}\n' for q in "ab")
    )
    gates = tmp_path / "gates.yaml"
    gates.write_text(
        "baseline: base.json\nmin_cases: 2\nmetrics:\n"
        "  score: {min: 0.5, max_drop: 0.1}\n  completed: {min: 1.0}\n"
    )

    class Judge:
        def __init__(self, model):
            pass

        async def __call__(self, case, report, retrieved):
            return {"score": 0.8}

    monkeypatch.setattr(eval_cli, "LLMJudge", Judge)
    monkeypatch.setattr(eval_cli, "get_model", lambda spec, settings: None)

    def run(*extra):
        monkeypatch.setattr(
            "sys.argv",
            ["research-eval", "--dataset", str(data), "--user", "e1", "--gate", str(gates), *extra],
        )
        try:
            eval_cli.main()
        except SystemExit as e:
            return e.code
        return 0

    def baseline(**over):
        b = _json.loads((tmp_path / "base.json").read_text())
        b.update(over)
        (tmp_path / "base.json").write_text(_json.dumps(b))

    return run, baseline, tmp_path


def test_eval_write_baseline_then_gate_passes(gate_env, capsys):
    run, _, tmp = gate_env
    assert run("--write-baseline") == 0
    assert f"gate: baseline written to {tmp / 'base.json'}" in capsys.readouterr().out
    assert run() == 0
    assert "gate: PASS" in capsys.readouterr().out


def test_eval_gate_pass_exits_0(gate_env, capsys):
    run, _, _ = gate_env
    run("--write-baseline")
    capsys.readouterr()
    assert run() == 0
    out = capsys.readouterr().out
    assert out.index("| **mean**") < out.index("gate: PASS")


def test_eval_gate_regression_exits_1_and_names_metric(gate_env, capsys):
    run, baseline, tmp = gate_env
    run("--write-baseline")
    import json

    agg = json.loads((tmp / "base.json").read_text())["aggregate"]
    baseline(aggregate={**agg, "score": 0.99})
    capsys.readouterr()
    assert run() == 1
    captured = capsys.readouterr()
    assert "gate: FAIL score:" in captured.err and "gate: FAIL" not in captured.out


def test_eval_gate_mismatch_exits_2(gate_env, capsys):
    run, baseline, _ = gate_env
    run("--write-baseline")
    baseline(model_id="other-model")
    capsys.readouterr()
    assert run() == 2
    captured = capsys.readouterr()
    assert "gate: baseline mismatch:" in captured.err and "mismatch" not in captured.out


def test_eval_gate_corrupt_baseline_exits_2(gate_env, capsys):
    run, _, tmp = gate_env
    (tmp / "base.json").write_text("{not json")
    assert run() == 2
    err = capsys.readouterr().err
    assert f"gate: unreadable baseline {tmp / 'base.json'}" in err and "Traceback" not in err


def test_eval_gate_missing_baseline_exits_2(gate_env, capsys):
    run, _, _ = gate_env
    assert run() == 2
    assert "run with --write-baseline first" in capsys.readouterr().err


def test_eval_write_baseline_requires_gate(offline_cli, monkeypatch, capsys):
    from research_agent import eval_cli

    monkeypatch.setattr("sys.argv", ["research-eval", "--write-baseline"])
    with pytest.raises(SystemExit) as exc:
        eval_cli.main()
    assert exc.value.code == 2 and "--gate" in capsys.readouterr().err


def test_eval_write_baseline_refuses_errored_case(gate_env, monkeypatch, capsys):
    from research_agent import eval_cli

    run, _, tmp = gate_env

    async def boom(agent, inputs, config, *, context, **kw):
        raise RuntimeError("nope")

    monkeypatch.setattr(eval_cli, "run_with_progress", boom)
    assert run("--write-baseline") == 2
    assert not (tmp / "base.json").exists()
    assert "errored" in capsys.readouterr().err


@pytest.fixture
def subset_env(offline_cli, monkeypatch, tmp_path):
    """Offline eval over a 3-case tagged dataset; returns run(*argv) -> exit code."""
    from research_agent import eval_cli

    data = tmp_path / "d.jsonl"
    data.write_text(
        '{"id": "a", "question": "a", "must_cover": ["x"], "tags": ["t1"]}\n'
        '{"id": "b", "question": "b", "must_cover": ["x"], "tags": ["t2"]}\n'
        '{"id": "c", "question": "c", "must_cover": ["x"], "tags": ["t2"]}\n'
    )

    class Judge:
        def __init__(self, model):
            pass

        async def __call__(self, case, report, retrieved):
            return {"score": 1.0}

    monkeypatch.setattr(eval_cli, "LLMJudge", Judge)
    monkeypatch.setattr(eval_cli, "get_model", lambda spec, settings: None)

    def run(*extra):
        monkeypatch.setattr(
            "sys.argv", ["research-eval", "--dataset", str(data), "--user", "e1", *extra]
        )
        try:
            eval_cli.main()
        except SystemExit as e:
            return e.code
        return 0

    return run, tmp_path


def test_eval_case_and_tag_run_only_the_subset(subset_env, offline_cli):
    import json

    run, tmp = subset_env
    assert run("--case", "a", "--tag", "t2") == 0
    assert len(offline_cli) == 3
    offline_cli.clear()
    assert run("--tag", "t2") == 0
    summary = json.loads((tmp / "eval_results.json").read_text())
    assert [c["case_id"] for c in summary["cases"]] == ["b", "c"]
    assert summary["subset"] == {"cases": [], "tags": ["t2"]}
    assert len(offline_cli) == 2


def test_eval_unknown_case_exits_2_naming_it(subset_env, offline_cli, capsys):
    run, _ = subset_env
    assert run("--case", "zzz") == 2
    assert "zzz" in capsys.readouterr().err and offline_cli == []


def test_eval_subset_with_gate_is_rejected(subset_env, tmp_path, capsys):
    run, _ = subset_env
    assert run("--tag", "t1", "--gate", str(tmp_path / "g.yaml")) == 2
    assert "--gate" in capsys.readouterr().err


@pytest.mark.parametrize("bad", ["0", "-1", "x"])
def test_eval_concurrency_must_be_positive(subset_env, bad, capsys):
    run, _ = subset_env
    assert run("--concurrency", bad) == 2
    assert "--concurrency" in capsys.readouterr().err


def test_eval_concurrency_reaches_run_eval(subset_env, monkeypatch):
    from research_agent import eval_cli

    seen = {}
    real = eval_cli.run_eval

    async def spy(cases, run_agent, judge, concurrency=2):
        seen["concurrency"] = concurrency
        return await real(cases, run_agent, judge, concurrency=concurrency)

    monkeypatch.setattr(eval_cli, "run_eval", spy)
    run, _ = subset_env
    assert run() == 0 and seen["concurrency"] == 6
    assert run("--concurrency", "3") == 0 and seen["concurrency"] == 3
