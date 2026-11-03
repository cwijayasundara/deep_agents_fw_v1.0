"""Run a graph to completion and collect everything the scorers need, from any namespace."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage


@dataclass
class CollectedRun:
    final: dict[str, Any]  # the final top-level state
    tool_outputs: list[str] = field(default_factory=list)  # every tool result, subagents too
    tool_calls: list[str] = field(default_factory=list)  # every tool call name, in order
    latency_s: float = 0.0


def _messages(update: Any) -> list[BaseMessage]:
    if not isinstance(update, dict):
        return []
    msgs = update.get("messages") or []
    msgs = getattr(msgs, "value", msgs)  # Overwrite wrapper
    return [m for m in msgs if isinstance(m, BaseMessage)] if isinstance(msgs, list) else []


async def collect_run(
    graph: Any, inputs: dict[str, Any], *, config: Any, context: Any
) -> CollectedRun:
    """Stream `graph`; the final state comes from the top-level "values", while tool results
    and tool-call names are gathered from every namespace (subagent results never reach the
    top-level message list). Mirrors the research CLI's `run_with_progress`, without logging."""
    run = CollectedRun(final={})
    start = time.monotonic()
    async for namespace, mode, data in graph.astream(
        inputs, config=config, context=context, stream_mode=["updates", "values"], subgraphs=True
    ):
        if mode == "values":
            if not namespace:
                run.final = data
        elif isinstance(data, dict):
            for update in data.values():
                for m in _messages(update):
                    if isinstance(m, ToolMessage):
                        run.tool_outputs.append(str(m.content))
                    elif isinstance(m, AIMessage):
                        run.tool_calls.extend(tc["name"] for tc in m.tool_calls)
    run.latency_s = time.monotonic() - start
    return run
