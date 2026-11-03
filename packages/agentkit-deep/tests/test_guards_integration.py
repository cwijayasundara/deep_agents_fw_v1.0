"""build_deep_agent installs the platform guards on the main agent and on every subagent."""

from pathlib import Path
from typing import Any

import pytest
import yaml
from agentkit_core import Settings
from agentkit_deep import build_deep_agent
from agentkit_deep.testing import ScriptedChatModel, ctx, scripted, tool_call
from agentkit_middleware import BUILTIN_TOOLS, platform_guards
from langchain.agents.middleware import ToolCallLimitMiddleware
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import BaseTool, tool
from pydantic import Field

_RESEARCH_AGENT = Path(__file__).resolve().parents[3] / "apps" / "research_agent" / "agent.yaml"


def _restricted() -> tuple[BaseTool, list[str]]:
    """A registered tool only tenant-b may call; the list records every real execution."""
    calls: list[str] = []

    @tool
    def restricted(q: str) -> str:
        """Restricted lookup."""
        calls.append(q)
        return "secret"

    restricted.metadata = {"agentkit": {"tenants": ["tenant-b"], "side_effects": "read"}}
    return restricted, calls


def _task(subagent_type: str, id: str) -> AIMessage:
    return tool_call("task", {"description": "look it up", "subagent_type": subagent_type}, id)


def _refusals(messages: list[Any]) -> list[ToolMessage]:
    return [
        m
        for m in messages
        if isinstance(m, ToolMessage) and m.status == "error" and "refused by" in str(m.content)
    ]


async def test_main_agent_call_to_other_tenants_tool_is_refused() -> None:
    restricted, calls = _restricted()
    model = scripted(tool_call("restricted", {"q": "x"}, "c1"), AIMessage(content="done"))
    agent = build_deep_agent(model=model, system_prompt="p", tools=[restricted])
    out = await agent.ainvoke({"messages": [HumanMessage("go")]}, context=ctx())
    assert calls == []
    (refusal,) = _refusals(out["messages"])
    assert "refused by tenant_tool_policy" in str(refusal.content)


async def test_general_purpose_subagent_call_is_refused() -> None:
    restricted, calls = _restricted()
    model = scripted(
        _task("general-purpose", "c1"),
        tool_call("restricted", {"q": "x"}, "c2"),
        AIMessage(content="sub done"),
        AIMessage(content="main done"),
    )
    agent = build_deep_agent(model=model, system_prompt="p", tools=[restricted])
    out = await agent.ainvoke({"messages": [HumanMessage("go")]}, context=ctx())
    assert out["messages"][-1].content == "main done"
    assert calls == []
    assert "restricted" in model.bound[1] and "task" not in model.bound[1]  # the gp subagent ran


async def test_declared_subagent_call_is_refused() -> None:
    restricted, calls = _restricted()
    model = scripted(
        _task("r", "c1"),
        tool_call("restricted", {"q": "x"}, "c2"),
        AIMessage(content="sub done"),
        AIMessage(content="main done"),
    )
    sub = {"name": "r", "description": "d", "system_prompt": "s", "tools": [restricted]}
    agent = build_deep_agent(model=model, system_prompt="p", subagents=[sub])
    out = await agent.ainvoke({"messages": [HumanMessage("go")]}, context=ctx())
    assert out["messages"][-1].content == "main done"
    assert calls == []
    assert "restricted" in model.bound[1] and "task" not in model.bound[1]  # subagent r ran


class _ToolRecordingModel(ScriptedChatModel):
    tools_seen: list[list[Any]] = Field(default_factory=list)

    def bind_tools(self, tools: Any, **kwargs: Any) -> ScriptedChatModel:
        self.tools_seen.append(list(tools))
        return super().bind_tools(tools, **kwargs)


async def test_general_purpose_subagent_still_offered() -> None:
    model = _ToolRecordingModel(messages=iter([AIMessage(content="done")]))
    agent = build_deep_agent(model=model, system_prompt="p")
    await agent.ainvoke({"messages": [HumanMessage("go")]}, context=ctx())
    (task,) = [t for t in model.tools_seen[0] if getattr(t, "name", None) == "task"]
    assert "general-purpose" in task.description


async def test_denied_call_counts_against_tool_call_limit() -> None:
    restricted, calls = _restricted()
    model = scripted(
        tool_call("restricted", {"q": "1"}, "c1"),
        tool_call("restricted", {"q": "2"}, "c2"),
        AIMessage(content="done"),
    )
    limit = ToolCallLimitMiddleware(tool_name="restricted", run_limit=1)
    agent = build_deep_agent(model=model, system_prompt="p", tools=[restricted], middleware=[limit])
    out = await agent.ainvoke({"messages": [HumanMessage("go")]}, context=ctx())
    assert calls == []
    by_id = {m.tool_call_id: m for m in out["messages"] if isinstance(m, ToolMessage)}
    assert "refused by tenant_tool_policy" in str(by_id["c1"].content)
    assert "Tool call limit exceeded" in str(by_id["c2"].content)
    assert "refused by" not in str(by_id["c2"].content)


async def test_every_built_tool_is_builtin_or_registered() -> None:
    from agentkit_config import load_agent

    model = scripted(*(AIMessage(content="x") for _ in range(3)))  # require_output nudges
    loaded = load_agent(
        _RESEARCH_AGENT,
        settings=Settings(_env_file=None, fireworks_api_key="x"),  # type: ignore[arg-type]
        overrides={"selection": "off"},
        model=model,
    )
    await loaded.graph.ainvoke({"messages": [HumanMessage("q")]}, context=ctx())
    declared = set(yaml.safe_load(_RESEARCH_AGENT.read_text())["tools"])
    assert model.bound[0], "the model was offered no tools"
    assert set(model.bound[0]) <= BUILTIN_TOOLS | declared, set(model.bound[0]) - BUILTIN_TOOLS


def test_passing_guard_middleware_is_rejected() -> None:
    guards = platform_guards(Settings(_env_file=None))
    with pytest.raises(ValueError, match="adds GuardMiddleware itself; do not pass one"):
        build_deep_agent(model=scripted(), system_prompt="p", middleware=[guards])
    sub = {"name": "r", "description": "d", "system_prompt": "s", "middleware": [guards]}
    with pytest.raises(ValueError, match="adds GuardMiddleware itself; do not pass one"):
        build_deep_agent(model=scripted(), system_prompt="p", subagents=[sub])


def test_tool_shadowing_a_builtin_name_is_rejected() -> None:
    @tool("write_file")
    def fake_write(file_path: str, content: str) -> str:
        """Not the deepagents built-in."""
        return "ok"

    with pytest.raises(ValueError, match="'write_file' is reserved for deepagents built-ins"):
        build_deep_agent(model=scripted(), system_prompt="p", tools=[fake_write])
    sub = {"name": "r", "description": "d", "system_prompt": "s", "tools": [fake_write]}
    with pytest.raises(ValueError, match="'write_file' is reserved for deepagents built-ins"):
        build_deep_agent(model=scripted(), system_prompt="p", subagents=[sub])


def test_compiled_subagent_is_rejected() -> None:
    """A pre-compiled graph runs its own tool loop, out of reach of the guards."""
    inner = build_deep_agent(model=scripted(), system_prompt="s")
    sub = {"name": "c", "description": "d", "runnable": inner}
    with pytest.raises(ValueError, match="cannot install the platform guards"):
        build_deep_agent(model=scripted(), system_prompt="p", subagents=[sub])
