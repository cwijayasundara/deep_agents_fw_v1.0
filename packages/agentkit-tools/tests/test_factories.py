import ddgs.ddgs
import pytest
from agentkit_core import BuildContext, ConfigError, ModelRegistry, Settings
from agentkit_tools import Source, ToolError
from agentkit_tools.duckduckgo import DuckDuckGoSearch
from agentkit_tools.factories import fetch_url, web_search


def _ctx(**env: str) -> BuildContext:
    settings = Settings(_env_file=None, **env)  # type: ignore[arg-type]
    return BuildContext(settings, ModelRegistry.default().resolve(), "agent")


def test_web_search_requires_tavily_key():
    with pytest.raises(ConfigError, match="TAVILY_API_KEY is required"):
        web_search(_ctx())


def test_web_search_tavily_builds_with_key():
    assert web_search(_ctx(tavily_api_key="k")).name == "web_search"


def test_web_search_duckduckgo_needs_no_key():
    assert web_search(_ctx(), backend="duckduckgo").name == "web_search"


def test_web_search_unknown_backend():
    with pytest.raises(ConfigError, match="tavily.*duckduckgo"):
        web_search(_ctx(), backend="bing")  # type: ignore[arg-type]


async def test_duckduckgo_maps_results(monkeypatch):
    rows = [{"href": "https://a.example", "title": "A", "body": "b"}]
    monkeypatch.setattr(ddgs.ddgs.DDGS, "text", lambda self, q, max_results=5, **kw: rows)
    assert await DuckDuckGoSearch().search("q", 3) == [Source("https://a.example", "A", "b")]


async def test_duckduckgo_error_becomes_tool_error(monkeypatch):
    def boom(self, q, max_results=5, **kw):
        raise RuntimeError("rate")

    monkeypatch.setattr(ddgs.ddgs.DDGS, "text", boom)
    with pytest.raises(ToolError, match="search failed: RuntimeError"):
        await DuckDuckGoSearch().search("q")
    tool = web_search(_ctx(), backend="duckduckgo")
    assert (await tool.ainvoke({"query": "q"})).startswith("ERROR:")


def test_fetch_url_max_chars_param():
    assert fetch_url(_ctx(), max_chars=100).name == "fetch_url"
