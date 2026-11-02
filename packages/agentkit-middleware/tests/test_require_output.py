import pytest
from agentkit_core import BuildContext, ConfigError, ModelRegistry, Settings
from agentkit_middleware import RequireOutputMiddleware
from agentkit_middleware.factories import require_output
from agentkit_middleware.require_output import NUDGE_NAME
from langchain_core.messages import AIMessage, HumanMessage


def _ctx():
    return BuildContext(Settings(_env_file=None), ModelRegistry.default().resolve(), "a")


def _state(*messages, files=None):
    return {"messages": list(messages), "files": files or {}}


def test_final_reply_without_the_file_jumps_back_with_a_nudge():
    mw = RequireOutputMiddleware("/report.md")
    out = mw.after_model(_state(HumanMessage("q"), AIMessage("Let me delegate.")), None)
    assert out["jump_to"] == "model"
    (nudge,) = out["messages"]
    assert nudge.name == NUDGE_NAME and "/report.md" in nudge.content


def test_no_nudge_when_the_file_exists_or_the_model_called_a_tool():
    mw = RequireOutputMiddleware("/report.md")
    assert (
        mw.after_model(_state(AIMessage("done"), files={"/report.md": {"content": ["x"]}}), None)
        is None
    )
    call = AIMessage("", tool_calls=[{"name": "web_search", "args": {}, "id": "1"}])
    assert mw.after_model(_state(call), None) is None


def test_nudges_stop_at_max_nudges():
    mw = RequireOutputMiddleware("/report.md", max_nudges=2)
    out = mw.after_model({**_state(AIMessage("a")), "require_output_nudges": 1}, None)
    assert out["require_output_nudges"] == 2
    assert mw.after_model({**_state(AIMessage("a")), "require_output_nudges": 2}, None) is None


def test_a_file_unchanged_since_the_run_started_still_gets_a_nudge():
    mw = RequireOutputMiddleware("/report.md")
    files = {"/report.md": {"content": "old", "modified_at": "t1"}}
    start = mw.before_agent(_state(HumanMessage("q"), files=files), None)
    assert start["require_output_nudges"] == 0
    state = {**_state(AIMessage("a"), files=files), **start}
    assert mw.after_model(state, None)["jump_to"] == "model"
    rewritten = {"/report.md": {"content": "old", "modified_at": "t2"}}
    assert mw.after_model({**state, "files": rewritten}, None) is None


def test_factory_validates_params():
    assert require_output(_ctx(), path="/report.md").max_nudges == 2
    with pytest.raises(ConfigError, match="absolute"):
        require_output(_ctx(), path="report.md")
    with pytest.raises(ConfigError, match="max_nudges"):
        require_output(_ctx(), path="/r.md", max_nudges=0)


# --- per-run behaviour on a checkpointed thread (two turns, one thread) ---

CTX = {
    "tenant": "default",
    "product": "agentkit",
    "team": "platform",
    "user_id": "local",
    "thread_id": "t",
    "agent_name": "demo",
    "agent_version": "0",
}


def _graph(model):
    from agentkit_deep import build_deep_agent
    from langgraph.checkpoint.memory import InMemorySaver

    return build_deep_agent(
        model=model,
        system_prompt="s",
        middleware=[RequireOutputMiddleware("/report.md")],
        settings=Settings(_env_file=None, deployment_tenant="default"),
        checkpointer=InMemorySaver(),
    )


async def _turn(graph, model, text):
    before = len(model.bound)
    out = await graph.ainvoke(
        {"messages": [HumanMessage(text)]},
        {"configurable": {"thread_id": "t"}},
        context=CTX,
    )
    return out, len(model.bound) - before


def _write(content, id):
    from agentkit_deep.testing import tool_call

    return tool_call("write_file", {"file_path": "/report.md", "content": content}, id)


async def test_a_resumed_turn_gets_its_own_nudges():
    from agentkit_deep.testing import scripted

    model = scripted(*[AIMessage(f"Let me look ({i}).") for i in range(6)])
    graph = _graph(model)
    _, calls1 = await _turn(graph, model, "q1")
    _, calls2 = await _turn(graph, model, "q2")
    assert (calls1, calls2) == (3, 3)  # 1 + max_nudges each turn


async def test_a_report_from_an_earlier_turn_does_not_satisfy_this_turn():
    from agentkit_deep.testing import scripted

    model = scripted(
        _write("old report", "w1"),
        AIMessage("done"),
        AIMessage("Let me check the follow-up."),  # turn 2 ends without rewriting /report.md
        _write("new report", "w2"),
        AIMessage("done again"),
    )
    graph = _graph(model)
    _, calls1 = await _turn(graph, model, "q1")
    out, calls2 = await _turn(graph, model, "q2")
    assert calls1 == 2
    assert calls2 == 3  # the stale report did not end the turn; a nudge sent it back
    turn2 = out["messages"][[m.content for m in out["messages"]].index("q2") :]
    assert sum(isinstance(m, HumanMessage) and m.name == NUDGE_NAME for m in turn2) == 1
    assert "new report" in str(out["files"]["/report.md"]["content"])
