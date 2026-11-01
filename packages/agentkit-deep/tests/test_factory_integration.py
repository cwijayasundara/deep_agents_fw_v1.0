"""build_deep_agent end to end: middleware order and what the model is actually offered."""

from agentkit_deep import build_deep_agent
from agentkit_deep.testing import scripted, tool_call
from agentkit_middleware import BUILTIN_TOOLS, Selection, SelectionMiddleware
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool


@tool
def alpha(x: str) -> str:
    """Alpha tool."""
    return "a"


@tool
def beta(x: str) -> str:
    """Beta tool."""
    return "b"


class Fixed:
    def __init__(self, tier="default", names=("alpha",)):
        self.sel = Selection(tier, frozenset(names))
        self.calls = 0

    async def select(self, task, tools, **kw):
        self.calls += 1
        return self.sel


def recorder(name: str, log: list[str]) -> AgentMiddleware:
    async def awrap_model_call(self, request, handler):
        log.append(name)
        return await handler(request)

    return type(f"Recorder_{name}", (AgentMiddleware,), {"awrap_model_call": awrap_model_call})()


async def _invoke(agent, thread="t"):
    return await agent.ainvoke(
        {"messages": [HumanMessage("go")]}, config={"configurable": {"thread_id": thread}}
    )


async def test_model_is_offered_only_selected_tools_plus_builtins():
    base = scripted(AIMessage(content="done"))
    await _invoke(build_deep_agent(model=base, system_prompt="p", tools=[alpha, beta]))
    baseline = set(base.bound[0])
    assert {"alpha", "beta", "write_file", "task"} <= baseline
    # guard: a DeepAgents upgrade that adds a built-in must be added to BUILTIN_TOOLS,
    # or selection would silently hide it from the model
    assert baseline - {"alpha", "beta"} <= BUILTIN_TOOLS

    model = scripted(tool_call("alpha", {"x": "1"}, "1"), AIMessage(content="done"))
    sel = Fixed()
    agent = build_deep_agent(
        model=model, system_prompt="p", tools=[alpha, beta], middleware=[SelectionMiddleware(sel)]
    )
    await _invoke(agent)
    assert len(model.bound) >= 2 and sel.calls == 1  # selected once, applied on every call
    for offered in model.bound:
        assert set(offered) == baseline - {"beta"}  # only the unselected tool is hidden


async def test_tier_selection_routes_to_the_tier_model():
    default, strong = (
        scripted(AIMessage(content="from-default")),
        scripted(AIMessage(content="from-strong")),
    )
    agent = build_deep_agent(
        model=default,
        system_prompt="p",
        tools=[alpha],
        middleware=[SelectionMiddleware(Fixed(tier="strong"), models={"strong": strong})],
    )
    out = await _invoke(agent)
    assert out["messages"][-1].content == "from-strong"
    assert not default.bound  # the default model was never bound or called


async def test_user_middleware_order_is_preserved():
    log: list[str] = []
    agent = build_deep_agent(
        model=scripted(AIMessage(content="ok")),
        system_prompt="p",
        middleware=[recorder("first", log), recorder("second", log)],
    )
    await _invoke(agent)
    assert log == ["first", "second"]  # outermost first, as supplied
