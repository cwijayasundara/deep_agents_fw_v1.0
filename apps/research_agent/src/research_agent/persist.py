"""`--persist` for the research CLIs: open Postgres, serialize turns per thread, report resumes.

Tenant guard limit (Ruling P4): `TenantGuardMiddleware` runs inside the graph, after LangGraph
has already checkpointed the run's input. A mismatched run would therefore write another
tenant's text into the thread's history before the guard rejects it. `require_tenant` closes
that gap for the CLIs by refusing the run before any graph call; code that invokes a persistent
graph directly must make the same check itself.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager, nullcontext
from typing import Any

from agentkit_core import Settings
from agentkit_middleware import TenantMismatch
from agentkit_persistence import (
    Persistence,
    PersistenceSettings,
    open_persistence,
    thread_lock,
)

PERSIST_HELP = (
    "keep threads and memory in encrypted Postgres (needs DATABASE_URL and LANGGRAPH_AES_KEY)"
)


@asynccontextmanager
async def persistence_for(persist: bool) -> AsyncIterator[Persistence | None]:
    """The deployment's Persistence under `--persist`, else None. ConfigError if misconfigured."""
    if not persist:
        yield None
        return
    async with open_persistence(PersistenceSettings.from_env()) as p:
        yield p


def require_tenant(tenant: str, settings: Settings) -> None:
    """Refuse another tenant's run before it can touch a checkpoint (Ruling P4)."""
    if tenant != settings.deployment_tenant:
        raise TenantMismatch(
            f"run tenant {tenant!r} != deployment tenant {settings.deployment_tenant!r}"
        )


def turn_lock(p: Persistence | None, thread: str) -> AbstractAsyncContextManager[None]:
    """Hold the thread's advisory lock for one turn (no-op without persistence)."""
    return thread_lock(p, thread) if p is not None else nullcontext()


async def resumed_step(graph: Any, thread: str) -> int | None:
    """The step of the thread's latest checkpoint, or None for a new thread."""
    state = await graph.aget_state({"configurable": {"thread_id": thread}})
    if not state.values:
        return None
    step = (state.metadata or {}).get("step")
    return int(step) if step is not None else None
