"""Offline test helpers: a scripted chat model that supports tool calling."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from agentkit_core import PlatformContext
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


def ctx(**overrides: str) -> PlatformContext:
    """A valid PlatformContext for the default deployment tenant; override any field."""
    base = {
        "tenant": "default",
        "product": "agentkit",
        "team": "platform",
        "user_id": "local",
        "thread_id": "t",
        "agent_name": "test",
        "agent_version": "0",
    }
    return PlatformContext(**{**base, **overrides})


def scripted(*messages: AIMessage) -> ScriptedChatModel:
    return ScriptedChatModel(messages=iter(messages))


def tool_call(name: str, args: dict[str, Any], id: str) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": id}])


def all_messages(it: Iterable[AIMessage]) -> ScriptedChatModel:
    return ScriptedChatModel(messages=iter(list(it)))


def _names(tools: Iterable[Any]) -> list[str]:
    return sorted(t["name"] if isinstance(t, dict) else getattr(t, "name", str(t)) for t in tools)


def describe_build(kwargs: Mapping[str, Any]) -> dict[str, Any]:
    """Comparable summary of the kwargs passed to build_deep_agent (for build-equivalence tests)."""
    subagents = [
        {
            "name": s["name"],
            "description": s["description"],
            "system_prompt": s["system_prompt"],
            "tools": _names(s.get("tools", [])),
            "skills": s.get("skills"),
        }
        for s in kwargs.get("subagents", [])
    ]
    return {
        "name": kwargs.get("name"),
        "system_prompt": kwargs.get("system_prompt"),
        "tools": _names(kwargs.get("tools", [])),
        "subagents": sorted(subagents, key=lambda s: s["name"]),
        "middleware": [type(m).__name__ for m in kwargs.get("middleware", [])],
        "skills": kwargs.get("skills"),
    }
