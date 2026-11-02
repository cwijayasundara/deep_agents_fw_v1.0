from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from agentkit_core import ModelSpec, Settings, get_model
from deepagents import FilesystemPermission, create_deep_agent
from deepagents.backends.protocol import BackendProtocol
from langchain.agents.middleware import AgentMiddleware
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver


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
) -> Any:
    """The one way teams build agents. Model is always explicit; middleware is injectable
    (the Decisions-based selection middleware attaches here once T4/T5 land).

    `skills` are skill *sources* (the parent dir of skill folders, e.g.
    `skills_mount.skills_source(owner)`); `backend` and `permissions` pass straight through."""
    if isinstance(model, ModelSpec):
        if settings is None:
            raise ValueError("settings is required when model is a ModelSpec")
        model = get_model(model, settings)
    return create_deep_agent(
        model=model,
        tools=list(tools),
        system_prompt=system_prompt,
        middleware=list(middleware),
        subagents=list(subagents) or None,  # type: ignore[arg-type]
        checkpointer=checkpointer,
        name=name,
        skills=None if skills is None else list(skills),
        backend=backend,
        permissions=None if permissions is None else list(permissions),
    )
