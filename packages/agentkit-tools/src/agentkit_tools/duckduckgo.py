from __future__ import annotations

import asyncio

from ddgs import DDGS

from .models import Source, ToolError


class DuckDuckGoSearch:
    """Keyless search backend via the `ddgs` package."""

    async def search(self, query: str, k: int = 5) -> list[Source]:
        try:
            rows = await asyncio.to_thread(lambda: DDGS().text(query, max_results=k))
        except Exception as e:
            raise ToolError(f"search failed: {type(e).__name__}") from e
        return [
            Source(url=r.get("href", ""), title=r.get("title", ""), snippet=r.get("body", ""))
            for r in rows
        ][:k]
