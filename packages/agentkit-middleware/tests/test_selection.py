from agentkit_deep import build_deep_agent
from agentkit_deep.testing import scripted, tool_call
from agentkit_middleware import Selection, SelectionMiddleware, ToolCard
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


class FakeSelector:
    def __init__(self, sel=None, boom=False):
        self.sel, self.boom, self.calls, self.seen = sel, boom, 0, []

    async def select(self, task, tools: list[ToolCard]):
        self.calls += 1
        self.seen.append((task, [t.name for t in tools]))
        if self.boom:
            raise TimeoutError("decisions down")
        return self.sel


async def _run(selector, thread="t1", turns=2):
    seen_tools: list[set[str]] = []
    msgs = [tool_call("alpha", {"x": "1"}, str(i)) for i in range(turns - 1)]
    model = scripted(*msgs, AIMessage(content="done"))
    mw = SelectionMiddleware(selector)
    original = mw._selection

    async def capture(thread_id, request):
        out = await original(thread_id, request)
        seen_tools.append({t.name for t in request.tools})
        return out

    mw._selection = capture  # type: ignore[method-assign]
    agent = build_deep_agent(model=model, system_prompt="p", tools=[alpha, beta], middleware=[mw])
    await agent.ainvoke(
        {"messages": [HumanMessage("do it")]}, config={"configurable": {"thread_id": thread}}
    )
    return seen_tools


async def test_selects_once_per_thread_and_keeps_builtins():
    sel = FakeSelector(Selection("default", frozenset({"alpha"})))
    await _run(sel, turns=3)
    assert sel.calls == 1
    assert sel.seen[0][0] == "do it"
    assert "beta" in sel.seen[0][1] and "write_file" not in sel.seen[0][1]  # builtins not offered


async def test_filter_applied_to_model_request():
    sel = Selection("default", frozenset({"alpha"}))
    mw = SelectionMiddleware(FakeSelector(sel))
    captured = {}

    class Req:
        tools = [alpha, beta, type("T", (), {"name": "write_file", "description": ""})()]
        messages = [HumanMessage("q")]

        def override(self, **kw):
            captured.update(kw)
            return self

    async def handler(r):
        return "ok"

    assert await mw.awrap_model_call(Req(), handler) == "ok"  # type: ignore[arg-type]
    assert {t.name for t in captured["tools"]} == {"alpha", "write_file"}


async def test_failure_falls_back_to_all_tools_and_caches():
    sel = FakeSelector(boom=True)
    mw = SelectionMiddleware(sel)
    captured = {}

    class Req:
        tools = [alpha, beta]
        messages = [HumanMessage("q")]

        def override(self, **kw):
            captured.update(kw)
            return self

    async def handler(r):
        return "ok"

    for _ in range(2):
        await mw.awrap_model_call(Req(), handler)  # type: ignore[arg-type]
    assert {t.name for t in captured["tools"]} == {"alpha", "beta"}
    assert sel.calls == 1  # fallback is cached too: no hammering a down API


async def test_tier_swaps_model():
    other = scripted(AIMessage(content="x"))
    mw = SelectionMiddleware(
        FakeSelector(Selection("strong", frozenset())), models={"strong": other}
    )
    captured = {}

    class Req:
        tools = [alpha]
        messages = [HumanMessage("q")]

        def override(self, **kw):
            captured.update(kw)
            return self

    async def handler(r):
        return "ok"

    await mw.awrap_model_call(Req(), handler)  # type: ignore[arg-type]
    assert captured["model"] is other
