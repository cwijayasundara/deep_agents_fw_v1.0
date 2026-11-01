from pathlib import Path

import pytest
from agentkit_core import ModelRegistry, Settings
from agentkit_deep.testing import scripted, tool_call
from agentkit_tools import Page, Source
from langchain_core.messages import AIMessage, HumanMessage
from research_agent import build_research_agent, extract_report, load_config

CONFIGS = sorted(Path(__file__).parents[1].glob("config/*.yaml"))


class FakeSearch:
    async def search(self, query, k=5):
        return [Source("https://a.example/x", "A", "fact about x")]


class FakeFetch:
    async def fetch(self, url):
        return Page(url, "A", "body")


def test_every_config_resolves_to_a_registry_entry():
    assert len(CONFIGS) == 6
    reg = ModelRegistry.default()
    for c in CONFIGS:
        cfg = load_config(c)
        assert reg.resolve(cfg["model"], cfg["tier"])


def test_bad_config_rejected(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("tier: fast\n")
    with pytest.raises(ValueError, match="model"):
        load_config(p)


async def test_end_to_end_report_with_citation():
    report = "# R\nX is true [1]\n\n## Sources\n[1] https://a.example/x"
    model = scripted(
        tool_call("web_search", {"query": "x"}, "1"),
        tool_call("write_file", {"file_path": "/report.md", "content": report}, "2"),
        AIMessage(content="done"),
    )
    agent = build_research_agent(
        {"model": "anthropic", "tier": "default"},
        Settings(_env_file=None),
        search=FakeSearch(),
        fetch=FakeFetch(),
        model=model,
    )
    out = await agent.ainvoke({"messages": [HumanMessage("what is x?")]})
    text = extract_report(out)
    assert "https://a.example/x" in text and "[1]" in text
    tool_msgs = [m.content for m in out["messages"] if m.type == "tool"]
    assert any("https://a.example/x" in str(c) for c in tool_msgs)  # citation was retrieved
