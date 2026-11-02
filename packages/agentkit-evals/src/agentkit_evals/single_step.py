"""Single-step evals: stop the agent at its first top-level tool call and score that decision."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from contextlib import aclosing
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from .dataset import EvalCase


@dataclass
class StepResult:
    name: str | None  # the first top-level tool call's name; None for a text-only reply
    args: dict[str, Any] = field(default_factory=dict)
    text: str = ""
    calls: list[tuple[str, dict[str, Any]]] = field(default_factory=list)  # all, in order


def to_messages(turns: Iterable[dict[str, Any]]) -> list[BaseMessage]:
    """`{role, content}` turns to LangChain messages (user, assistant [+tool_calls], tool)."""
    out: list[BaseMessage] = []
    for t in turns:
        role, content = t.get("role"), t.get("content", "")
        if role == "user":
            out.append(HumanMessage(content))
        elif role == "assistant":
            calls = [
                {"name": c["name"], "args": c.get("args", {}), "id": c["id"], "type": "tool_call"}
                for c in t.get("tool_calls", [])
            ]
            out.append(AIMessage(content, tool_calls=calls))
        elif role == "tool":
            out.append(ToolMessage(content, tool_call_id=t["tool_call_id"], name=t.get("name")))
        else:
            raise ValueError(f"unknown message role {role!r}")
    return out


def case_messages(case: EvalCase) -> list[BaseMessage]:
    return to_messages(case.messages or [{"role": "user", "content": case.question}])


def _ai_messages(update: Any) -> list[AIMessage]:
    if not isinstance(update, dict):
        return []
    msgs = update.get("messages") or []
    msgs = getattr(msgs, "value", msgs)  # Overwrite wrapper
    return [m for m in msgs if isinstance(m, AIMessage)] if isinstance(msgs, list) else []


async def single_step(graph: Any, case: EvalCase, *, config: Any, context: Any) -> StepResult:
    """The first top-level model reply: its tool calls, or `name=None` and its text.

    No tool runs: leaving the stream at that update stops the graph before its tools node. Calls
    inside subagents (non-empty namespace) are never considered. Neither are the input
    messages: middleware may re-emit the whole list (PIIMiddleware redacting the last user turn,
    deepagents' PatchToolCallsMiddleware answering a dangling call) before the model runs, so
    every input message gets an id and an AIMessage carrying one of those ids is skipped."""
    inputs = [m.model_copy(update={"id": m.id or str(uuid.uuid4())}) for m in case_messages(case)]
    prefix_ids = {m.id for m in inputs}
    stream = graph.astream(
        {"messages": inputs},
        config=config,
        context=context,
        stream_mode="updates",
        subgraphs=True,
    )
    async with aclosing(stream):
        async for namespace, data in stream:
            if namespace or not isinstance(data, dict):
                continue
            for update in data.values():
                for m in _ai_messages(update):
                    if m.id in prefix_ids:
                        continue
                    # The first top-level model reply is the decision, whatever it holds:
                    # a text-only reply must not be given a second try by a nudge middleware.
                    calls = [(c["name"], dict(c.get("args") or {})) for c in m.tool_calls]
                    if not calls:
                        return StepResult(None, {}, str(m.content))
                    return StepResult(calls[0][0], calls[0][1], str(m.content), calls)
    return StepResult(None, {}, "")
