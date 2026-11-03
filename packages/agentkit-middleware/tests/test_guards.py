from typing import Any

import pytest
from agentkit_core import Settings
from agentkit_middleware import (
    Deny,
    GuardMiddleware,
    SideEffectsGuard,
    TenantToolPolicyGuard,
    platform_guards,
)
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool, tool
from pydantic import ValidationError


def make_tool(name: str, meta: dict[str, Any] | None) -> BaseTool:
    @tool(name)
    def _t(q: str) -> str:
        """A test tool."""
        return q

    if meta is not None:
        _t.metadata = {"agentkit": meta}
    return _t


def meta(side_effects: str = "read", tenants: list[str] | None = None) -> dict[str, Any]:
    return {
        "owner": "platform",
        "version": "1.0.0",
        "tenants": tenants,
        "side_effects": side_effects,
        "identity": None,
        "classification": "internal",
        "examples": [],
    }


def request(name: str, t: BaseTool | None) -> ToolCallRequest:
    call = {"name": name, "args": {"q": "x"}, "id": "call-1", "type": "tool_call"}
    return ToolCallRequest(tool_call=call, tool=t, state={}, runtime=None)  # type: ignore[arg-type]


class Recorder:
    def __init__(self) -> None:
        self.calls: list[ToolCallRequest] = []

    async def __call__(self, req: ToolCallRequest) -> ToolMessage:
        self.calls.append(req)
        return ToolMessage(content="ran", tool_call_id=req.tool_call["id"])


def guards(tenant: str = "acme") -> GuardMiddleware:
    return platform_guards(Settings(_env_file=None, AGENTKIT_TENANT=tenant))  # type: ignore[call-arg]


async def run(mw: GuardMiddleware, name: str, t: BaseTool | None) -> tuple[Any, Recorder]:
    handler = Recorder()
    return await mw.awrap_tool_call(request(name, t), handler), handler


def assert_refused(out: Any, handler: Recorder, by: str, reason: str) -> None:
    assert isinstance(out, ToolMessage)
    assert out.status == "error"
    assert out.tool_call_id == "call-1"
    assert out.content == f"Tool call refused by {by}: {reason}"
    assert handler.calls == []


async def test_builtin_tool_passes() -> None:
    out, handler = await run(guards(), "read_file", make_tool("read_file", None))
    assert out.content == "ran"
    assert len(handler.calls) == 1


async def test_unregistered_tool_is_denied() -> None:
    out, handler = await run(guards(), "rogue", make_tool("rogue", None))
    assert_refused(out, handler, "tenant_tool_policy", "unregistered tool 'rogue'")


async def test_tool_of_another_tenant_is_denied_and_handler_not_called() -> None:
    t = make_tool("crm", meta(tenants=["beta"]))
    out, handler = await run(guards("acme"), "crm", t)
    assert_refused(
        out, handler, "tenant_tool_policy", "tool 'crm' is not available to tenant 'acme'"
    )
    out, handler = await run(guards("beta"), "crm", t)
    assert out.content == "ran"


async def test_write_tool_denied_by_default_read_and_external_allowed() -> None:
    mw = guards()
    for cls in ("read", "external"):
        out, handler = await run(mw, f"t_{cls}", make_tool(f"t_{cls}", meta(cls)))
        assert out.content == "ran", cls
    out, handler = await run(mw, "t_write", make_tool("t_write", meta("write")))
    assert_refused(
        out,
        handler,
        "side_effects",
        "tool 't_write' has side effects 'write'; allowed: ['external', 'read']",
    )


def test_sync_wrap_denies_too() -> None:
    calls: list[ToolCallRequest] = []

    def handler(req: ToolCallRequest) -> ToolMessage:
        calls.append(req)
        return ToolMessage(content="ran", tool_call_id="call-1")

    out = guards().wrap_tool_call(request("rogue", make_tool("rogue", None)), handler)
    assert isinstance(out, ToolMessage) and out.status == "error"
    assert calls == []
    out = guards().wrap_tool_call(request("ls", None), handler)
    assert out.content == "ran"


class Boom:
    name = "boom"

    def check(self, call: Any, tool: BaseTool | None) -> Deny | None:
        raise RuntimeError("secret detail")


class Always:
    def __init__(self, name: str) -> None:
        self.name = name

    def check(self, call: Any, tool: BaseTool | None) -> Deny | None:
        return Deny(self.name, "no")


async def test_raising_guard_denies_not_crashes() -> None:
    out, handler = await run(GuardMiddleware([Boom()]), "ls", None)
    assert_refused(out, handler, "boom", "guard failed: RuntimeError")
    assert "secret detail" not in out.content


async def test_first_deny_wins_and_names_guard() -> None:
    mw = GuardMiddleware([Always("first"), Always("second")])
    out, handler = await run(mw, "ls", None)
    assert_refused(out, handler, "first", "no")
    assert mw.name == "agentkit_guards"


def test_settings_parse_comma_list_and_reject_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    assert Settings(_env_file=None).allowed_side_effects == frozenset({"read", "external"})
    monkeypatch.setenv("AGENTKIT_ALLOWED_SIDE_EFFECTS", " read , write ")
    assert Settings(_env_file=None).allowed_side_effects == frozenset({"read", "write"})
    monkeypatch.setenv("AGENTKIT_ALLOWED_SIDE_EFFECTS", "read, writ")
    with pytest.raises(ValidationError, match="writ"):
        Settings(_env_file=None)


def test_guards_abstain_without_a_tool() -> None:
    call = {"name": "x", "args": {}, "id": "1", "type": "tool_call"}
    assert TenantToolPolicyGuard("acme").check(call, None) is None  # type: ignore[arg-type]
    assert SideEffectsGuard(frozenset({"read"})).check(call, None) is None  # type: ignore[arg-type]


async def test_metadata_missing_a_key_fails_closed() -> None:
    partial = {k: v for k, v in meta().items() if k != "side_effects"}
    out, handler = await run(guards(), "half", make_tool("half", partial))
    assert_refused(out, handler, "side_effects", "guard failed: KeyError")
