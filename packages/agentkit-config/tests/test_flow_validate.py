from __future__ import annotations

from pathlib import Path
from typing import TypedDict

from agentkit_config import CodePools, Library
from agentkit_config.errors import SpecError
from agentkit_config.flow.compile import flow_roots
from agentkit_config.flow.validate import validate_flow
from agentkit_config.spec import parse_flow
from agentkit_core import ModelRegistry

HEAD = "apiVersion: agentkit/v1\nkind: Flow\nname: f\nstate: t.S\n"


class S(TypedDict, total=False):
    x: str


def step(state: S) -> dict[str, str]:
    return {"x": "y"}


def route(state: S) -> str:
    return "ok"


def pools() -> CodePools:
    return CodePools.from_entry_points().override(
        schemas={"t.S": S}, nodes={"t.step": step, "t.route": route}
    )


def check(tmp_path: Path, body: str) -> list[SpecError]:
    f = tmp_path / "flow.yaml"
    f.write_text(HEAD + body, encoding="utf-8")
    lib = Library.from_roots([tmp_path], pools())
    return validate_flow(parse_flow(f), lib, ModelRegistry.default(), file=str(f))


def pairs(errs: list[SpecError]) -> list[tuple[str, str]]:
    return [(e.path, e.message) for e in errs]


def test_valid_fn_flow_has_no_errors(tmp_path: Path) -> None:
    body = (
        "nodes:\n  a: {fn: t.step}\n  b: {interrupt: true}\n"
        "edges:\n  - START -> a\n  - from: a\n    route: t.route\n    to: {ok: b, done: END}\n"
        "  - b -> END\n"
    )
    assert check(tmp_path, body) == []


def test_unreachable_node_error(tmp_path: Path) -> None:
    body = "nodes:\n  a: {fn: t.step}\n  b: {fn: t.step}\nedges:\n  - START -> a -> END\n"
    errs = pairs(check(tmp_path, body))
    assert ("nodes.b", "node 'b' is unreachable from START") in errs
    assert all(p != "nodes.a" for p, _ in errs)


def test_end_unreachable_error(tmp_path: Path) -> None:
    body = "nodes:\n  a: {fn: t.step}\n  b: {fn: t.step}\nedges:\n  - START -> a -> b -> a\n"
    errs = pairs(check(tmp_path, body))
    assert ("nodes.a", "END is unreachable from node 'a'") in errs
    assert ("nodes.b", "END is unreachable from node 'b'") in errs


def test_unknown_route_target_error(tmp_path: Path) -> None:
    body = (
        "nodes:\n  a: {fn: t.step}\n"
        "edges:\n  - START -> a\n  - from: a\n    route: t.route\n    to: {ok: END, x: nope}\n"
    )
    errs = pairs(check(tmp_path, body))
    assert ("edges[1].to.x", "unknown route target 'nope'; known: END, a") in errs


def test_edge_errors_use_original_yaml_index(tmp_path: Path) -> None:
    body = (
        "nodes:\n  a: {fn: t.step}\n  b: {fn: t.step}\n"
        "edges:\n  - START -> a -> b -> END\n  - ghost -> a\n"
        "  - from: zed\n    route: t.nah\n    to: {ok: END}\n"
    )
    errs = pairs(check(tmp_path, body))
    assert ("edges[1]", "unknown edge source 'ghost' in 'ghost -> a'; known: START, a, b") in errs
    assert ("edges[2].from", "unknown route source 'zed'; known: a, b") in errs
    assert any(p == "edges[2].route" and "'t.nah'" in m and "t.route" in m for p, m in errs)
    assert not any(p.startswith("edges[0]") for p, _ in errs)


def test_missing_start_edge_error(tmp_path: Path) -> None:
    assert ("edges", "flow needs an edge from START, like 'START -> a'") in pairs(
        check(tmp_path, "nodes: {}\nedges: []\n")
    )
    errs = pairs(check(tmp_path, "nodes:\n  a: {fn: t.step}\nedges:\n  - a -> END\n"))
    assert any(p == "edges" and "START" in m for p, m in errs)


def test_unknown_state_fn_router_and_agent(tmp_path: Path) -> None:
    text = (
        "nodes:\n  a: {fn: t.nope}\n  r: {agent: ghost, input: q, output: d}\n"
        "edges:\n  - START -> a -> r\n  - from: r\n    route: t.nah\n    to: {ok: END}\n"
    )
    f = tmp_path / "flow.yaml"
    f.write_text(HEAD.replace("t.S", "t.Missing") + text, encoding="utf-8")
    lib = Library.from_roots([tmp_path], pools())
    errs = pairs(validate_flow(parse_flow(f), lib, ModelRegistry.default(), file=str(f)))
    paths = [p for p, _ in errs]
    assert "state" in paths and "nodes.a.fn" in paths and "nodes.r.agent" in paths
    assert "edges[1].route" in paths
    assert any(p == "nodes.a.fn" and "t.step" in m for p, m in errs)  # known names listed


def test_invalid_agent_errors_surface_with_agent_path(tmp_path: Path) -> None:
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    (prompts / "p.md").write_text("hi", encoding="utf-8")
    agents = tmp_path / "agents"
    agents.mkdir()
    bad = agents / "bad.yaml"
    bad.write_text(
        "apiVersion: agentkit/v1\nkind: Agent\nname: bad\nmodel: fireworks-glm\n"
        "prompt: p\ntools: [nope]\n",
        encoding="utf-8",
    )
    body = (
        "nodes:\n  r: {agent: bad, input: q, output: d}\n  s: {agent: bad, input: d, output: e}\n"
        "edges:\n  - START -> r -> s -> END\n"
    )
    errs = check(tmp_path, body)
    hits = [e for e in errs if e.file == str(bad) and e.severity == "error"]
    assert len(hits) == 1  # one agent file used by two nodes: its errors are reported once
    assert hits[0].path == "tools[0]" and "nope" in hits[0].message


def test_flow_roots_add_app_dir_and_dedupe(tmp_path: Path) -> None:
    app = tmp_path / "apps" / "x"
    (app / "flows").mkdir(parents=True)
    (tmp_path / "libraries").mkdir()
    f = app / "flows" / "f.yaml"
    f.write_text("", encoding="utf-8")
    roots = flow_roots(f)
    assert roots == [app / "flows", app, tmp_path / "libraries"]
    assert len(set(roots)) == len(roots)
