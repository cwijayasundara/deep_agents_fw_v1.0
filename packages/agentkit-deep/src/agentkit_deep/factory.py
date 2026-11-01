from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from agentkit_core import ModelSpec, Settings, get_model
from deepagents import create_deep_agent
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
) -> Any:
    """The one way teams build agents. Model is always explicit; middleware is injectable
    (the Decisions-based selection middleware attaches here once T4/T5 land)."""
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
    )
