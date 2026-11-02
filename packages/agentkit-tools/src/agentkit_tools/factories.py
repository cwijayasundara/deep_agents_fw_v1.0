from __future__ import annotations

from typing import Literal

from agentkit_core import BuildContext, ConfigError
from langchain_core.tools import BaseTool

from .duckduckgo import DuckDuckGoSearch
from .fetch import HttpFetch
from .langchain_tools import make_fetch_tool, make_web_search_tool
from .models import SearchTool
from .tavily import TavilySearch

BACKENDS = ("tavily", "duckduckgo")


def web_search(
    ctx: BuildContext, *, backend: Literal["tavily", "duckduckgo"] = "duckduckgo"
) -> BaseTool:
    """Web search tool. DuckDuckGo (no key) is the default; `backend: tavily` needs a key."""
    search: SearchTool
    if backend == "tavily":
        key = ctx.settings.tavily_api_key
        if key is None:
            raise ConfigError("TAVILY_API_KEY is required for the web search tool")
        search = TavilySearch(key.get_secret_value())
    elif backend == "duckduckgo":
        search = DuckDuckGoSearch()
    else:
        raise ConfigError(f"unknown web_search backend {backend!r}; expected one of {BACKENDS}")
    return make_web_search_tool(search)


def fetch_url(ctx: BuildContext, *, max_chars: int = 20_000) -> BaseTool:
    return make_fetch_tool(HttpFetch(max_chars=max_chars))
