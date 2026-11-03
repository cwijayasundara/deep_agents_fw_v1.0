import json
import os
from pathlib import Path

import agentkit_config.load as load_mod
from agentkit_config import CodePools, Library, load_agent
from agentkit_core import Settings
from agentkit_deep.testing import describe_build
from agentkit_tools import Page, Source, make_fetch_tool, make_web_search_tool, platform_tool
from research_agent import DEFAULT_AGENT

FIXTURE = Path(__file__).parent / "fixtures" / "python_build_snapshot.json"


class FakeSearch:
    async def search(self, query, k=5):
        return [Source("https://a.example/x", "A", "fact about x")]


class FakeFetch:
    async def fetch(self, url):
        return Page(url, "A", "body")


def _external(factory):
    """Register a fake factory the way the real search and fetch factories are."""
    return platform_tool(owner="platform", version="1.0.0", side_effects="external")(factory)


def test_yaml_build_matches_python_snapshot(monkeypatch):
    recorded: dict = {}

    def recorder(**kwargs):
        recorded.update(kwargs)
        return object()

    monkeypatch.setattr(load_mod, "build_deep_agent", recorder)
    pools = CodePools.from_entry_points().override(
        tools={
            "web_search": _external(lambda ctx, **kw: make_web_search_tool(FakeSearch())),
            "fetch_url": _external(lambda ctx, **kw: make_fetch_tool(FakeFetch())),
        }
    )
    load_agent(
        DEFAULT_AGENT,
        settings=Settings(
            _env_file=None,
            tavily_api_key="t",
            openai_api_key="o",
            anthropic_api_key="a",
            fireworks_api_key="f",
        ),
        library=Library.for_file(DEFAULT_AGENT, pools),
        overrides={"model": "anthropic"},
    )
    actual = describe_build(recorded)
    if os.environ.get("UPDATE_SNAPSHOT") == "1":
        FIXTURE.write_text(json.dumps(actual, sort_keys=True, indent=2) + "\n")
    assert actual == json.loads(FIXTURE.read_text())
