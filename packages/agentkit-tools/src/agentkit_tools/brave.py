from __future__ import annotations

import httpx

from .models import Source, ToolError

BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"


def _body(resp: httpx.Response) -> str:
    try:
        return resp.text
    except Exception:  # body unreadable; treat as no error detail
        return ""


class BraveSearch:
    """Brave Search API (own index)."""

    def __init__(
        self, api_key: str, client: httpx.AsyncClient | None = None, timeout: float = 20.0
    ) -> None:
        self._key = api_key
        self._client = client or httpx.AsyncClient(timeout=timeout)

    async def search(self, query: str, k: int = 5) -> list[Source]:
        try:
            resp = await self._client.get(
                BRAVE_URL,
                headers={"X-Subscription-Token": self._key, "Accept": "application/json"},
                params={"q": query, "count": k},
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            # Brave reports a bad/expired key as 422 SUBSCRIPTION_TOKEN_INVALID instead of an
            # auth status; surface it as 401 so the fallback chain can disable us for the run.
            if status == 422 and "SUBSCRIPTION_TOKEN_INVALID" in _body(e.response):
                raise ToolError(
                    "search failed: HTTP 422 (invalid subscription token)", status=401
                ) from e
            raise ToolError(f"search failed: HTTP {status}", status=status) from e
        except httpx.HTTPError as e:
            raise ToolError(f"search failed: {type(e).__name__}") from e
        rows = (resp.json().get("web") or {}).get("results", [])
        return [
            Source(url=r["url"], title=r.get("title", ""), snippet=r.get("description", ""))
            for r in rows
        ][:k]
