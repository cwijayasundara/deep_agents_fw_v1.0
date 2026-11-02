"""The deployment tenant follows AGENTKIT_TENANT, and the suite is isolated from the ambient one."""

import os

import pytest
from agentkit_core import Settings
from agentkit_deep import build_deep_agent
from agentkit_deep.factory import _process_tenant
from agentkit_deep.testing import ctx, scripted
from agentkit_middleware import TenantMismatch
from langchain_core.messages import AIMessage, HumanMessage


def test_suite_runs_under_the_default_tenant() -> None:
    assert "AGENTKIT_TENANT" not in os.environ
    assert Settings.model_config["env_file"] is None  # a `.env` tenant cannot leak in
    assert Settings().deployment_tenant == "default"


async def test_guard_uses_an_exported_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTKIT_TENANT", "acme")
    _process_tenant.cache_clear()
    model = scripted(AIMessage(content="done"))
    agent = build_deep_agent(model=model, system_prompt="p")  # no settings: process tenant
    with pytest.raises(TenantMismatch, match="deployment tenant 'acme'"):
        await agent.ainvoke({"messages": [HumanMessage("go")]}, context=ctx())
    out = await agent.ainvoke({"messages": [HumanMessage("go")]}, context=ctx(tenant="acme"))
    assert out["messages"][-1].content == "done"


def test_dotenv_tenant_is_read_when_env_file_is_used(tmp_path) -> None:
    env = tmp_path / ".env"
    env.write_text("AGENTKIT_TENANT=beta\n")
    assert Settings(_env_file=env).deployment_tenant == "beta"
