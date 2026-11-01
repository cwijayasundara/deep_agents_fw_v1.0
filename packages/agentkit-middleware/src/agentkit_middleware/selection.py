"""Per-thread model-tier + tool-surface selection.

The selector backend (OpenAI Decisions API, wired in T4) is behind the `Selector` protocol.
Selection runs ONCE per thread and is cached, so the provider prompt cache stays warm.
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from langchain.agents.middleware import AgentMiddleware, ModelRequest, ModelResponse
from langchain_core.language_models import BaseChatModel
from langgraph.config import get_config

log = logging.getLogger(__name__)

# DeepAgents harness tools are never hidden from the model.
BUILTIN_TOOLS = frozenset(
    {
        "ls",
        "read_file",
        "write_file",
        "edit_file",
        "delete",
        "glob",
        "grep",
        "execute",
        "task",
        "write_todos",
    }
)


@dataclass(frozen=True)
class ToolCard:
    name: str
    description: str


@dataclass(frozen=True)
class Selection:
    tier: str
    tool_names: frozenset[str]


class Selector(Protocol):
    async def select(
        self, task: str, tools: list[ToolCard], *, thread_id: str | None = None
    ) -> Selection: ...


def _name(tool: Any) -> str | None:
    return tool.get("name") if isinstance(tool, dict) else getattr(tool, "name", None)


def _desc(tool: Any) -> str:
    d = tool.get("description") if isinstance(tool, dict) else getattr(tool, "description", "")
    return str(d or "")


def _task_text(request: ModelRequest) -> str:
    for m in request.messages:
        if m.type == "human":
            return str(m.content)
    return ""


def _thread_id() -> str:
    try:
        return str(get_config().get("configurable", {}).get("thread_id", "_default"))
    except RuntimeError:  # outside a LangGraph run
        return "_default"


class SelectionMiddleware(AgentMiddleware):
    def __init__(
        self,
        selector: Selector,
        models: Mapping[str, BaseChatModel] | None = None,
        default_tier: str = "default",
        builtins: frozenset[str] = BUILTIN_TOOLS,
        max_threads: int = 1024,
    ) -> None:
        self._selector = selector
        self._models = dict(models or {})
        self._default_tier = default_tier
        self._builtins = builtins
        self._cache: OrderedDict[str, Selection] = OrderedDict()
        self._max = max_threads

    async def _selection(self, thread: str, request: ModelRequest) -> Selection:
        if thread in self._cache:
            self._cache.move_to_end(thread)
            return self._cache[thread]
        cards = [
            ToolCard(n, _desc(t))
            for t in request.tools
            if (n := _name(t)) is not None and n not in self._builtins
        ]
        try:
            sel = await self._selector.select(_task_text(request), cards, thread_id=thread)
        except Exception as e:  # degrade: all tools, default tier
            log.warning("selection unavailable for thread %s (%s); using all tools", thread, e)
            sel = Selection(self._default_tier, frozenset(c.name for c in cards))
        self._cache[thread] = sel
        if len(self._cache) > self._max:
            self._cache.popitem(last=False)
        return sel

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> Any:
        sel = await self._selection(_thread_id(), request)
        keep = sel.tool_names | self._builtins
        overrides: dict[str, Any] = {
            "tools": [t for t in request.tools if (n := _name(t)) is None or n in keep]
        }
        model = self._models.get(sel.tier)
        if model is not None:
            overrides["model"] = model
        return await handler(request.override(**overrides))
