from __future__ import annotations

from collections.abc import Sequence
from functools import cache
from typing import Any

from agentkit_core import ModelSpec, PlatformContext, Settings, get_model
from agentkit_middleware import TenantGuardMiddleware
from deepagents import FilesystemPermission, create_deep_agent
from deepagents.backends.protocol import BackendProtocol
from langchain.agents.middleware import AgentMiddleware
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore


@cache
def _process_tenant() -> str:
    """The deployment tenant when no Settings are passed (read once: it is per process)."""
    return Settings().deployment_tenant


def build_deep_agent(
    *,
    model: BaseChatModel | ModelSpec,
    system_prompt: str,
    tools: Sequence[BaseTool] = (),
    subagents: Sequence[dict[str, Any]] = (),
    middleware: Sequence[AgentMiddleware] = (),
    settings: Settings | None = None,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
    name: str | None = None,
    skills: Sequence[str] | None = None,
    backend: BackendProtocol | None = None,
    permissions: Sequence[FilesystemPermission] | None = None,
    store: BaseStore | None = None,
) -> Any:
    """The one way teams build agents. Model is always explicit; middleware is injectable
    (the Decisions-based selection middleware attaches here once T4/T5 land).

    `skills` are skill *sources* (the parent dir of skill folders, e.g.
    `skills_mount.skills_source(owner)`); `backend` and `permissions` pass straight through.

    Every run must be invoked with `context=PlatformContext(...)`: `TenantGuardMiddleware`
    (for `settings.deployment_tenant`, from `AGENTKIT_TENANT`) goes ahead of all caller
    middleware and rejects a missing context or another tenant's run. Callers cannot opt out."""
    if isinstance(model, ModelSpec):
        if settings is None:
            raise ValueError("settings is required when model is a ModelSpec")
        model = get_model(model, settings)
    if any(isinstance(m, TenantGuardMiddleware) for m in middleware):
        raise ValueError("build_deep_agent adds TenantGuardMiddleware itself; do not pass one")
    tenant = settings.deployment_tenant if settings is not None else _process_tenant()
    guard = TenantGuardMiddleware(tenant)
    return create_deep_agent(
        model=model,
        tools=list(tools),
        system_prompt=system_prompt,
        middleware=[guard, *middleware],
        context_schema=PlatformContext,
        store=store,
        subagents=list(subagents) or None,  # type: ignore[arg-type]
        checkpointer=checkpointer,
        name=name,
        skills=None if skills is None else list(skills),
        backend=backend,
        permissions=None if permissions is None else list(permissions),
    )
