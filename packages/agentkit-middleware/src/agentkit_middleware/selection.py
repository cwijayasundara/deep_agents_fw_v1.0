"""Per-thread model-tier + tool-surface selection.

The selector backend (OpenAI Decisions API, wired in T4) is behind the `Selector` protocol.
Selection runs ONCE per thread: the result is stored in agent state (`agentkit_selection`), so
it is per thread, survives restarts with a checkpointer, and the provider prompt cache stays
warm. The key is private: a subagent neither inherits nor overwrites its parent's selection.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import asdict, dataclass
from typing import Annotated, Any, NotRequired, Protocol

from langchain.agents.middleware import (
    AgentMiddleware,
    AgentState,
    ExtendedModelResponse,
    ModelRequest,
    ModelResponse,
)
from langchain.agents.middleware.types import PrivateStateAttr
from langchain_core.callbacks import adispatch_custom_event
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langgraph.types import Command

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
class DecisionsUsage:
    """Tokens one selection request cost (cached tokens are part of `input_tokens`)."""

    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0


@dataclass(frozen=True)
class Selection:
    tier: str
    tool_names: frozenset[str]
    usage: DecisionsUsage | None = None  # what the selector's backend reported, if anything


# Custom callback event carrying a selection's DecisionsUsage (read by the cost ledger).
DECISIONS_USAGE_EVENT = "agentkit.decisions_usage"


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


STATE_KEY = "agentkit_selection"


class SelectionState(AgentState[Any]):
    agentkit_selection: NotRequired[Annotated[dict[str, Any], PrivateStateAttr]]


def _thread(request: ModelRequest) -> str | None:
    """The run's thread id from its PlatformContext (the Decisions prompt-cache key)."""
    return getattr(getattr(request.runtime, "context", None), "thread_id", None)


def _stored(request: ModelRequest) -> Selection | None:
    raw: dict[str, Any] | None = (request.state or {}).get(STATE_KEY)  # type: ignore[assignment]
    return Selection(raw["tier"], frozenset(raw["tools"])) if raw else None


def _with_update(response: Any, sel: Selection) -> ExtendedModelResponse[Any]:
    if isinstance(response, AIMessage):
        response = ModelResponse(result=[response])
    record = {"tier": sel.tier, "tools": sorted(sel.tool_names)}
    return ExtendedModelResponse(response, Command(update={STATE_KEY: record}))


async def _report_usage(usage: DecisionsUsage) -> None:
    """Hand the selection's token usage to the run's callbacks (e.g. the cost ledger)."""
    try:
        await adispatch_custom_event(DECISIONS_USAGE_EVENT, asdict(usage))
    except RuntimeError:  # outside a run (no parent run id): nobody to report to
        log.debug("decisions usage not reported: no active run")


class SelectionMiddleware(AgentMiddleware):
    state_schema = SelectionState

    def __init__(
        self,
        selector: Selector,
        models: Mapping[str, BaseChatModel] | None = None,
        default_tier: str = "default",
        builtins: frozenset[str] = BUILTIN_TOOLS,
    ) -> None:
        super().__init__()
        self._selector = selector
        self._models = dict(models or {})
        self._default_tier = default_tier
        self._builtins = builtins

    async def _select(self, request: ModelRequest) -> Selection:
        thread = _thread(request)
        cards = [
            ToolCard(n, _desc(t))
            for t in request.tools
            if (n := _name(t)) is not None and n not in self._builtins
        ]
        try:
            sel = await self._selector.select(_task_text(request), cards, thread_id=thread)
        except Exception as e:  # degrade: all tools, default tier (stored too: no hammering)
            log.warning("selection unavailable for thread %s (%s); using all tools", thread, e)
            return Selection(self._default_tier, frozenset(c.name for c in cards))
        log.info(
            "selection for thread %s: tier=%s tools=%s",
            thread,
            sel.tier,
            ", ".join(sorted(sel.tool_names)) or "none",
        )
        if sel.usage is not None:
            await _report_usage(sel.usage)
        return sel

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> Any:
        stored = _stored(request)
        sel = stored or await self._select(request)
        keep = sel.tool_names | self._builtins
        overrides: dict[str, Any] = {
            "tools": [t for t in request.tools if (n := _name(t)) is None or n in keep]
        }
        model = self._models.get(sel.tier)
        if model is not None:
            overrides["model"] = model
        response = await handler(request.override(**overrides))
        return response if stored else _with_update(response, sel)
