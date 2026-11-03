"""Search wrappers: try backends in order, and cache repeated queries."""

from __future__ import annotations

import logging
from collections import OrderedDict
from collections.abc import Sequence

from .models import SearchTool, Source, ToolError

log = logging.getLogger(__name__)

# Auth or quota failures (432 is Tavily's plan limit): retrying in the same run is pointless.
DEAD_STATUSES = frozenset({401, 402, 403, 432})


class FallbackSearch:
    """Try each backend in turn; the next one runs only when the previous raised `ToolError`.

    A backend that fails with an auth or quota status (`DEAD_STATUSES`) is skipped from then on,
    unless it is the last one left.
    """

    def __init__(self, backends: Sequence[tuple[str, SearchTool]]) -> None:
        if not backends:
            raise ValueError("FallbackSearch needs at least one backend")
        self._backends = list(backends)
        self._dead: set[str] = set()

    async def search(self, query: str, k: int = 5) -> list[Source]:
        live = [(n, b) for n, b in self._backends if n not in self._dead] or self._backends[-1:]
        errors: list[str] = []
        for name, backend in live:
            try:
                return await backend.search(query, k)
            except ToolError as e:
                log.warning("web_search backend %s failed for %r: %s", name, query, e)
                errors.append(f"{name}: {e}")
                if e.status in DEAD_STATUSES and name not in self._dead:
                    self._dead.add(name)
                    log.warning(
                        "web_search backend %s disabled for this run (HTTP %s)", name, e.status
                    )
        raise ToolError("; ".join(errors))


class CachedSearch:
    """Remember successful results per (query, k) so a repeated query costs nothing."""

    def __init__(self, inner: SearchTool, max_entries: int = 256) -> None:
        self._inner = inner
        self._max = max_entries
        self._cache: OrderedDict[tuple[str, int], list[Source]] = OrderedDict()

    async def search(self, query: str, k: int = 5) -> list[Source]:
        key = (" ".join(query.lower().split()), k)
        if key in self._cache:
            self._cache.move_to_end(key)
            return list(self._cache[key])
        results = await self._inner.search(query, k)
        self._cache[key] = list(results)
        if len(self._cache) > self._max:
            self._cache.popitem(last=False)
        return results
