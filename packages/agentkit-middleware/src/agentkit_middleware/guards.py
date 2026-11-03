"""Deny-only tool guards: refuse a tool call before it runs, never rewrite or allow-list it.

Guards read the JSON metadata `agentkit_config` stamps on each registered tool
(`tool.metadata["agentkit"]`: owner, version, tenants, side_effects, ...). They fail closed: a
guard that raises, or metadata missing a key a guard needs, refuses the call.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from agentkit_core import Settings
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import ToolCall, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.types import Command

from .selection import BUILTIN_TOOLS

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Deny:
    guard: str
    reason: str


class Guard(Protocol):
    name: str

    def check(self, call: ToolCall, tool: BaseTool | None) -> Deny | None: ...


def _agentkit_meta(tool: BaseTool) -> Any:
    return (tool.metadata or {}).get("agentkit")


class TenantToolPolicyGuard:
    """Refuse unregistered tools and tools restricted to other tenants."""

    name = "tenant_tool_policy"

    def __init__(self, tenant: str) -> None:
        self.tenant = tenant

    def check(self, call: ToolCall, tool: BaseTool | None) -> Deny | None:
        if tool is None or call["name"] in BUILTIN_TOOLS:
            return None
        meta = _agentkit_meta(tool)
        if not isinstance(meta, dict):
            return Deny(self.name, f"unregistered tool {call['name']!r}")
        tenants = meta["tenants"]
        if tenants is not None and self.tenant not in tenants:
            return Deny(
                self.name, f"tool {call['name']!r} is not available to tenant {self.tenant!r}"
            )
        return None


class SideEffectsGuard:
    """Refuse registered tools whose side-effect class the deployment does not allow."""

    name = "side_effects"

    def __init__(self, allowed: frozenset[str]) -> None:
        self.allowed = frozenset(allowed)

    def check(self, call: ToolCall, tool: BaseTool | None) -> Deny | None:
        if tool is None or call["name"] in BUILTIN_TOOLS:
            return None
        meta = _agentkit_meta(tool)
        if not isinstance(meta, dict):
            return None  # TenantToolPolicyGuard refuses unregistered tools
        cls = meta["side_effects"]
        if cls not in self.allowed:
            return Deny(
                self.name,
                f"tool {call['name']!r} has side effects {cls!r}; allowed: {sorted(self.allowed)}",
            )
        return None


class GuardMiddleware(AgentMiddleware):
    """Run guards in order before each tool call; the first `Deny` refuses the call."""

    name = "agentkit_guards"

    def __init__(self, guards: Sequence[Guard]) -> None:
        super().__init__()
        self.guards = tuple(guards)

    def _refusal(self, request: ToolCallRequest) -> ToolMessage | None:
        call = request.tool_call
        for guard in self.guards:
            try:
                deny = guard.check(call, request.tool)
            except Exception as e:  # fail closed, without leaking the error text to the model
                deny = Deny(guard.name, f"guard failed: {type(e).__name__}")
            if deny is not None:
                log.warning("tool call %r refused by %s: %s", call["name"], deny.guard, deny.reason)
                return ToolMessage(
                    content=f"Tool call refused by {deny.guard}: {deny.reason}",
                    tool_call_id=call["id"],
                    name=call["name"],
                    status="error",
                )
        return None

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
    ) -> ToolMessage | Command[Any]:
        refusal = self._refusal(request)
        return refusal if refusal is not None else handler(request)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        refusal = self._refusal(request)
        return refusal if refusal is not None else await handler(request)


def platform_guards(settings: Settings) -> GuardMiddleware:
    """The platform's guards for one deployment: tenant tool policy, then side effects."""
    return GuardMiddleware(
        [
            TenantToolPolicyGuard(settings.deployment_tenant),
            SideEffectsGuard(settings.allowed_side_effects),
        ]
    )
