from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from agentkit_config import CodePools, Library, SpecErrors, load_agent
from agentkit_config.cli import main
from agentkit_config.registry import Registry
from agentkit_config.spec import parse_agent
from agentkit_config.validate import validate_agent
from agentkit_core import ModelRegistry, Settings
from agentkit_deep.testing import scripted
from agentkit_tools import platform_tool
from langchain_core.tools import tool


def _build(ctx: Any) -> Any:
    @tool
    def x(query: str) -> str:
        """Do x."""
        return "x"

    return x


def _fresh() -> Any:
    return lambda ctx: _build(ctx)


restricted = platform_tool(
    owner="team-a", version="1.0.0", side_effects="read", tenants=["tenant-a"]
)(_fresh())
open_tool = platform_tool(owner="platform", version="2.1.0", side_effects="write")(_fresh())


def _pools(**tools: Any) -> CodePools:
    return CodePools(
        Registry("tool", tools),
        Registry("middleware", {}),
        Registry("node", {}),
        Registry("schema", {}),
    )


def _agent_file(tmp_path: Path) -> Path:
    (tmp_path / "prompts").mkdir(exist_ok=True)
    (tmp_path / "prompts" / "main.md").write_text("I am {{agent_name}}.")
    p = tmp_path / "agent.yaml"
    p.write_text(
        "apiVersion: agentkit/v1\nkind: Agent\nname: demo\nmodel: anthropic\nprompt: main\n"
        "tools: [x]\noutput: null\n"
    )
    return p


def _settings(tenant: str) -> Settings:
    return Settings(_env_file=None, deployment_tenant=tenant)  # type: ignore[arg-type]


def test_validate_rejects_tool_for_other_tenant(tmp_path: Path) -> None:
    p = _agent_file(tmp_path)
    lib = Library.from_roots([tmp_path], _pools(x=restricted))
    errs = validate_agent(
        parse_agent(p), lib, ModelRegistry.default(), file="a.yaml", tenant="tenant-b"
    )
    msgs = [(e.path, e.message) for e in errs if e.severity == "error"]
    assert msgs == [("tools[0]", "tool 'x' is not available to tenant 'tenant-b'")]


def test_load_agent_fails_before_get_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import agentkit_config.resolve as resolve_mod

    calls: list[Any] = []
    monkeypatch.setattr(resolve_mod, "get_model", lambda *a, **k: calls.append(a))
    p = _agent_file(tmp_path)
    lib = Library.from_roots([tmp_path], _pools(x=restricted))
    with pytest.raises(SpecErrors, match="not available to tenant 'tenant-b'"):
        load_agent(p, settings=_settings("tenant-b"), library=lib, model=scripted())
    assert calls == []


def test_allowed_tenant_loads_with_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import agentkit_config.load as load_mod
    import agentkit_config.resolve as resolve_mod

    seen: dict[str, Any] = {}
    monkeypatch.setattr(load_mod, "build_deep_agent", lambda **kw: seen.update(kw))
    p = _agent_file(tmp_path)
    lib = Library.from_roots([tmp_path], _pools(x=restricted))
    load_agent(p, settings=_settings("tenant-a"), library=lib, model=scripted())
    meta = seen["tools"][0].metadata["agentkit"]
    assert meta["owner"] == "team-a" and meta["tenants"] == ["tenant-a"]
    assert resolve_mod  # imported for symmetry with the spy test


def test_undecorated_tool_is_an_error(tmp_path: Path) -> None:
    """At runtime the guards refuse every call to it, so validate must not pass it."""
    p = _agent_file(tmp_path)
    lib = Library.from_roots([tmp_path], _pools(x=_build))
    errs = validate_agent(
        parse_agent(p), lib, ModelRegistry.default(), file="a.yaml", tenant="tenant-b"
    )
    assert [e.message for e in errs if e.severity == "error"] == [
        "tool 'x' has no @platform_tool metadata; its calls would be refused as unregistered"
    ]
    assert [e.path for e in errs if e.severity == "error"] == ["tools[0]"]


def test_tools_list_filters_by_tenant(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    pools = _pools(restricted_tool=restricted, open_tool=open_tool, bare=_build)
    monkeypatch.setattr(CodePools, "from_entry_points", classmethod(lambda cls: pools))
    assert main(["tools", "list", "--tenant", "tenant-b"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out == ["bare - - - - *", "open_tool 2.1.0 write internal platform *"]
    assert main(["tools", "list", "--tenant", "tenant-a"]) == 0
    out = capsys.readouterr().out
    assert "restricted_tool 1.0.0 read internal team-a tenant-a" in out


def test_factory_validate_hook_gets_params_and_library(tmp_path: Path) -> None:
    """Ruling S3: `__agentkit_validate__(params, library)` messages become errors; a crashing
    hook is an error too, never an exception out of validate."""
    seen: list[Any] = []

    def ok_hook(params: Any, library: Any) -> list[str]:
        seen.append((dict(params), library.roots))
        return ["connector 'c' is unknown"]

    def boom(params: Any, library: Any) -> list[str]:
        raise RuntimeError("bad")

    p = _agent_file(tmp_path)
    for hook, want in ((ok_hook, "connector 'c' is unknown"), (boom, "RuntimeError: bad")):
        f = platform_tool(owner="platform", version="1.0.0", side_effects="read")(_fresh())
        f.__agentkit_validate__ = hook  # type: ignore[attr-defined]
        lib = Library.from_roots([tmp_path], _pools(x=f))
        errs = validate_agent(parse_agent(p), lib, ModelRegistry.default(), file="a.yaml")
        msgs = [(e.path, e.message) for e in errs if e.severity == "error"]
        assert len(msgs) == 1 and msgs[0][0] == "tools[0]" and want in msgs[0][1]
    assert seen == [({}, (tmp_path.resolve(),))]


def _flow_with_agent(tmp_path: Path) -> Path:
    (tmp_path / "agents").mkdir(exist_ok=True)
    _agent_file(tmp_path).rename(tmp_path / "agents" / "demo.yaml")
    f = tmp_path / "flow.yaml"
    f.write_text(
        "apiVersion: agentkit/v1\nkind: Flow\nname: f\nstate: t.S\n"
        "nodes:\n  a: {agent: demo, input: q, output: d}\nedges:\n  - START -> a\n  - a -> END\n"
    )
    return f


def test_flow_validate_applies_tenant_policy_to_agent_nodes(tmp_path: Path) -> None:
    """Triage #8: a flow's agents are checked against the deployment tenant, like an agent file."""
    from agentkit_config.flow.validate import validate_flow
    from agentkit_config.spec import parse_flow

    f = _flow_with_agent(tmp_path)
    pools = _pools(x=restricted).override(schemas={"t.S": dict})
    lib = Library.from_roots([tmp_path], pools)
    models = ModelRegistry.default()
    errs = validate_flow(parse_flow(f), lib, models, file=str(f), tenant="tenant-b")
    assert [e.message for e in errs if e.severity == "error"] == [
        "tool 'x' is not available to tenant 'tenant-b'"
    ]
    assert not [
        e
        for e in validate_flow(parse_flow(f), lib, models, file=str(f), tenant="tenant-a")
        if e.severity == "error"
    ]


def test_cli_validate_flow_uses_the_deployment_tenant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    f = _flow_with_agent(tmp_path)
    pools = _pools(x=restricted).override(schemas={"t.S": dict})
    monkeypatch.setattr(CodePools, "from_entry_points", classmethod(lambda cls: pools))
    monkeypatch.setenv("AGENTKIT_TENANT", "tenant-b")
    assert main(["validate", str(f)]) == 1
    assert "not available to tenant 'tenant-b'" in capsys.readouterr().out
