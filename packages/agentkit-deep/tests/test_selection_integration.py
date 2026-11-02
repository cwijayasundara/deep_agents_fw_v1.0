from types import SimpleNamespace

import pytest
from agentkit_deep import build_deep_agent
from agentkit_deep.testing import ctx, scripted, tool_call
from agentkit_middleware import (
    MissingPlatformContext,
    Selection,
    SelectionMiddleware,
    ToolCard,
)
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver


@tool
def alpha(x: str) -> str:
    """Alpha tool."""
    return "a"


@tool
def beta(x: str) -> str:
    """Beta tool."""
    return "b"


class FakeSelector:
    def __init__(self, sel=None, boom=False, by_thread=None):
        self.sel, self.boom, self.by_thread = sel, boom, by_thread or {}
        self.calls, self.seen, self.threads = 0, [], []

    async def select(self, task, tools: list[ToolCard], *, thread_id=None):
        self.calls += 1
        self.seen.append((task, [t.name for t in tools]))
        self.threads.append(thread_id)
        if self.boom:
            raise TimeoutError("decisions down")
        return self.by_thread.get(thread_id, self.sel)


def _model(turns=2):
    msgs = [tool_call("alpha", {"x": "1"}, str(i)) for i in range(turns - 1)]
    return scripted(*msgs, AIMessage(content="done"))


async def _run(selector, thread="t1", turns=2, mw=None):
    model = _model(turns)
    agent = build_deep_agent(
        model=model,
        system_prompt="p",
        tools=[alpha, beta],
        middleware=[mw or SelectionMiddleware(selector)],
    )
    await agent.ainvoke({"messages": [HumanMessage("do it")]}, context=ctx(thread_id=thread))
    return model


async def test_selects_once_per_run_and_keeps_builtins():
    sel = FakeSelector(Selection("default", frozenset({"alpha"})))
    model = await _run(sel, turns=3)
    assert sel.calls == 1 and len(model.bound) == 3  # cached in state across model calls
    assert sel.seen[0][0] == "do it"
    assert "beta" in sel.seen[0][1] and "write_file" not in sel.seen[0][1]  # builtins not offered
    assert all("alpha" in b and "beta" not in b for b in model.bound)


async def test_prompt_cache_key_is_the_context_thread():
    sel = FakeSelector(Selection("default", frozenset({"alpha"})))
    await _run(sel, thread="thread-42")
    assert sel.threads == ["thread-42"]


async def test_two_threads_in_one_process_get_independent_selections():
    sel = FakeSelector(
        by_thread={
            "t-a": Selection("default", frozenset({"alpha"})),
            "t-b": Selection("default", frozenset({"beta"})),
        }
    )
    mw = SelectionMiddleware(sel)  # one long-lived instance shared by both threads
    model_a = await _run(sel, thread="t-a", mw=mw)
    model_b = await _run(sel, thread="t-b", mw=mw)
    assert sel.calls == 2 and sel.threads == ["t-a", "t-b"]
    assert all("alpha" in b and "beta" not in b for b in model_a.bound)
    assert all("beta" in b and "alpha" not in b for b in model_b.bound)


async def test_selection_persists_per_thread_across_turns_with_checkpointer():
    sel = FakeSelector(Selection("default", frozenset({"alpha"})))
    model = scripted(AIMessage(content="one"), AIMessage(content="two"), AIMessage(content="3"))
    agent = build_deep_agent(
        model=model,
        system_prompt="p",
        tools=[alpha, beta],
        middleware=[SelectionMiddleware(sel)],
        checkpointer=InMemorySaver(),
    )
    for thread in ("t1", "t1", "t2"):
        await agent.ainvoke(
            {"messages": [HumanMessage("q")]},
            config={"configurable": {"thread_id": thread}},
            context=ctx(thread_id=thread),
        )
    assert sel.threads == ["t1", "t2"]  # t1's second turn reused its stored selection


async def test_failure_falls_back_to_all_tools_and_caches():
    sel = FakeSelector(boom=True)
    model = await _run(sel, turns=3)
    assert sel.calls == 1  # fallback is cached too: no hammering a down API
    assert all({"alpha", "beta"} <= set(b) for b in model.bound)


async def test_run_without_context_fails_at_the_factory_boundary():
    sel = FakeSelector(Selection("default", frozenset({"alpha"})))
    model = _model()
    agent = build_deep_agent(
        model=model, system_prompt="p", tools=[alpha], middleware=[SelectionMiddleware(sel)]
    )
    with pytest.raises(MissingPlatformContext, match="context=PlatformContext"):
        await agent.ainvoke({"messages": [HumanMessage("go")]})
    assert model.bound == [] and sel.calls == 0  # nothing ran


async def test_declarative_subagent_selection_is_its_own():
    """A declarative subagent with its own SelectionMiddleware: it selects from its own tools,
    sees the run's context, and neither inherits nor clobbers the parent's stored selection."""
    parent_sel = FakeSelector(Selection("default", frozenset({"alpha"})))
    sub_sel = FakeSelector(Selection("default", frozenset({"beta"})))
    model = scripted(
        tool_call("task", {"description": "sub-q", "subagent_type": "sub"}, "c1"),
        AIMessage(content="sub done"),
        tool_call("alpha", {"x": "1"}, "c2"),
        AIMessage(content="done"),
    )
    sub = {
        "name": "sub",
        "description": "a sub",
        "system_prompt": "s",
        "tools": [alpha, beta],
        "middleware": [SelectionMiddleware(sub_sel)],
    }
    agent = build_deep_agent(
        model=model,
        system_prompt="p",
        tools=[alpha, beta],
        subagents=[sub],
        middleware=[SelectionMiddleware(parent_sel)],
    )
    out = await agent.ainvoke({"messages": [HumanMessage("go")]}, context=ctx(thread_id="T"))
    assert out["messages"][-1].content == "done"
    assert parent_sel.calls == 1 and sub_sel.calls == 1
    assert parent_sel.threads == sub_sel.threads == ["T"]  # context reached the subagent
    assert sub_sel.seen[0][0] == "sub-q"
    parent_calls = [b for b in model.bound if "task" in b]
    sub_calls = [b for b in model.bound if "task" not in b]
    assert len(parent_calls) == 3 and len(sub_calls) == 1
    assert all("alpha" in b and "beta" not in b for b in parent_calls)
    assert "beta" in sub_calls[0] and "alpha" not in sub_calls[0]


def _req(tools, sel_state=None, context=None):
    captured: dict = {}

    class Req:
        messages = [HumanMessage("q")]
        state = {} if sel_state is None else {"agentkit_selection": sel_state}
        runtime = SimpleNamespace(context=context)

        def override(self, **kw):
            captured.update(kw)
            return self

    Req.tools = tools
    return Req(), captured


async def test_filter_applied_to_model_request_from_stored_state():
    sel = FakeSelector(Selection("default", frozenset({"beta"})))
    builtin = type("T", (), {"name": "write_file", "description": ""})()
    req, captured = _req(
        [alpha, beta, builtin], {"tier": "default", "tools": ["alpha"]}, ctx(thread_id="x")
    )

    async def handler(r):
        return "ok"

    assert await SelectionMiddleware(sel).awrap_model_call(req, handler) == "ok"  # type: ignore[arg-type]
    assert sel.calls == 0  # stored selection wins; no new Decisions call
    assert {t.name for t in captured["tools"]} == {"alpha", "write_file"}


async def test_tier_swaps_model():
    other = scripted(AIMessage(content="x"))
    mw = SelectionMiddleware(
        FakeSelector(Selection("strong", frozenset())), models={"strong": other}
    )
    req, captured = _req([alpha], context=ctx())

    async def handler(r):
        return AIMessage(content="ok")

    await mw.awrap_model_call(req, handler)  # type: ignore[arg-type]
    assert captured["model"] is other
