from __future__ import annotations

import logging

from langchain_core.tools import BaseTool, StructuredTool

from .models import FetchTool, SearchTool, ToolError

log = logging.getLogger(__name__)


def make_web_search_tool(search: SearchTool) -> BaseTool:
    """Read-only LangChain search tool. Errors are returned as text so the agent can recover."""

    async def web_search(query: str, k: int = 5) -> str:
        """Search the web. Returns numbered results with URL, title and snippet."""
        try:
            results = await search.search(query, k)
        except ToolError as e:
            log.warning("web_search %r failed: %s", query, e)
            return f"ERROR: {e}"
        if not results:
            return "No results."
        return "\n\n".join(
            f"[{i}] {s.title}\n{s.url}\n{s.snippet}" for i, s in enumerate(results, 1)
        )

    return StructuredTool.from_function(coroutine=web_search, name="web_search")


def make_fetch_tool(fetch: FetchTool) -> BaseTool:
    """Read-only LangChain fetch tool. Errors are returned as text so the agent can recover."""

    async def fetch_url(url: str) -> str:
        """Fetch a web page and return its readable text (truncated if long)."""
        try:
            page = await fetch.fetch(url)
        except ToolError as e:
            log.warning("fetch_url %s failed: %s", url, e)
            return f"ERROR: {e}"
        note = "\n[truncated]" if page.truncated else ""
        return f"{page.title}\n{page.url}\n\n{page.text}{note}"

    return StructuredTool.from_function(coroutine=fetch_url, name="fetch_url")
