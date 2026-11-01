"""Offline test helpers: a scripted chat model that supports tool calling."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from pydantic import Field


class ScriptedChatModel(GenericFakeChatModel):
    """Scripted replies; records the tool names offered on every bind (one entry per model call)."""

    bound: list[list[str]] = Field(default_factory=list)

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> ScriptedChatModel:
        self.bound.append(
            [t["name"] if isinstance(t, dict) else getattr(t, "name", str(t)) for t in tools]
        )
        return self


def scripted(*messages: AIMessage) -> ScriptedChatModel:
    return ScriptedChatModel(messages=iter(messages))


def tool_call(name: str, args: dict[str, Any], id: str) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": id}])


def all_messages(it: Iterable[AIMessage]) -> ScriptedChatModel:
    return ScriptedChatModel(messages=iter(list(it)))
