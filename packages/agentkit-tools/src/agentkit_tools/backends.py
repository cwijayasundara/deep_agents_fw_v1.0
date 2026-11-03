"""Built-in `agentkit.search_backends` providers: one factory per search backend."""

from __future__ import annotations

from collections.abc import Callable

from agentkit_core import ConfigError, Settings
from agentkit_core.seams import provider

from .brave import BraveSearch
from .duckduckgo import DuckDuckGoSearch
from .models import SearchTool
from .parallel import ParallelSearch
from .tavily import TavilySearch

KEY_ENV = {"parallel": "PARALLEL_API_KEY", "brave": "BRAVE_API_KEY", "tavily": "TAVILY_API_KEY"}


def api_key(settings: Settings, name: str) -> str | None:
    """The configured key for a keyed backend, or None when unset or empty."""
    secret = getattr(settings, KEY_ENV[name].lower())
    if secret is None or not secret.get_secret_value():
        return None
    return str(secret.get_secret_value())


def _keyed(name: str, cls: Callable[[str], SearchTool]) -> Callable[[Settings], SearchTool]:
    @provider(owner="platform", version="1.0.0")
    def build(settings: Settings) -> SearchTool:
        key = api_key(settings, name)
        if key is None:
            raise ConfigError(f"{KEY_ENV[name]} is required for the {name} web search backend")
        return cls(key)

    build.__name__ = name
    return build


parallel = _keyed("parallel", ParallelSearch)
brave = _keyed("brave", BraveSearch)
tavily = _keyed("tavily", TavilySearch)


@provider(owner="platform", version="1.0.0")
def duckduckgo(settings: Settings) -> SearchTool:
    return DuckDuckGoSearch()
