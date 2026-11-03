from __future__ import annotations

import logging
from collections.abc import Sequence

from agentkit_core import BuildContext, ConfigError
from agentkit_core.seams import Seam
from langchain_core.tools import BaseTool

from .backends import api_key
from .chain import CachedSearch, FallbackSearch
from .fetch import HttpFetch
from .langchain_tools import make_fetch_tool, make_web_search_tool
from .models import SearchTool
from .platform import platform_tool

log = logging.getLogger(__name__)

SEARCH_BACKENDS: Seam[SearchTool] = Seam("agentkit.search_backends", "web_search backend")
# `auto`: each built-in whose key is set, in this order, then keyless DuckDuckGo as last resort.
# Third-party providers are reachable by name only.
AUTO_ORDER: tuple[str, ...] = ("parallel", "brave", "tavily")


def _key(ctx: BuildContext, name: str) -> str | None:
    return api_key(ctx.settings, name)


def _backend(ctx: BuildContext, name: str) -> SearchTool:
    return SEARCH_BACKENDS.get(name, ctx.settings.deployment_tenant)(ctx.settings)


def _names(ctx: BuildContext, backend: str | Sequence[str]) -> list[str]:
    if backend == "auto":
        names = [n for n in AUTO_ORDER if _key(ctx, n)]
        if not names:
            log.warning("web_search: no search API key set; using DuckDuckGo only (unreliable)")
        return [*names, "duckduckgo"]
    if isinstance(backend, str):
        names = [backend]
    elif isinstance(backend, list | tuple) and all(isinstance(n, str) for n in backend):
        names = list(backend)
    else:
        raise ConfigError(f"web_search backend must be a name or a list of names, got {backend!r}")
    if not names:
        raise ConfigError("web_search backend list is empty")
    if len(set(names)) != len(names):
        raise ConfigError(f"web_search backend list has duplicates: {names}")
    return names


@platform_tool(owner="platform", version="1.1.0", side_effects="external", classification="public")
def web_search(ctx: BuildContext, *, backend: str | list[str] = "auto") -> BaseTool:
    """Web search tool.

    `backend: auto` (default) uses every search key that is set (Parallel, then Brave, then
    Tavily) and falls back to keyless DuckDuckGo. A name uses that backend only; a list tries
    them in order. A named backend whose key is missing is a `ConfigError` at build.
    Repeated queries are served from a per-tool cache.
    """
    names = _names(ctx, backend)
    backends = [(n, _backend(ctx, n)) for n in names]
    search: SearchTool = backends[0][1] if len(backends) == 1 else FallbackSearch(backends)
    return make_web_search_tool(CachedSearch(search))


@platform_tool(owner="platform", version="1.0.0", side_effects="external", classification="public")
def fetch_url(ctx: BuildContext, *, max_chars: int = 20_000) -> BaseTool:
    return make_fetch_tool(HttpFetch(max_chars=max_chars))
