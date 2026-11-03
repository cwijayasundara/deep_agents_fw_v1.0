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


def test_prompt_hash_is_exposed_on_the_agent_config():
    import hashlib

    from agentkit_deep import agent_prompt_hash

    agent = build_deep_agent(model=scripted(AIMessage(content="x")), system_prompt="be brief")
    want = hashlib.sha256(b"be brief").hexdigest()
    assert agent.config["metadata"]["prompt_hash"] == want
    assert agent_prompt_hash(agent) == want


async def test_metered_model_reports_usage_and_model_name():
    from agentkit_deep.testing import MeteredChatModel

    model = MeteredChatModel(messages=iter([AIMessage(content="a")]), model_name="m1")
    out = await model.ainvoke("hi")
    assert out.usage_metadata == {"input_tokens": 10, "output_tokens": 3, "total_tokens": 13}
    assert model._get_ls_params()["ls_model_name"] == "m1"


def test_prompt_id_is_exposed_when_given():
    from agentkit_deep import agent_prompt_id

    plain = build_deep_agent(model=scripted(AIMessage(content="x")), system_prompt="p")
    assert agent_prompt_id(plain) == ""
    agent = build_deep_agent(
        model=scripted(AIMessage(content="x")), system_prompt="p", prompt_id="a/b@1.0.0"
    )
    assert agent.config["metadata"]["prompt_id"] == "a/b@1.0.0"
    assert agent_prompt_id(agent) == "a/b@1.0.0"
