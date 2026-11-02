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
    nudge = HumanMessage("n", name=NUDGE_NAME)
    assert mw.after_model(_state(nudge, AIMessage("a")), None) is not None
    assert mw.after_model(_state(nudge, nudge, AIMessage("a")), None) is None


def test_factory_validates_params():
    assert require_output(_ctx(), path="/report.md").max_nudges == 2
    with pytest.raises(ConfigError, match="absolute"):
        require_output(_ctx(), path="report.md")
    with pytest.raises(ConfigError, match="max_nudges"):
        require_output(_ctx(), path="/r.md", max_nudges=0)
