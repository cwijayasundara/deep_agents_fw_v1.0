from __future__ import annotations

import httpx

from .models import Source, ToolError

TAVILY_URL = "https://api.tavily.com/search"


class TavilySearch:
    def __init__(
        self, api_key: str, client: httpx.AsyncClient | None = None, timeout: float = 20.0
    ) -> None:
        self._key = api_key
        self._client = client or httpx.AsyncClient(timeout=timeout)

    async def search(self, query: str, k: int = 5) -> list[Source]:
        try:
            resp = await self._client.post(
                TAVILY_URL,
                headers={"Authorization": f"Bearer {self._key}"},
                json={"query": query, "max_results": k},
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            raise ToolError(f"search failed: HTTP {status}", status=status) from e
        except httpx.HTTPError as e:
            raise ToolError(f"search failed: {type(e).__name__}") from e
        return [
            Source(url=r["url"], title=r.get("title", ""), snippet=r.get("content", ""))
            for r in resp.json().get("results", [])
        ][:k]
