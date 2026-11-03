"""Capture what each chat-model call was actually sent: model, tools, system prompt, messages."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import BaseMessage


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def digest(messages: Sequence[BaseMessage]) -> str:
    """Order- and content-sensitive sha256 of a message list."""
    rows = [
        [m.type, m.content, getattr(m, "tool_calls", None), getattr(m, "tool_call_id", None)]
        for m in messages
    ]
    return _sha(json.dumps(rows, sort_keys=True, default=str))


@dataclass(frozen=True)
class CapturedRequest:
    namespace: str  # checkpoint_ns minus the calling node's own segment; "" is the main agent
    step: int | None  # langgraph_step
    model: str | None
    tools: tuple[str, ...]
    system_sha: str | None
    messages_sha: str  # digest of the non-system messages
    message_count: int


def _parent_namespace(checkpoint_ns: str) -> str:
    # Inside a node, checkpoint_ns ends with that node ("model:<id>"); a subagent's calls are
    # nested under its parent's node ("tools:<id>|model:<id>"). Dropping the last segment gives ""
    # for the main agent.
    return "|".join(checkpoint_ns.split("|")[:-1])


def _tool_names(params: dict[str, Any]) -> tuple[str, ...]:
    names = []
    for t in params.get("tools") or []:
        fn = t.get("function") if isinstance(t.get("function"), dict) else t
        if fn.get("name"):
            names.append(fn["name"])
    return tuple(sorted(names))


class RequestCapture(AsyncCallbackHandler):
    """Callback handler that records one `CapturedRequest` per chat-model call."""

    def __init__(self) -> None:
        self.records: list[CapturedRequest] = []

    async def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[BaseMessage]],
        *,
        run_id: UUID,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        params = kwargs.get("invocation_params") or {}
        meta = metadata or {}
        msgs = messages[0] if messages else []
        system = [m for m in msgs if m.type == "system"]
        rest = [m for m in msgs if m.type != "system"]
        self.records.append(
            CapturedRequest(
                namespace=_parent_namespace(meta.get("checkpoint_ns", "")),
                step=meta.get("langgraph_step"),
                model=params.get("model") or params.get("model_name"),
                tools=_tool_names(params),
                system_sha=_sha("\n".join(str(m.content) for m in system)) if system else None,
                messages_sha=digest(rest),
                message_count=len(rest),
            )
        )
