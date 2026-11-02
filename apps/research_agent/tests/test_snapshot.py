import json
import os
from pathlib import Path

import research_agent.agent as agent_mod
from agentkit_core import Settings
from agentkit_deep.testing import describe_build
from agentkit_tools import Page, Source
from research_agent import build_research_agent

FIXTURE = Path(__file__).parent / "fixtures" / "python_build_snapshot.json"


class FakeSearch:
    async def search(self, query, k=5):
        return [Source("https://a.example/x", "A", "fact about x")]


class FakeFetch:
    async def fetch(self, url):
        return Page(url, "A", "body")


def test_python_build_matches_snapshot(monkeypatch):
    recorded: dict = {}

    def recorder(**kwargs):
        recorded.update(kwargs)
        return object()

    monkeypatch.setattr(agent_mod, "build_deep_agent", recorder)
    build_research_agent(
        {"model": "anthropic", "tier": "default", "selection": "decisions"},
        Settings(_env_file=None, tavily_api_key="t", openai_api_key="o", anthropic_api_key="a"),
        search=FakeSearch(),
        fetch=FakeFetch(),
    )
    actual = describe_build(recorded)
    if os.environ.get("UPDATE_SNAPSHOT") == "1":
        FIXTURE.write_text(json.dumps(actual, sort_keys=True, indent=2) + "\n")
    assert actual == json.loads(FIXTURE.read_text())
