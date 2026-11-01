import httpx
import pytest
import respx
from agentkit_tools import HttpFetch, TavilySearch, ToolError, make_research_tools


@respx.mock
async def test_tavily_search_parses_and_authenticates():
    route = respx.post("https://api.tavily.com/search").mock(
        return_value=httpx.Response(
            200, json={"results": [{"url": "https://a.com", "title": "A", "content": "aa"}]}
        )
    )
    out = await TavilySearch("k1").search("q", 3)
    assert out[0].url == "https://a.com" and out[0].snippet == "aa"
    req = route.calls[0].request
    assert req.headers["authorization"] == "Bearer k1"
    assert b'"max_results":3' in req.content.replace(b" ", b"")


@respx.mock
async def test_tavily_http_error_becomes_tool_error():
    respx.post("https://api.tavily.com/search").mock(return_value=httpx.Response(500))
    with pytest.raises(ToolError):
        await TavilySearch("k").search("q")


@respx.mock
async def test_tavily_timeout_becomes_tool_error():
    respx.post("https://api.tavily.com/search").mock(side_effect=httpx.ConnectTimeout("t"))
    with pytest.raises(ToolError):
        await TavilySearch("k").search("q")


@respx.mock
async def test_fetch_extracts_text_and_title():
    html = "<html><head><title>T</title><script>x()</script></head><body><p>Hello</p></body></html>"
    respx.get("https://e.com/p").mock(
        return_value=httpx.Response(200, text=html, headers={"content-type": "text/html"})
    )
    page = await HttpFetch().fetch("https://e.com/p")
    assert page.title == "T" and page.text == "Hello" and not page.truncated


@respx.mock
async def test_fetch_truncates_oversize():
    respx.get("https://e.com/big").mock(
        return_value=httpx.Response(200, text="x" * 5000, headers={"content-type": "text/plain"})
    )
    page = await HttpFetch(max_bytes=1000, max_chars=500).fetch("https://e.com/big")
    assert page.truncated and len(page.text) == 500


@pytest.mark.parametrize(
    "url", ["file:///etc/passwd", "http://localhost/x", "http://127.0.0.1/", "http://10.0.0.5/"]
)
async def test_fetch_blocks_unsafe_urls(url):
    with pytest.raises(ToolError):
        await HttpFetch().fetch(url)


@respx.mock
async def test_langchain_tools_return_errors_as_text():
    respx.post("https://api.tavily.com/search").mock(return_value=httpx.Response(500))
    search_tool, fetch_tool = make_research_tools(TavilySearch("k"), HttpFetch())
    assert (await search_tool.ainvoke({"query": "q"})).startswith("ERROR")
    assert (await fetch_tool.ainvoke({"url": "http://localhost/"})).startswith("ERROR")
