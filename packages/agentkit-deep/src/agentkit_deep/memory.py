"""Memory tiers for a persistent agent: one `CompositeBackend` over three kinds of path.

- `/memories/` → the store, at the run user's namespace (`store_namespace(ctx, "user", ...)`).
- `/org/` → the store, at the tenant-wide namespace. Agents read it; `ORG_WRITE_DENY` refuses
  writes at the tool layer, so org memory is seeded by operators, never by a run.
- `/skills/<owner>/` → the read-only skills routes from `skills_mount.skills_routes`, when given.
- everything else, `/report.md` included → `StateBackend`: ephemeral per-thread files.

The two kinds differ (`memories` vs `org`), so a user whose id is `global` writes
`(…, "global", "memories")` and can never reach org memory at `(…, "global", "org")`.
"""

from __future__ import annotations

from collections.abc import Mapping

from agentkit_core import PlatformContext, store_namespace
from deepagents import FilesystemPermission
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
from deepagents.backends.protocol import BackendProtocol
from langgraph.runtime import Runtime

USER_ROUTE, ORG_ROUTE = "/memories/", "/org/"
MEMORY_SOURCES = (f"{ORG_ROUTE}AGENTS.md", f"{USER_ROUTE}AGENTS.md")
ORG_WRITE_DENY = FilesystemPermission(operations=["write"], paths=[f"{ORG_ROUTE}**"], mode="deny")


def _user_namespace(rt: Runtime[PlatformContext]) -> tuple[str, ...]:
    return store_namespace(rt.context, "user", "memories")


def _org_namespace(rt: Runtime[PlatformContext]) -> tuple[str, ...]:
    return store_namespace(rt.context, "global", "org")


def memory_backend(skills: Mapping[str, BackendProtocol] | None = None) -> CompositeBackend:
    """The persistent agent's backend; `skills` are `skills_routes(...)`, absorbed as routes."""
    routes = dict(skills or {})
    clash = sorted(r for r in routes if r.startswith((USER_ROUTE, ORG_ROUTE)))
    if clash:
        raise ValueError(f"skills routes {clash} would shadow the memory routes")
    routes[ORG_ROUTE] = StoreBackend(namespace=_org_namespace)
    routes[USER_ROUTE] = StoreBackend(namespace=_user_namespace)
    return CompositeBackend(default=StateBackend(), routes=routes)


def has_memory_routes(backend: BackendProtocol) -> bool:
    """True when `backend` routes both memory tiers (i.e. it came from `memory_backend`)."""
    routes = backend.routes if isinstance(backend, CompositeBackend) else {}
    return all(isinstance(routes.get(r), StoreBackend) for r in (USER_ROUTE, ORG_ROUTE))
