"""The one way callers build a run's RunnableConfig: thread, tenant metadata, ledger, tracing.

The metadata values are identifiers only (tenant, user, thread, agent, prompt hash). LangGraph
copies string metadata into the plaintext `checkpoints.metadata` column, so never put user
content or secrets here (Ruling P3).
"""

from __future__ import annotations

import uuid
from typing import Any

from agentkit_core import PlatformContext
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.runnables import RunnableConfig
from langfuse.langchain import CallbackHandler

from .ledger import CostLedger
from .tracing import langchain_handler, trace_id_for


def run_config(
    ctx: PlatformContext, prompt_hash: str, ledger: CostLedger, *, recursion_limit: int = 100
) -> RunnableConfig:
    """Config for one run of `ctx`: a fresh root `run_id`, the ledger, and a tracing handler
    when tracing is on. Callers pass `context=ctx` to the run as well."""
    run_id = uuid.uuid4()
    callbacks: list[BaseCallbackHandler] = [ledger]
    handler = langchain_handler(run_id)
    if handler is not None:
        callbacks.append(handler)
    metadata: dict[str, Any] = {
        "tenant": ctx.tenant,
        "product": ctx.product,
        "team": ctx.team,
        "user_id": ctx.user_id,
        "thread_id": ctx.thread_id,
        "agent_name": ctx.agent_name,
        "agent_version": ctx.agent_version,
        "prompt_hash": prompt_hash,
        "langfuse_user_id": ctx.user_id,
        "langfuse_session_id": ctx.thread_id,
        "langfuse_tags": [f"tenant:{ctx.tenant}", f"agent:{ctx.agent_name}"],
    }
    return RunnableConfig(
        run_id=run_id,
        recursion_limit=recursion_limit,
        configurable={"thread_id": ctx.thread_id},
        metadata=metadata,
        callbacks=callbacks,
    )


def trace_id(config: RunnableConfig) -> str | None:
    """The trace id of a run built by `run_config`; None when that run is not traced."""
    callbacks = config.get("callbacks") or []
    traced = isinstance(callbacks, list) and any(isinstance(c, CallbackHandler) for c in callbacks)
    run_id = config.get("run_id")
    return trace_id_for(run_id) if traced and run_id is not None else None
