from __future__ import annotations

from typing import Literal

from agentkit_core import BuildContext, ConfigError, ModelRegistry, get_model
from langchain.agents.middleware import (
    AgentMiddleware,
    ModelCallLimitMiddleware,
    ModelFallbackMiddleware,
    ModelRetryMiddleware,
    PIIMiddleware,
    ToolCallLimitMiddleware,
    ToolRetryMiddleware,
)

# "url" is deliberately absent: redacting URLs would strip citations from answers.
_PII_TYPES = ("email", "credit_card", "ip", "mac_address")

# ModelCallLimit/ToolCallLimit are generic; mypy infers them as incompatible with the bare base,
# hence `type: ignore[assignment]` on those constructions.


def call_limit(
    ctx: BuildContext,
    *,
    max_model_calls: int,
    thread_limit: int | None = None,
    exit_behavior: Literal["end", "error"] = "end",
) -> AgentMiddleware:
    mw: AgentMiddleware = ModelCallLimitMiddleware(  # type: ignore[assignment]
        run_limit=max_model_calls, thread_limit=thread_limit, exit_behavior=exit_behavior
    )
    return mw


def tool_call_limit(
    ctx: BuildContext,
    *,
    run_limit: int,
    tool_name: str | None = None,
    thread_limit: int | None = None,
) -> AgentMiddleware:
    mw: AgentMiddleware = ToolCallLimitMiddleware(  # type: ignore[assignment]
        tool_name=tool_name,
        run_limit=run_limit,
        thread_limit=thread_limit,
        exit_behavior="continue",
    )
    return mw


def model_fallback(ctx: BuildContext, *, models: list[str]) -> AgentMiddleware:
    if not models:
        raise ConfigError("model_fallback needs at least one model")
    registry = ModelRegistry.default()
    built = []
    for item in models:
        entry, _, tier = item.partition(":")
        spec = registry.resolve(entry, tier or "default")
        built.append(get_model(spec, ctx.settings))
    mw: AgentMiddleware = ModelFallbackMiddleware(built[0], *built[1:])
    return mw


def model_retry(
    ctx: BuildContext,
    *,
    max_retries: int = 2,
    initial_delay: float = 1.0,
    max_delay: float = 30.0,
) -> AgentMiddleware:
    mw: AgentMiddleware = ModelRetryMiddleware(
        max_retries=max_retries,
        initial_delay=initial_delay,
        max_delay=max_delay,
        on_failure="error",
        jitter=True,
    )
    return mw


def tool_retry(
    ctx: BuildContext,
    *,
    max_retries: int = 2,
    tools: list[str] | None = None,
    initial_delay: float = 1.0,
    max_delay: float = 30.0,
) -> AgentMiddleware:
    mw: AgentMiddleware = ToolRetryMiddleware(
        max_retries=max_retries,
        tools=tools,  # type: ignore[arg-type]
        initial_delay=initial_delay,
        max_delay=max_delay,
        on_failure="continue",
    )
    return mw


def pii(
    ctx: BuildContext,
    *,
    type: str,  # noqa: A002 - YAML key
    strategy: Literal["block", "redact", "mask", "hash"] = "redact",
    apply_to_input: bool = True,
    apply_to_output: bool = False,
    apply_to_tool_results: bool = False,
) -> AgentMiddleware:
    if type == "url":
        raise ConfigError("pii type 'url' would redact citations; not allowed")
    if type not in _PII_TYPES:
        raise ConfigError(f"unknown pii type '{type}'; expected one of {_PII_TYPES}")
    mw: AgentMiddleware = PIIMiddleware(
        type,
        strategy=strategy,
        apply_to_input=apply_to_input,
        apply_to_output=apply_to_output,
        apply_to_tool_results=apply_to_tool_results,
    )
    return mw
