import json

import httpx
import pytest
import respx
from agentkit_tools import (
    BraveSearch,
    CachedSearch,
    FallbackSearch,
    ParallelSearch,
    Source,
    ToolError,
    make_web_search_tool,
)


@respx.mock
async def test_parallel_search_request_and_mapping():
    route = respx.post("https://api.parallel.ai/v1/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "search_id": "s",
                "session_id": "x",
                "results": [
                    {"url": "https://a.com", "title": "A", "excerpts": ["one", "two"]},
                    {"url": "https://b.com", "title": None, "excerpts": []},
                ],
            },
        )
    )
    out = await ParallelSearch("pk").search("rag vs fine-tuning", 2)
    assert out == [Source("https://a.com", "A", "one\ntwo"), Source("https://b.com", "", "")]
    req = route.calls[0].request
    assert req.headers["x-api-key"] == "pk"
    body = json.loads(req.content)
    assert body["search_queries"] == ["rag vs fine-tuning"]
    assert body["mode"] == "fast"
    assert body["advanced_settings"]["max_results"] == 2


@respx.mock
async def test_parallel_http_error_hides_key():
    respx.post("https://api.parallel.ai/v1/search").mock(return_value=httpx.Response(429))
    with pytest.raises(ToolError, match="HTTP 429") as ei:
        await ParallelSearch("secret-key").search("q")
    assert "secret-key" not in str(ei.value)


@respx.mock
async def test_brave_search_request_and_mapping():
    route = respx.get("https://api.search.brave.com/res/v1/web/search").mock(
        return_value=httpx.Response(
            200,
            json={"web": {"results": [{"url": "https://a.com", "title": "A", "description": "d"}]}},
        )
    )
    assert await BraveSearch("bk").search("q", 3) == [Source("https://a.com", "A", "d")]
    req = route.calls[0].request
    assert req.headers["x-subscription-token"] == "bk"
    assert req.url.params["q"] == "q" and req.url.params["count"] == "3"


@respx.mock
async def test_brave_no_web_block_is_empty():
    respx.get("https://api.search.brave.com/res/v1/web/search").mock(
        return_value=httpx.Response(200, json={"query": {"original": "q"}})
    )
    assert await BraveSearch("bk").search("q") == []


@respx.mock
async def test_brave_timeout_becomes_tool_error():
    respx.get("https://api.search.brave.com/res/v1/web/search").mock(
        side_effect=httpx.ReadTimeout("t")
    )
    with pytest.raises(ToolError, match="ReadTimeout"):
        await BraveSearch("bk").search("q")


class _Fake:
    def __init__(self, result=None, error=None):
        self.calls = 0
        self._result, self._error = result or [], error

    async def search(self, query, k=5):
        self.calls += 1
        if self._error:
            raise ToolError(self._error)
        return self._result


async def test_fallback_uses_next_backend_on_tool_error():
    a, b = _Fake(error="search failed: HTTP 429"), _Fake([Source("u", "t", "s")])
    assert await FallbackSearch([("a", a), ("b", b)]).search("q") == [Source("u", "t", "s")]
    assert (a.calls, b.calls) == (1, 1)


async def test_fallback_stops_at_first_success_even_if_empty():
    a, b = _Fake([]), _Fake([Source("u", "t", "s")])
    assert await FallbackSearch([("a", a), ("b", b)]).search("q") == []
    assert b.calls == 0


async def test_fallback_all_failed_names_each_backend():
    chain = FallbackSearch([("a", _Fake(error="x")), ("b", _Fake(error="y"))])
    with pytest.raises(ToolError, match="a: x; b: y"):
        await chain.search("q")
    tool = make_web_search_tool(chain)
    assert (await tool.ainvoke({"query": "q"})).startswith("ERROR: a: x")


async def test_cache_reuses_results_for_same_normalised_query():
    inner = _Fake([Source("u", "t", "s")])
    cache = CachedSearch(inner)
    await cache.search("RAG  vs Fine-tuning", 5)
    await cache.search("rag vs fine-tuning", 5)
    assert inner.calls == 1
    await cache.search("rag vs fine-tuning", 3)
    assert inner.calls == 2


async def test_cache_does_not_store_errors_and_evicts_oldest():
    failing = _Fake(error="boom")
    cache = CachedSearch(failing)
    for _ in range(2):
        with pytest.raises(ToolError):
            await cache.search("q")
    assert failing.calls == 2

    inner = _Fake([Source("u", "t", "s")])
    small = CachedSearch(inner, max_entries=1)
    await small.search("a")
    await small.search("b")
    await small.search("a")
    assert inner.calls == 3


class _Status:
    def __init__(self, status):
        self.calls, self._status = 0, status

    async def search(self, query, k=5):
        self.calls += 1
        raise ToolError(f"search failed: HTTP {self._status}", status=self._status)


async def test_fallback_skips_backend_after_quota_error():
    dead, ok = _Status(432), _Fake([Source("u", "t", "s")])
    chain = FallbackSearch([("tavily", dead), ("duckduckgo", ok)])
    await chain.search("a")
    await chain.search("b")
    assert (dead.calls, ok.calls) == (1, 2)


async def test_fallback_keeps_retrying_after_transient_error():
    flaky, ok = _Status(429), _Fake([Source("u", "t", "s")])
    chain = FallbackSearch([("brave", flaky), ("duckduckgo", ok)])
    await chain.search("a")
    await chain.search("b")
    assert flaky.calls == 2


async def test_fallback_keeps_last_backend_even_if_dead():
    a, b = _Status(401), _Status(403)
    chain = FallbackSearch([("a", a), ("b", b)])
    for q in ("x", "y"):
        with pytest.raises(ToolError):
            await chain.search(q)
    assert (a.calls, b.calls) == (1, 2)


@respx.mock
async def test_http_status_is_carried_on_tool_error():
    respx.post("https://api.parallel.ai/v1/search").mock(return_value=httpx.Response(403))
    with pytest.raises(ToolError) as ei:
        await ParallelSearch("k").search("q")
    assert ei.value.status == 403
