from __future__ import annotations

from pathlib import Path
from typing import Any

from agentkit_config.errors import SpecError
from agentkit_config.library import Library
from agentkit_config.pools.code import CodePools
from agentkit_config.registry import Registry
from agentkit_config.spec import AgentSpec, SubAgentSpec
from agentkit_config.validate import NO_CALL_LIMIT, validate_agent, validate_subagent
from agentkit_core import ModelRegistry
from agentkit_tools import ToolMeta

MODELS = ModelRegistry({"m1": {"provider": "openai", "fast": "a", "default": "b", "strong": "c"}})


def _tool(ctx: Any, *, limit: int = 1) -> Any: ...


_tool.__agentkit_tool__ = ToolMeta(owner="platform", version="1.0.0", side_effects="read")  # type: ignore[attr-defined]


def _mw(ctx: Any, *, n: int = 1) -> Any: ...


def _pools() -> CodePools:
    return CodePools(
        Registry("tool", {"t1": _tool, "t2": _tool}),
        Registry("middleware", {"call_limit": _mw}),
        Registry("node", {}),
        Registry("schema", {"Report": dict}),
    )


def _lib(tmp_path: Path, skills: dict[str, str] | None = None) -> Library:
    (tmp_path / "prompts").mkdir(exist_ok=True)
    (tmp_path / "prompts" / "main.md").write_text("Hi {{agent_name}} on {{date}}")
    (tmp_path / "prompts" / "bad.md").write_text("Hi {{who}}")
    for name, tools in (skills or {}).items():
        d = tmp_path / "skills" / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: d\nallowed-tools: {tools}\n---\nbody\n"
        )
    return Library.from_roots([tmp_path], _pools())


def _agent(**kw: Any) -> AgentSpec:
    base: dict[str, Any] = {
        "apiVersion": "agentkit/v1",
        "kind": "Agent",
        "name": "a",
        "model": "m1",
        "prompt": "main",
    }
    return AgentSpec.model_validate({**base, **kw})


def _sub(**kw: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "name": "s",
        "description": "d",
        "prompt": "main",
        "response_schema": "Report",
    }
    return {**base, **kw}


def _run(tmp_path: Path, spec: AgentSpec, skills: dict[str, str] | None = None) -> list[SpecError]:
    errs = validate_agent(spec, _lib(tmp_path, skills), MODELS, file="agent.yaml")
    return [e for e in errs if e.message != NO_CALL_LIMIT]  # covered by its own tests


def _msgs(errs: list[SpecError]) -> dict[str, str]:
    return {e.path: e.message for e in errs}


def test_valid_agent_has_no_errors(tmp_path: Path) -> None:
    assert _run(tmp_path, _agent(tools=["t1"], middleware=[{"type": "call_limit"}])) == []


def test_unknown_model_and_tier(tmp_path: Path) -> None:
    m = _msgs(_run(tmp_path, _agent(model="nope", tier="huge")))
    assert "m1" in m["model"]
    assert "tier" in m and "fast" in m["tier"]


def test_unknown_prompt(tmp_path: Path) -> None:
    m = _msgs(_run(tmp_path, _agent(prompt="nope")))
    assert "main" in m["prompt"]


def test_unknown_tool_in_subagent_exact_path(tmp_path: Path) -> None:
    spec = _agent(subagents=[_sub(tools=["t1", "t_typo"])])
    errs = _run(tmp_path, spec)
    assert [e.path for e in errs] == ["subagents[0].tools[1]"]
    assert "t_typo" in errs[0].message and "t1, t2" in errs[0].message


def test_unknown_skill(tmp_path: Path) -> None:
    m = _msgs(_run(tmp_path, _agent(skills=["ghost"])))
    assert "ghost" in m["skills[0]"]


def test_unknown_subagent_name(tmp_path: Path) -> None:
    m = _msgs(_run(tmp_path, _agent(subagents=["ghost"])))
    assert "ghost" in m["subagents[0]"]


def test_pool_subagent_is_validated(tmp_path: Path) -> None:
    (tmp_path / "subagents").mkdir()
    (tmp_path / "subagents" / "s.yaml").write_text(
        "name: s\ndescription: d\nprompt: main\nresponse_schema: Report\ntools: [bad_tool]\n"
    )
    errs = _run(tmp_path, _agent(subagents=["s"]))
    assert [e.path for e in errs] == ["subagents[0].tools[0]"]


def test_unknown_middleware_and_schema(tmp_path: Path) -> None:
    m = _msgs(_run(tmp_path, _agent(middleware=[{"type": "zzz"}])))
    assert "call_limit" in m["middleware[0]"]


def test_unknown_response_schema_in_subagent(tmp_path: Path) -> None:
    m = _msgs(_run(tmp_path, _agent(subagents=[_sub(response_schema="Nope")])))
    assert "Report" in m["subagents[0].response_schema"]


def test_bad_params(tmp_path: Path) -> None:
    spec = _agent(
        tools=[{"t1": {"bogus": 1}}], middleware=[{"type": "call_limit", "params": {"x": 1}}]
    )
    m = _msgs(_run(tmp_path, spec))
    assert "bogus" in m["tools[0]"]
    assert "'x'" in m["middleware[0]"]


def test_duplicate_tool_and_subagent_names(tmp_path: Path) -> None:
    spec = _agent(tools=["t1", "t1"], subagents=[_sub(tools=["t2", "t2"]), _sub()])
    m = _msgs(_run(tmp_path, spec))
    assert "duplicate" in m["tools[1]"]
    assert "duplicate" in m["subagents[0].tools[1]"]
    assert "duplicate" in m["subagents[1]"]


def test_prompt_variable_not_allowed(tmp_path: Path) -> None:
    m = _msgs(_run(tmp_path, _agent(prompt="bad")))
    assert "who" in m["prompt"]


def test_skill_tools_must_exist(tmp_path: Path) -> None:
    spec = _agent(tools=["t1"], skills=["sk"])
    errs = _run(tmp_path, spec, {"sk": "t1 t2 read_file"})
    assert [e.path for e in errs] == ["skills[0]"]
    assert "t2" in errs[0].message and "t1" not in errs[0].message.split("missing")[1]


def test_subagent_skill_uses_own_tools(tmp_path: Path) -> None:
    spec = _agent(tools=["t1"], subagents=[_sub(skills=["sk"])])
    errs = _run(tmp_path, spec, {"sk": "t1"})
    assert [e.path for e in errs] == ["subagents[0].skills[0]"]


def test_subagent_without_schema_warns(tmp_path: Path) -> None:
    spec = _agent(subagents=[_sub(response_schema=None)])
    errs = _run(tmp_path, spec)
    assert len(errs) == 1 and errs[0].severity == "warning"
    assert errs[0].message == "no response_schema; completion contract recommended"
    assert errs[0].path == "subagents[0]"


def test_selection_middleware_rejected(tmp_path: Path) -> None:
    m = _msgs(_run(tmp_path, _agent(middleware=[{"type": "selection"}])))
    assert m["middleware[0]"] == "use top-level 'selection:'"


def test_collects_all_errors(tmp_path: Path) -> None:
    spec = _agent(model="nope", prompt="nope", tools=["zzz"])
    assert {e.path for e in _run(tmp_path, spec)} == {"model", "prompt", "tools[0]"}


def test_validate_subagent_standalone(tmp_path: Path) -> None:
    sub = SubAgentSpec.model_validate(_sub(tools=["zzz"], model="m1"))
    errs = validate_subagent(sub, _lib(tmp_path), MODELS, file="s.yaml")
    assert [e.path for e in errs] == ["tools[0]"]


def test_no_code_pools_is_an_error_not_a_skip(tmp_path: Path) -> None:
    lib = Library.from_roots([_lib(tmp_path).roots[0]], None)
    spec = _agent(
        tools=["t1"],
        middleware=[{"type": "call_limit"}],
        subagents=[_sub(tools=["t2"])],
    )
    m = _msgs(validate_agent(spec, lib, MODELS, file="a.yaml"))
    assert set(m) == {
        "tools[0]",
        "middleware[0]",
        "subagents[0].tools[0]",
        "subagents[0].response_schema",
    }
    assert all("no code pools loaded" in v for v in m.values())


def test_subagent_unknown_model_and_tier(tmp_path: Path) -> None:
    m = _msgs(_run(tmp_path, _agent(subagents=[_sub(model="nope", tier="huge")])))
    assert "m1" in m["subagents[0].model"]
    assert "fast" in m["subagents[0].tier"]


def test_output_must_be_an_absolute_file_path(tmp_path: Path) -> None:
    assert "output" not in _msgs(_run(tmp_path, _agent(output="/report.md")))
    m = _msgs(_run(tmp_path, _agent(output="report")))
    assert m["output"] == "output must be an absolute file path like /report.md"


def test_subagent_name_must_differ_from_agent(tmp_path: Path) -> None:
    errs = _run(tmp_path, _agent(subagents=[_sub(name="a")]))
    assert [e.path for e in errs] == ["subagents[0]"]
    assert "differ" in errs[0].message


def _mwpools() -> CodePools:
    return CodePools(
        Registry("tool", {}),
        Registry(
            "middleware",
            {
                "call_limit": _mw,
                "model_retry": _mw,
                "pii": _mw_kw,
                "tool_call_limit": _mw_kw,
                "require_output": _mw_kw,
            },
        ),
        Registry("node", {}),
        Registry("schema", {"Report": dict}),
    )


def _mw_kw(ctx: Any, **kw: Any) -> Any: ...


def _run_mw(tmp_path: Path, spec: AgentSpec) -> list[SpecError]:
    _lib(tmp_path)  # writes the prompt files
    lib = Library.from_roots([tmp_path], _mwpools())
    return validate_agent(spec, lib, MODELS, file="agent.yaml")


CL = {"type": "call_limit"}


def test_duplicate_singleton_middleware_is_error(tmp_path: Path) -> None:
    spec = _agent(middleware=[CL, {"type": "model_retry"}, {"type": "model_retry"}])
    m = _msgs(_run_mw(tmp_path, spec))
    assert m["middleware[2]"] == "duplicate middleware 'model_retry'"
    off = _agent(
        middleware=[CL, {"type": "model_retry"}, {"type": "model_retry", "enabled": False}]
    )
    assert _run_mw(tmp_path, off) == []


def test_duplicate_require_output_is_error(tmp_path: Path) -> None:
    ro = {"type": "require_output", "params": {"path": "/report.md"}}
    m = _msgs(_run_mw(tmp_path, _agent(middleware=[ro, ro])))
    assert m["middleware[1]"] == "duplicate middleware 'require_output'"


def test_two_pii_types_ok_same_type_error(tmp_path: Path) -> None:
    def pii(t: str) -> dict[str, Any]:
        return {"type": "pii", "params": {"type": t}}

    ok = _agent(middleware=[CL, pii("email"), pii("url")])
    assert _run_mw(tmp_path, ok) == []
    bad = _agent(middleware=[CL, pii("email"), pii("email")])
    assert "middleware[2]" in _msgs(_run_mw(tmp_path, bad))
    tl = {"type": "tool_call_limit", "params": {"run_limit": 1}}
    tl2 = {"type": "tool_call_limit", "params": {"run_limit": 1, "tool_name": "x"}}
    assert _run_mw(tmp_path, _agent(middleware=[CL, tl, tl2])) == []
    assert "middleware[2]" in _msgs(_run_mw(tmp_path, _agent(middleware=[CL, tl, tl])))


def test_agent_without_call_limit_warns(tmp_path: Path) -> None:
    errs = _run_mw(tmp_path, _agent())
    assert [(e.severity, e.message, e.path) for e in errs] == [
        ("warning", "no call_limit; a runaway loop is unbounded", "")
    ]
    off = _agent(middleware=[{"type": "call_limit", "enabled": False}])
    assert len(_run_mw(tmp_path, off)) == 1


def test_subagent_without_call_limit_does_not_warn(tmp_path: Path) -> None:
    spec = _agent(middleware=[CL], subagents=[_sub()])
    assert _run_mw(tmp_path, spec) == []
