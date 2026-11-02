"""Canonical middleware stack order for YAML agents.

The first middleware in the list is the outermost wrapper. `SelectionMiddleware` overrides the
request's model in `wrap_model_call`, so fallback sits inside it and can swap the model when that
one fails. Retry sits inside fallback, so each model is retried before the next is tried."""

from __future__ import annotations

from langchain.agents.middleware import AgentMiddleware

# "selection" is an internal slot name only; YAML uses the top-level `selection:` field.
STACK_ORDER: tuple[str, ...] = (
    "selection",
    "model_fallback",
    "model_retry",
    "tool_retry",
    "call_limit",
    "tool_call_limit",
    "pii",
)
SINGLETONS = frozenset({"selection", "model_fallback", "model_retry", "tool_retry", "call_limit"})


def order_stack(items: list[tuple[str, AgentMiddleware]]) -> list[AgentMiddleware]:
    """Stable sort by `STACK_ORDER`; unknown types follow all known ones in input order."""
    rank = {t: i for i, t in enumerate(STACK_ORDER)}
    return [m for _, m in sorted(items, key=lambda it: rank.get(it[0], len(rank)))]
