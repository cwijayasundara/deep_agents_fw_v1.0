"""Offline test helpers: a scripted chat model that supports tool calling."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any, cast

from agentkit_core import PlatformContext
from agentkit_persistence import Persistence
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.messages.ai import UsageMetadata
from langchain_core.outputs import ChatResult
from langchain_core.tools import BaseTool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from pydantic import Field


class ScriptedChatModel(GenericFakeChatModel):
    """Scripted replies; records the tool names offered on every bind (one entry per model call)."""

    bound: list[list[str]] = Field(default_factory=list)

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> ScriptedChatModel:
        self.bound.append(
            [t["name"] if isinstance(t, dict) else getattr(t, "name", str(t)) for t in tools]
        )
        return self


class MeteredChatModel(ScriptedChatModel):
    """A ScriptedChatModel whose replies report `usage` as `usage_metadata` (ledger/trace tests).

    `model_name` becomes the `ls_model_name` callbacks see. A reply that already carries
    `usage_metadata` keeps it."""

    usage: dict[str, Any] = Field(
        default_factory=lambda: {"input_tokens": 10, "output_tokens": 3, "total_tokens": 13}
    )
    model_name: str = "scripted"

    def _generate(self, *args: Any, **kwargs: Any) -> ChatResult:
        result = super()._generate(*args, **kwargs)
        for gen in result.generations:
            msg = gen.message
            if isinstance(msg, AIMessage) and msg.usage_metadata is None:
                msg.usage_metadata = cast(UsageMetadata, dict(self.usage))
        return result


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


def memory_persistence() -> Persistence:
    """A `Persistence` on InMemorySaver/InMemoryStore (no Postgres, no pools, no encryption)."""
    none = cast(Any, None)
    return Persistence(
        pool=none,
        lock_pool=none,
        saver=cast(Any, InMemorySaver()),
        store=cast(Any, InMemoryStore()),
    )


def registered[T: BaseTool](
    tool: T, *, side_effects: str = "read", tenants: Sequence[str] | None = None
) -> T:
    """`tool`, carrying the `metadata["agentkit"]` a registered platform tool gets from
    agentkit-config, so the platform guards let a test fake run. Returns the same object."""
    meta = {"tenants": None if tenants is None else list(tenants), "side_effects": side_effects}
    tool.metadata = {**(tool.metadata or {}), "agentkit": meta}
    return tool


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
