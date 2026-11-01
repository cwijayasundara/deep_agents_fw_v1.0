import pytest
from agentkit_core import ModelSpec, Provider
from agentkit_deep import build_deep_agent
from agentkit_deep.testing import scripted, tool_call
from langchain_core.messages import AIMessage, HumanMessage


async def test_runs_one_step_and_writes_file():
    model = scripted(
        tool_call("write_file", {"file_path": "/a.md", "content": "hi"}, "1"),
        AIMessage(content="done"),
    )
    agent = build_deep_agent(model=model, system_prompt="be brief")
    out = await agent.ainvoke({"messages": [HumanMessage("go")]})
    assert out["messages"][-1].content == "done"
    assert "/a.md" in out["files"]


def test_modelspec_requires_settings():
    with pytest.raises(ValueError, match="settings"):
        build_deep_agent(model=ModelSpec(Provider.ANTHROPIC, "x"), system_prompt="p")
