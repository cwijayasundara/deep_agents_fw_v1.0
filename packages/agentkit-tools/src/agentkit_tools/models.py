from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Source:
    url: str
    title: str
    snippet: str


@dataclass(frozen=True)
class Page:
    url: str
    title: str
    text: str
    truncated: bool = False


class SearchTool(Protocol):
    async def search(self, query: str, k: int = 5) -> list[Source]: ...


class FetchTool(Protocol):
    async def fetch(self, url: str) -> Page: ...


class ToolError(RuntimeError):
    """Tool failed in a way the agent should see as a message, not a crash."""
