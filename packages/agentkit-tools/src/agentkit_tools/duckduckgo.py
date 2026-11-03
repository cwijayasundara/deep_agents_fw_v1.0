from __future__ import annotations

import asyncio
import logging

from ddgs import DDGS
from ddgs.exceptions import DDGSException

from .models import Source, ToolError

log = logging.getLogger(__name__)
NO_RESULTS = "No results found."


class DuckDuckGoSearch:
    """Keyless search backend via the `ddgs` package."""

    async def search(self, query: str, k: int = 5) -> list[Source]:
        try:
            rows = await asyncio.to_thread(lambda: DDGS().text(query, max_results=k))
        except DDGSException as e:
            if (
                type(e) is DDGSException and str(e) == NO_RESULTS
            ):  # no engine errored; nothing matched
                return []
            log.warning("duckduckgo search %r failed: %r", query, e)
            raise ToolError(f"search failed: {type(e).__name__}") from e
        except Exception as e:
            log.warning("duckduckgo search %r failed: %r", query, e)
            raise ToolError(f"search failed: {type(e).__name__}") from e
        return [
            Source(url=r.get("href", ""), title=r.get("title", ""), snippet=r.get("body", ""))
            for r in rows
        ][:k]
