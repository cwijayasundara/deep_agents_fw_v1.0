from __future__ import annotations

import hashlib
from collections.abc import Sequence
from functools import cache
from typing import TYPE_CHECKING, Any

from agentkit_core import ModelSpec, PlatformContext, Settings, get_model
from agentkit_middleware import TenantGuardMiddleware
from deepagents import FilesystemPermission, create_deep_agent
from deepagents.backends.protocol import BackendProtocol
from langchain.agents.middleware import AgentMiddleware
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore

from .memory import MEMORY_SOURCES, ORG_WRITE_DENY, has_memory_routes, memory_backend

if TYPE_CHECKING:
    from agentkit_persistence import Persistence

PROMPT_HASH_KEY = "prompt_hash"
PROMPT_ID_KEY = "prompt_id"


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
    persistence: Persistence | None = None,
    prompt_id: str | None = None,
) -> Any:
    """The one way teams build agents. Model is always explicit; middleware is injectable
    (the Decisions-based selection middleware attaches here once T4/T5 land).

    `skills` are skill *sources* (the parent dir of skill folders, e.g.
    `skills_mount.skills_source(owner)`); `backend` and `permissions` pass straight through.

    Every run must be invoked with `context=PlatformContext(...)`: `TenantGuardMiddleware`
    (for `settings.deployment_tenant`, from `AGENTKIT_TENANT`) goes ahead of all caller
    middleware and rejects a missing context or another tenant's run. Callers cannot opt out.

    `persistence` makes the agent durable: its encrypted saver and store become the
    checkpointer and store, the backend gets the memory tiers (`memory.memory_backend()`, or
    the caller's `backend` if it came from `memory_backend(skills_routes(...))`), both
    `AGENTS.md` sources load into the prompt, and `/org/**` writes are denied.

    Guard limit: the guard runs inside the graph, after a checkpointer has saved the run's
    input. A caller invoking a persistent agent must compare `context.tenant` with the
    deployment tenant first (as `research_agent.persist.require_tenant` does), or another
    tenant's input lands in the thread's history before the guard refuses the run.

    The returned agent's `config["metadata"]["prompt_hash"]` is the SHA-256 of `system_prompt`
    as configured, before memory or harness text is added (see `prompt_hash`); every run and
    trace inherits it. `prompt_id` (`name@version` from the prompt registry), when given, is
    exposed the same way as `config["metadata"]["prompt_id"]`."""
    if isinstance(model, ModelSpec):
        if settings is None:
            raise ValueError("settings is required when model is a ModelSpec")
        model = get_model(model, settings)
    if any(isinstance(m, TenantGuardMiddleware) for m in middleware):
        raise ValueError("build_deep_agent adds TenantGuardMiddleware itself; do not pass one")
    tenant = settings.deployment_tenant if settings is not None else _process_tenant()
    guard = TenantGuardMiddleware(tenant)
    memory: list[str] | None = None
    if persistence is not None:
        if checkpointer is not None or store is not None:
            raise ValueError("persistence supplies the checkpointer and store; pass only one")
        if backend is None:
            backend = memory_backend()
        elif not has_memory_routes(backend):
            raise ValueError("with persistence, backend must come from memory_backend(...)")
        checkpointer, store = persistence.saver, persistence.store
        memory = list(MEMORY_SOURCES)
        permissions = [ORG_WRITE_DENY, *(permissions or ())]
    agent: Any = create_deep_agent(
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
        memory=memory,
    )
    metadata = {PROMPT_HASH_KEY: prompt_hash(system_prompt)}
    if prompt_id:
        metadata[PROMPT_ID_KEY] = prompt_id
    return agent.with_config(metadata=metadata)


def prompt_hash(system_prompt: str) -> str:
    """SHA-256 (hex) of the configured system prompt: which prompt a trace or usage row ran.

    It hashes the text passed to `build_deep_agent`, not what the model finally sees (deepagents'
    base prompt and `AGENTS.md` memory are added at run time and are not part of the hash)."""
    return hashlib.sha256(system_prompt.encode()).hexdigest()


def agent_prompt_hash(agent: Any) -> str:
    """The prompt hash `build_deep_agent` put on the agent's config; "" for any other graph."""
    config = getattr(agent, "config", None) or {}
    return str((config.get("metadata") or {}).get(PROMPT_HASH_KEY, ""))


def agent_prompt_id(agent: Any) -> str:
    """The `name@version` prompt id `build_deep_agent` put on the agent's config; "" if none."""
    config = getattr(agent, "config", None) or {}
    return str((config.get("metadata") or {}).get(PROMPT_ID_KEY, ""))
