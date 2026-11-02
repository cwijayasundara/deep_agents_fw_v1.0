import httpx
import pytest
import respx
from agentkit_tools import HttpFetch, TavilySearch, ToolError, make_fetch_tool, make_web_search_tool


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
    with pytest.raises(ToolError, match="HTTP 500") as ei:
        await TavilySearch("secret-key").search("q")
    assert "secret-key" not in str(ei.value) and "api.tavily.com" not in str(ei.value)


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


@pytest.mark.parametrize(
    "target",
    ["http://127.0.0.1/admin", "http://169.254.169.254/latest/meta-data/", "http://localhost/"],
)
@respx.mock
async def test_fetch_blocks_redirect_to_private_address(target):
    respx.get("https://e.com/r").mock(
        return_value=httpx.Response(302, headers={"location": target})
    )
    private = respx.get(target).mock(return_value=httpx.Response(200, text="secret"))
    with pytest.raises(ToolError, match="private"):
        await HttpFetch().fetch("https://e.com/r")
    assert not private.called


@respx.mock
async def test_fetch_follows_safe_relative_redirect():
    respx.get("https://e.com/old").mock(
        return_value=httpx.Response(301, headers={"location": "/new"})
    )
    respx.get("https://e.com/new").mock(
        return_value=httpx.Response(200, text="moved", headers={"content-type": "text/plain"})
    )
    page = await HttpFetch().fetch("https://e.com/old")
    assert page.text == "moved" and page.url == "https://e.com/new"


@respx.mock
async def test_fetch_caps_redirect_chain():
    respx.get("https://e.com/loop").mock(
        return_value=httpx.Response(302, headers={"location": "https://e.com/loop"})
    )
    with pytest.raises(ToolError, match="redirects"):
        await HttpFetch().fetch("https://e.com/loop")


@respx.mock
async def test_fetch_ignores_injected_client_redirect_setting():
    respx.get("https://e.com/r").mock(
        return_value=httpx.Response(302, headers={"location": "http://10.0.0.5/"})
    )
    client = httpx.AsyncClient(follow_redirects=True)
    with pytest.raises(ToolError, match="private"):
        await HttpFetch(client=client).fetch("https://e.com/r")


@respx.mock
async def test_langchain_tools_return_errors_as_text():
    respx.post("https://api.tavily.com/search").mock(return_value=httpx.Response(500))
    search_tool = make_web_search_tool(TavilySearch("k"))
    fetch_tool = make_fetch_tool(HttpFetch())
    assert (await search_tool.ainvoke({"query": "q"})).startswith("ERROR")
    assert (await fetch_tool.ainvoke({"url": "http://localhost/"})).startswith("ERROR")
