"""Run the agent while logging each step (model calls, tool calls, subagents) as it happens."""

from __future__ import annotations

import logging
import sys
import time
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage

log = logging.getLogger("research_agent")

_PREVIEW = 160


def setup_logging(verbosity: int = 0) -> None:
    """0 = progress (INFO), 1+ = DEBUG for agentkit/research_agent, -1 = warnings only."""
    level = logging.WARNING if verbosity < 0 else logging.DEBUG if verbosity > 0 else logging.INFO
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(levelname)-5s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stderr,
        force=True,
    )
    for name in ("research_agent", "agentkit_core", "agentkit_tools", "agentkit_middleware"):
        logging.getLogger(name).setLevel(level)


def _short(text: Any, n: int = _PREVIEW) -> str:
    s = " ".join(str(text).split())
    return s if len(s) <= n else s[: n - 1] + "…"


def _who(namespace: tuple[str, ...]) -> str:
    return "orchestrator" if not namespace else f"subagent[{len(namespace)}]"


def _messages(update: Any) -> list[BaseMessage]:
    if not isinstance(update, dict):
        return []
    msgs = update.get("messages") or []
    msgs = getattr(msgs, "value", msgs)  # Overwrite wrapper
    return [m for m in msgs if isinstance(m, BaseMessage)] if isinstance(msgs, list) else []


def _describe_call(name: str, args: dict[str, Any]) -> str:
    if name == "task":
        return f"delegate to {args.get('subagent_type', '?')}: {_short(args.get('description'))}"
    if name == "web_search":
        return f"web_search {args.get('query')!r}"
    if name == "fetch_url":
        return f"fetch_url {args.get('url')}"
    if name in ("write_file", "edit_file"):
        return f"{name} {args.get('file_path')}"
    if name == "write_todos":
        todos = args.get("todos") or []
        return f"write_todos ({len(todos)} items)"
    return f"{name} {_short(args, 100)}"


def log_update(namespace: tuple[str, ...], node: str, update: Any) -> None:
    who = _who(namespace)
    for m in _messages(update):
        if isinstance(m, AIMessage):
            if m.tool_calls:
                for tc in m.tool_calls:
                    log.info("%s -> %s", who, _describe_call(tc["name"], tc.get("args") or {}))
            elif m.content:
                log.info("%s says: %s", who, _short(m.content))
            usage = m.usage_metadata
            if usage:
                log.debug(
                    "%s tokens in=%s out=%s", who, usage["input_tokens"], usage["output_tokens"]
                )
        elif isinstance(m, ToolMessage):
            status = "error" if m.status == "error" or str(m.content).startswith("ERROR") else "ok"
            log.info("%s <- %s %s (%d chars)", who, m.name, status, len(str(m.content)))
            log.debug("%s <- %s: %s", who, m.name, _short(m.content, 400))


def _tool_texts(update: Any) -> list[str]:
    return [str(m.content) for m in _messages(update) if isinstance(m, ToolMessage)]


async def run_with_progress(
    agent: Any,
    inputs: dict[str, Any],
    config: dict[str, Any] | None = None,
    *,
    context: Any = None,
    tool_outputs: list[str] | None = None,
    tool_calls: list[str] | None = None,
) -> dict[str, Any]:
    """Stream the agent, logging every step; return the final top-level state.

    If `tool_outputs` is given, every tool result is appended to it, including results seen only
    inside subagents (which never reach the top-level message list). `tool_calls` likewise collects
    the name of every tool call, in order, from any namespace."""
    start = time.monotonic()
    final: dict[str, Any] = {}
    async for namespace, mode, data in agent.astream(
        inputs, config=config, context=context, stream_mode=["updates", "values"], subgraphs=True
    ):
        if mode == "values":
            if not namespace:
                final = data
        elif isinstance(data, dict):
            for node, update in data.items():
                log_update(namespace, node, update)
                if tool_outputs is not None:
                    tool_outputs.extend(_tool_texts(update))
                if tool_calls is not None:
                    tool_calls.extend(
                        tc["name"]
                        for m in _messages(update)
                        if isinstance(m, AIMessage)
                        for tc in m.tool_calls
                    )
    log.info("agent finished in %.1fs", time.monotonic() - start)
    return final
