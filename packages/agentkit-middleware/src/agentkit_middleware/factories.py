from __future__ import annotations

from agentkit_core import BuildContext
from langchain.agents.middleware import AgentMiddleware, ModelCallLimitMiddleware


def call_limit(ctx: BuildContext, *, max_model_calls: int) -> AgentMiddleware:
    mw: AgentMiddleware = ModelCallLimitMiddleware(run_limit=max_model_calls)  # type: ignore[assignment]
    return mw
