"""Cross-reference and graph-shape checks for a FlowSpec; never raises."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from agentkit_core import ModelRegistry

from agentkit_config.errors import SpecError, SpecErrors
from agentkit_config.library import Library
from agentkit_config.registry import Registry
from agentkit_config.spec import AgentNode, Edge, FlowSpec, FnNode, parse_agent
from agentkit_config.validate import validate_agent

START, END = "START", "END"


def _known(names: Iterable[str]) -> str:
    return ", ".join(sorted(names)) or "(none)"


def _pool_error(
    file: str, path: str, kind: str, name: str, reg: Registry[Any] | None
) -> list[SpecError]:
    if reg is None:
        return [SpecError(file, path, f"no code pools loaded; cannot resolve {kind} {name!r}")]
    if name in reg:
        return []
    return [SpecError(file, path, f"unknown {kind} {name!r}; known: {_known(reg.names())}")]


def _agent_errors(
    node: AgentNode, path: str, lib: Library, models: ModelRegistry, file: str, tenant: str | None
) -> tuple[Path | None, list[SpecError]]:
    if node.agent not in lib.agents:
        msg = f"unknown agent {node.agent!r}; known: {_known(lib.agents.names())}"
        return None, [SpecError(file, f"{path}.agent", msg)]
    agent_file = lib.agents.get(node.agent, file=file, path=f"{path}.agent")
    try:
        errs = validate_agent(
            parse_agent(agent_file), lib, models, file=str(agent_file), tenant=tenant
        )
    except SpecErrors as exc:
        errs = exc.errors
    return agent_file, errs


def _node_errors(
    spec: FlowSpec, lib: Library, models: ModelRegistry, file: str, tenant: str | None
) -> list[SpecError]:
    schemas = lib.code.schemas if lib.code is not None else None
    fns = lib.code.nodes if lib.code is not None else None
    out = _pool_error(file, "state", "state schema", spec.state, schemas)
    checked: set[Path] = set()  # report each agent file's own errors once
    for name, node in spec.nodes.items():
        path = f"nodes.{name}"
        if isinstance(node, FnNode):
            out += _pool_error(file, f"{path}.fn", "node fn", node.fn, fns)
        elif isinstance(node, AgentNode):
            agent_file, errs = _agent_errors(node, path, lib, models, file, tenant)
            if agent_file not in checked:
                out += errs
            if agent_file is not None:
                checked.add(agent_file)
    return out


def _edge_errors(spec: FlowSpec, lib: Library, file: str) -> list[SpecError]:
    sources, targets = {*spec.nodes, START}, {*spec.nodes, END}
    routers = lib.code.nodes if lib.code is not None else None
    out: list[SpecError] = []

    def bad(path: str, role: str, name: str, known: set[str], where: str = "") -> None:
        msg = f"unknown {role} {name!r}{where}; known: {_known(known)}"
        out.append(SpecError(file, path, msg))

    for k, e in enumerate(spec.edges):
        p = f"edges[{spec.yaml_index(k)}]"
        if isinstance(e, Edge):
            where = f" in '{e.source} -> {e.target}'"
            if e.source not in sources:
                bad(p, "edge source", e.source, sources, where)
            if e.target not in targets:
                bad(p, "edge target", e.target, targets, where)
            continue
        if e.source not in spec.nodes:
            bad(f"{p}.from", "route source", e.source, set(spec.nodes))
        out += _pool_error(file, f"{p}.route", "router", e.route, routers)
        for key, target in e.to.items():
            if target not in targets:
                bad(f"{p}.to.{key}", "route target", target, targets)
    if not any(e.source == START for e in spec.edges):
        out.append(SpecError(file, "edges", "flow needs an edge from START, like 'START -> a'"))
    return out


def successors(spec: FlowSpec) -> dict[str, set[str]]:
    """Adjacency over plain edges and every route target."""
    graph: dict[str, set[str]] = {}
    for e in spec.edges:
        targets = {e.target} if isinstance(e, Edge) else set(e.to.values())
        graph.setdefault(e.source, set()).update(targets)
    return graph


def _reach(graph: Mapping[str, set[str]], start: str) -> set[str]:
    seen, todo = {start}, [start]
    while todo:
        for nxt in graph.get(todo.pop(), set()) - seen:
            seen.add(nxt)
            todo.append(nxt)
    return seen


def _shape_errors(spec: FlowSpec, file: str) -> list[SpecError]:
    forward = successors(spec)
    backward: dict[str, set[str]] = {}
    for src, dsts in forward.items():
        for dst in dsts:
            backward.setdefault(dst, set()).add(src)
    from_start, to_end = _reach(forward, START), _reach(backward, END)
    out: list[SpecError] = []
    for name in spec.nodes:
        if name not in from_start:
            out.append(SpecError(file, f"nodes.{name}", f"node {name!r} is unreachable from START"))
        if name not in to_end:
            out.append(SpecError(file, f"nodes.{name}", f"END is unreachable from node {name!r}"))
    return out


def validate_flow(
    spec: FlowSpec, lib: Library, models: ModelRegistry, *, file: str, tenant: str | None = None
) -> list[SpecError]:
    """Collect every problem in a flow, including each referenced agent's own errors.

    With `tenant`, tools restricted to other tenants are errors (as in `validate_agent`)."""
    return (
        _node_errors(spec, lib, models, file, tenant)
        + _edge_errors(spec, lib, file)
        + _shape_errors(spec, file)
    )
