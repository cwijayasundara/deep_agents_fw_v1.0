import logging

from agentkit_core import Settings
from agentkit_deep.testing import scripted, tool_call
from agentkit_tools import Page, Source
from langchain_core.messages import AIMessage, HumanMessage
from research_agent import build_research_agent, extract_report
from research_agent.progress import run_with_progress


class FakeSearch:
    async def search(self, query, k=5):
        return [Source("https://a.example/x", "A", "fact")]


class FakeFetch:
    async def fetch(self, url):
        return Page(url, "A", "body")


async def test_run_with_progress_logs_steps_and_returns_final_state(caplog):
    model = scripted(
        tool_call("task", {"description": "look up x", "subagent_type": "researcher"}, "0"),
        tool_call("web_search", {"query": "x"}, "1"),
        AIMessage(content="found x"),
        tool_call("write_file", {"file_path": "/report.md", "content": "# R [1]"}, "2"),
        AIMessage(content="done"),
    )
    agent = build_research_agent(
        {"model": "anthropic", "tier": "default"},
        Settings(_env_file=None),
        search=FakeSearch(),
        fetch=FakeFetch(),
        model=model,
    )
    with caplog.at_level(logging.INFO, logger="research_agent"):
        out = await run_with_progress(agent, {"messages": [HumanMessage("what is x?")]})
    assert extract_report(out) == "# R [1]"
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
    agent = build_research_agent(
        {"model": "anthropic", "tier": "default"},
        Settings(_env_file=None),
        search=FakeSearch(),
        fetch=FakeFetch(),
        model=model,
    )
    outputs: list[str] = []
    await run_with_progress(agent, {"messages": [HumanMessage("q")]}, tool_outputs=outputs)
    # the search result was seen only inside the researcher subagent
    assert any("https://a.example/x" in o and "fact" in o for o in outputs)
