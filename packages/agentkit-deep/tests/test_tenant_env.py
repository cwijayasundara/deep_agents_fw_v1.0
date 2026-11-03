"""The deployment tenant follows AGENTKIT_TENANT, and the suite is isolated from the ambient one."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from agentkit_core import Settings
from agentkit_deep import build_deep_agent
from agentkit_deep.factory import _process_settings
from agentkit_deep.testing import ctx, scripted
from agentkit_middleware import TenantMismatch
from langchain_core.messages import AIMessage, HumanMessage


def test_suite_runs_under_the_default_tenant() -> None:
    assert "AGENTKIT_TENANT" not in os.environ
    assert Settings.model_config["env_file"] is None  # a `.env` tenant cannot leak in
    assert Settings().deployment_tenant == "default"


async def test_guard_uses_an_exported_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTKIT_TENANT", "acme")
    _process_settings.cache_clear()
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


_SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "tenant_env.sh"


def _stamped_repo(tmp_path: Path, tenant_file: str, dotenv: str | None = None) -> Path:
    """A throwaway repo layout holding a copy of tenant_env.sh and one tenant file."""
    (tmp_path / "scripts").mkdir()
    shutil.copy(_SCRIPT, tmp_path / "scripts" / "tenant_env.sh")
    (tmp_path / "deploy" / "tenants").mkdir(parents=True)
    (tmp_path / "deploy" / "tenants" / "t1.env").write_text(tenant_file)
    if dotenv is not None:
        (tmp_path / ".env").write_text(dotenv)
    return tmp_path / "scripts" / "tenant_env.sh"


def _run(script: Path) -> subprocess.CompletedProcess[str]:
    # A shell export must never survive: the tenant file decides, or Settings' default does.
    env = {**os.environ, "AGENTKIT_ALLOWED_SIDE_EFFECTS": "write"}
    probe = 'echo "${AGENTKIT_ALLOWED_SIDE_EFFECTS-<unset>}"'
    return subprocess.run(
        ["bash", str(script), "t1", "bash", "-c", probe],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_tenant_env_exports_the_stamped_side_effects(tmp_path: Path) -> None:
    script = _stamped_repo(tmp_path, "AGENTKIT_TENANT=t1\nAGENTKIT_ALLOWED_SIDE_EFFECTS=read\n")
    out = _run(script)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "read"


def test_tenant_env_leaves_side_effects_unset_for_an_older_stamp(tmp_path: Path) -> None:
    script = _stamped_repo(tmp_path, "AGENTKIT_TENANT=t1\n")
    out = _run(script)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "<unset>"  # Settings falls back to its default


def test_tenant_env_refuses_side_effects_in_dotenv(tmp_path: Path) -> None:
    script = _stamped_repo(
        tmp_path,
        "AGENTKIT_TENANT=t1\nAGENTKIT_ALLOWED_SIDE_EFFECTS=read\n",
        dotenv="AGENTKIT_ALLOWED_SIDE_EFFECTS=read,write\n",
    )
    out = _run(script)
    assert out.returncode == 2
    assert "AGENTKIT_ALLOWED_SIDE_EFFECTS" in out.stderr
