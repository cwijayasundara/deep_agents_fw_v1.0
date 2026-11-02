"""Contract: langchain v1 agent runtime context and the middleware constructors we build on."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from agentkit_deep.testing import scripted, tool_call
from langchain.agents import create_agent
from langchain.agents.middleware import (
    AgentMiddleware,
    HumanInTheLoopMiddleware,
    ModelCallLimitMiddleware,
    ModelFallbackMiddleware,
    ModelRequest,
    ModelResponse,
    PIIMiddleware,
    ToolCallLimitMiddleware,
    ToolErrorMiddleware,
)
from langchain.tools import ToolRuntime, tool
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langgraph.runtime import Runtime
from pydantic import BaseModel

pytestmark = pytest.mark.contract


class Ctx(BaseModel):
    tenant: str
    user_id: str


class _Capture(AgentMiddleware[Any, Ctx]):
    def __init__(self) -> None:
        super().__init__()
        self.before_agent_ctx: list[object] = []
        self.model_call_ctx: list[object] = []

    async def abefore_agent(self, state: Any, runtime: Runtime[Ctx]) -> None:
        self.before_agent_ctx.append(runtime.context)

    async def awrap_model_call(
        self,
        request: ModelRequest[Ctx],
        handler: Callable[[ModelRequest[Ctx]], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        self.model_call_ctx.append(request.runtime.context)
        return await handler(request)


async def test_context_reaches_before_agent_model_call_and_tool() -> None:
    seen_by_tool: list[object] = []

    @tool
    def whoami(runtime: ToolRuntime[Ctx]) -> str:
        """Report the caller."""
        seen_by_tool.append(runtime.context)
        return "ok"

    capture = _Capture()
    agent = create_agent(
        scripted(tool_call("whoami", {}, "c1"), AIMessage(content="done")),
        tools=[whoami],
        middleware=[capture],
        context_schema=Ctx,
    )
    ctx = Ctx(tenant="acme", user_id="u7")
    await agent.ainvoke({"messages": [{"role": "user", "content": "hi"}]}, context=ctx)

    assert capture.before_agent_ctx == [ctx]
    assert capture.before_agent_ctx[0] is ctx
    assert len(capture.model_call_ctx) == 2
    assert all(c is ctx for c in capture.model_call_ctx)
    assert seen_by_tool == [ctx]


def _fake() -> GenericFakeChatModel:
    return GenericFakeChatModel(messages=iter([AIMessage(content="x")]))


class _Down(GenericFakeChatModel):
    def _generate(self, *args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("primary down")


async def test_model_fallback_answers_when_primary_raises() -> None:
    first, second = _fake(), _fake()
    mw = ModelFallbackMiddleware(first, second)
    assert mw.models == [first, second]
    primary = _Down(messages=iter([]))
    agent = create_agent(primary, middleware=[ModelFallbackMiddleware(_fake())])
    out = await agent.ainvoke({"messages": [{"role": "user", "content": "hi"}]})
    assert out["messages"][-1].content == "x"


def test_model_call_limit_builds() -> None:
    mw = ModelCallLimitMiddleware(run_limit=3, thread_limit=10, exit_behavior="error")
    assert (mw.run_limit, mw.thread_limit, mw.exit_behavior) == (3, 10, "error")


def test_tool_call_limit_builds() -> None:
    mw = ToolCallLimitMiddleware(tool_name="web_search", run_limit=2)
    assert (mw.tool_name, mw.run_limit, mw.exit_behavior) == ("web_search", 2, "continue")


def test_pii_middleware_builds_with_builtin_detector() -> None:
    mw = PIIMiddleware("email", strategy="redact")
    assert (mw.pii_type, mw.strategy) == ("email", "redact")
    assert mw.detector("mail a@b.io now")


def test_tool_error_middleware_requires_a_handler() -> None:
    with pytest.raises(ValueError, match="on_error"):
        ToolErrorMiddleware()
    mw = ToolErrorMiddleware(lambda exc, req: "failed", tools=["web_search"])
    assert mw.on_error is not None


def test_hitl_accepts_per_call_interrupt_mode() -> None:
    mw = HumanInTheLoopMiddleware({"write_file": True}, interrupt_mode="per_call")
    assert mw.interrupt_mode == "per_call"
    with pytest.raises(ValueError, match="per_call"):
        HumanInTheLoopMiddleware({"write_file": True}, interrupt_mode="bogus")  # type: ignore[arg-type]
