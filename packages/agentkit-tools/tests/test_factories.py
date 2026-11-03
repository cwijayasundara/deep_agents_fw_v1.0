import ddgs.ddgs
import ddgs.exceptions
import pytest
from agentkit_core import BuildContext, ConfigError, ModelRegistry, Settings
from agentkit_tools import Source, ToolError
from agentkit_tools.duckduckgo import DuckDuckGoSearch
from agentkit_tools.factories import _names, fetch_url, web_search


def _ctx(**env: str) -> BuildContext:
    settings = Settings(_env_file=None, **env)  # type: ignore[arg-type]
    return BuildContext(settings, ModelRegistry.default().resolve(), "agent")


def test_web_search_auto_without_keys_falls_back_to_duckduckgo():
    # `auto` still builds with no key: keyless DuckDuckGo is the last resort.
    assert _names(_ctx(), "auto") == ["duckduckgo"]
    assert web_search(_ctx()).name == "web_search"


def test_web_search_auto_orders_keyed_backends_first():
    ctx = _ctx(tavily_api_key="t", brave_api_key="b", parallel_api_key="p")
    assert _names(ctx, "auto") == ["parallel", "brave", "tavily", "duckduckgo"]
    assert _names(_ctx(brave_api_key="b"), "auto") == ["brave", "duckduckgo"]


def test_web_search_empty_key_counts_as_unset():
    assert _names(_ctx(parallel_api_key=""), "auto") == ["duckduckgo"]


@pytest.mark.parametrize(("backend", "env"), [("parallel", "PARALLEL"), ("brave", "BRAVE")])
def test_web_search_named_backend_requires_key(backend, env):
    with pytest.raises(ConfigError, match=f"{env}_API_KEY is required"):
        web_search(_ctx(), backend=backend)
    assert web_search(_ctx(**{f"{backend}_api_key": "k"}), backend=backend).name == "web_search"


def test_web_search_backend_list():
    ctx = _ctx(parallel_api_key="p")
    assert web_search(ctx, backend=["parallel", "duckduckgo"]).name == "web_search"
    with pytest.raises(ConfigError, match="BRAVE_API_KEY is required"):
        web_search(ctx, backend=["parallel", "brave"])
    with pytest.raises(ConfigError, match="empty"):
        web_search(ctx, backend=[])
    with pytest.raises(ConfigError, match="duplicates"):
        web_search(ctx, backend=["duckduckgo", "duckduckgo"])
    with pytest.raises(ConfigError, match="name or a list"):
        web_search(ctx, backend=5)  # type: ignore[arg-type]


def test_web_search_tavily_requires_key():
    with pytest.raises(ConfigError, match="TAVILY_API_KEY is required"):
        web_search(_ctx(), backend="tavily")


def test_web_search_tavily_builds_with_key():
    assert web_search(_ctx(tavily_api_key="k"), backend="tavily").name == "web_search"


def test_web_search_duckduckgo_needs_no_key():
    assert web_search(_ctx(), backend="duckduckgo").name == "web_search"


def test_web_search_unknown_backend():
    with pytest.raises(ConfigError, match="parallel.*brave.*tavily.*duckduckgo"):
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


async def test_duckduckgo_no_results_is_empty_not_error(monkeypatch):
    def none_found(self, q, max_results=5, **kw):
        raise ddgs.ddgs.DDGSException("No results found.")

    monkeypatch.setattr(ddgs.ddgs.DDGS, "text", none_found)
    assert await DuckDuckGoSearch().search("q") == []
    tool = web_search(_ctx(), backend="duckduckgo")
    assert await tool.ainvoke({"query": "q"}) == "No results."


async def test_duckduckgo_ratelimit_is_still_an_error(monkeypatch):
    def limited(self, q, max_results=5, **kw):
        raise ddgs.exceptions.RatelimitException("No results found.")

    monkeypatch.setattr(ddgs.ddgs.DDGS, "text", limited)
    with pytest.raises(ToolError, match="RatelimitException"):
        await DuckDuckGoSearch().search("q")


def test_fetch_url_max_chars_param():
    assert fetch_url(_ctx(), max_chars=100).name == "fetch_url"
