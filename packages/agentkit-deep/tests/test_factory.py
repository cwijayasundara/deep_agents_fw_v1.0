import pytest
from agentkit_core import ModelSpec, Provider, Settings
from agentkit_deep import build_deep_agent
from agentkit_deep.testing import ctx, scripted, tool_call
from agentkit_middleware import TenantMismatch
from langchain_core.messages import AIMessage, HumanMessage


async def test_runs_one_step_and_writes_file():
    model = scripted(
        tool_call("write_file", {"file_path": "/a.md", "content": "hi"}, "1"),
        AIMessage(content="done"),
    )
    agent = build_deep_agent(model=model, system_prompt="be brief")
    out = await agent.ainvoke({"messages": [HumanMessage("go")]}, context=ctx())
    assert out["messages"][-1].content == "done"
    assert "/a.md" in out["files"]


def test_modelspec_requires_settings():
    with pytest.raises(ValueError, match="settings"):
        build_deep_agent(model=ModelSpec(Provider.ANTHROPIC, "x"), system_prompt="p")


async def test_deployment_tenant_comes_from_settings():
    model = scripted(AIMessage(content="done"))
    agent = build_deep_agent(
        model=model,
        system_prompt="p",
        settings=Settings(_env_file=None, deployment_tenant="acme"),
    )
    with pytest.raises(TenantMismatch, match="run tenant 'default' != deployment tenant 'acme'"):
        await agent.ainvoke({"messages": [HumanMessage("go")]}, context=ctx())
    assert model.bound == []  # the model was never called
    out = await agent.ainvoke({"messages": [HumanMessage("go")]}, context=ctx(tenant="acme"))
    assert out["messages"][-1].content == "done"


async def test_dict_context_is_validated_against_platform_context():
    agent = build_deep_agent(model=scripted(AIMessage(content="done")), system_prompt="p")
    bad = ctx().model_dump() | {"tenant": "acme.corp"}
    with pytest.raises(Exception, match="tenant"):
        await agent.ainvoke({"messages": [HumanMessage("go")]}, context=bad)
