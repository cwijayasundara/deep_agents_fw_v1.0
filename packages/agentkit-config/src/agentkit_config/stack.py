"""Canonical middleware stack order for YAML agents.

The first middleware in the list is the outermost wrapper. `SelectionMiddleware` overrides the
request's model in `wrap_model_call`, so fallback sits inside it and can swap the model when that
one fails. Retry sits inside fallback, so each model is retried before the next is tried.

`require_output` comes just before `call_limit`. `after_model` hooks run innermost first and a
`jump_to: "model"` skips every hook outside the one that jumps, so with this order the call that
ends in a nudge has already been counted by `ModelCallLimitMiddleware.after_model`, and the jump
re-enters through `call_limit`'s `before_model`: nudged runs stay inside the call budget."""

from __future__ import annotations

from langchain.agents.middleware import AgentMiddleware

# "selection" is an internal slot name only; YAML uses the top-level `selection:` field.
STACK_ORDER: tuple[str, ...] = (
    "selection",
    "model_fallback",
    "model_retry",
    "tool_retry",
    "require_output",
    "call_limit",
    "tool_call_limit",
    "pii",
)
SINGLETONS = frozenset(
    {"selection", "model_fallback", "model_retry", "tool_retry", "require_output", "call_limit"}
)


def order_stack(items: list[tuple[str, AgentMiddleware]]) -> list[AgentMiddleware]:
    """Stable sort by `STACK_ORDER`; unknown types follow all known ones in input order."""
    rank = {t: i for i, t in enumerate(STACK_ORDER)}
    return [m for _, m in sorted(items, key=lambda it: rank.get(it[0], len(rank)))]
