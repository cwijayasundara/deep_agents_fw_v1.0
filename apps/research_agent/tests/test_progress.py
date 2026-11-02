import logging

from agentkit_config import CodePools, Library, load_agent, read_output
from agentkit_core import Settings
from agentkit_deep.testing import ctx, scripted, tool_call
from agentkit_tools import Page, Source, make_fetch_tool, make_web_search_tool
from langchain_core.messages import AIMessage, HumanMessage
from research_agent import DEFAULT_AGENT
from research_agent.progress import run_with_progress


class FakeSearch:
    async def search(self, query, k=5):
        return [Source("https://a.example/x", "A", "fact")]


class FakeFetch:
    async def fetch(self, url):
        return Page(url, "A", "body")


def build_agent(model):
    pools = CodePools.from_entry_points().override(
        tools={
            "web_search": lambda ctx, **kw: make_web_search_tool(FakeSearch()),
            "fetch_url": lambda ctx, **kw: make_fetch_tool(FakeFetch()),
        }
    )
    return load_agent(
        DEFAULT_AGENT,
        settings=Settings(_env_file=None),
        library=Library.for_file(DEFAULT_AGENT, pools),
        overrides={"model": "anthropic", "selection": "off"},
        model=model,
    )


async def test_run_with_progress_logs_steps_and_returns_final_state(caplog):
    model = scripted(
        tool_call("task", {"description": "look up x", "subagent_type": "researcher"}, "0"),
        tool_call("web_search", {"query": "x"}, "1"),
        AIMessage(content="found x"),
        tool_call("write_file", {"file_path": "/report.md", "content": "# R [1]"}, "2"),
        AIMessage(content="done"),
    )
    loaded = build_agent(model)
    agent = loaded.graph
    with caplog.at_level(logging.INFO, logger="research_agent"):
        out = await run_with_progress(
            agent, {"messages": [HumanMessage("what is x?")]}, context=ctx()
        )
    assert read_output(out, loaded.spec.output) == "# R [1]"
    text = caplog.text
    assert "orchestrator -> delegate to researcher: look up x" in text
    assert "subagent[1] -> web_search 'x'" in text
    assert "subagent[1] <- web_search ok" in text
    assert "orchestrator -> write_file /report.md" in text
    assert "agent finished in" in text


async def test_run_with_progress_collects_subagent_tool_outputs():
    model = scripted(
        tool_call("task", {"description": "look up x", "subagent_type": "researcher"}, "0"),
        tool_call("web_search", {"query": "x"}, "1"),
        AIMessage(content="found x"),
        AIMessage(content="done"),
    )
    loaded = build_agent(model)
    agent = loaded.graph
    outputs: list[str] = []
    await run_with_progress(
        agent, {"messages": [HumanMessage("q")]}, context=ctx(), tool_outputs=outputs
    )
    # the search result was seen only inside the researcher subagent
    assert any("https://a.example/x" in o and "fact" in o for o in outputs)


async def test_run_with_progress_collects_tool_call_names_from_subagents():
    model = scripted(
        tool_call("task", {"description": "look up x", "subagent_type": "researcher"}, "0"),
        tool_call("web_search", {"query": "x"}, "1"),
        AIMessage(content="found x"),
        AIMessage(content="done"),
    )
    loaded = build_agent(model)
    calls: list[str] = []
    await run_with_progress(
        loaded.graph, {"messages": [HumanMessage("q")]}, context=ctx(), tool_calls=calls
    )
    assert calls == ["task", "web_search"]
