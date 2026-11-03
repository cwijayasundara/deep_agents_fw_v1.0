from __future__ import annotations

import httpx

from .models import Source, ToolError

PARALLEL_URL = "https://api.parallel.ai/v1/search"


class ParallelSearch:
    """Parallel Search API: results come with LLM-sized markdown excerpts."""

    def __init__(
        self,
        api_key: str,
        client: httpx.AsyncClient | None = None,
        timeout: float = 20.0,
        mode: str = "fast",
        max_chars_per_result: int = 1500,
    ) -> None:
        self._key = api_key
        self._client = client or httpx.AsyncClient(timeout=timeout)
        self._mode = mode
        self._max_chars = max_chars_per_result

    async def search(self, query: str, k: int = 5) -> list[Source]:
        try:
            resp = await self._client.post(
                PARALLEL_URL,
                headers={"x-api-key": self._key},
                json={
                    "objective": query,
                    "search_queries": [query],
                    "mode": self._mode,
                    "advanced_settings": {
                        "max_results": k,
                        "excerpt_settings": {"max_chars_per_result": self._max_chars},
                    },
                },
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            raise ToolError(f"search failed: HTTP {status}", status=status) from e
        except httpx.HTTPError as e:
            raise ToolError(f"search failed: {type(e).__name__}") from e
        return [
            Source(
                url=r["url"],
                title=r.get("title") or "",
                snippet="\n".join(r.get("excerpts") or []),
            )
            for r in resp.json().get("results", [])
        ][:k]
