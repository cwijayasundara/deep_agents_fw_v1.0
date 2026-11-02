"""Cross-reference and graph-shape checks for a FlowSpec; never raises."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
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
    node: AgentNode, path: str, lib: Library, models: ModelRegistry, file: str
) -> list[SpecError]:
    if node.agent not in lib.agents:
        msg = f"unknown agent {node.agent!r}; known: {_known(lib.agents.names())}"
        return [SpecError(file, f"{path}.agent", msg)]
    agent_file = lib.agents.get(node.agent, file=file, path=f"{path}.agent")
    try:
        return validate_agent(parse_agent(agent_file), lib, models, file=str(agent_file))
    except SpecErrors as exc:
        return exc.errors


def _node_errors(spec: FlowSpec, lib: Library, models: ModelRegistry, file: str) -> list[SpecError]:
    schemas = lib.code.schemas if lib.code is not None else None
    fns = lib.code.nodes if lib.code is not None else None
    out = _pool_error(file, "state", "state schema", spec.state, schemas)
    for name, node in spec.nodes.items():
        path = f"nodes.{name}"
        if isinstance(node, FnNode):
            out += _pool_error(file, f"{path}.fn", "node fn", node.fn, fns)
        elif isinstance(node, AgentNode):
            out += _agent_errors(node, path, lib, models, file)
    return out


def _edge_errors(spec: FlowSpec, file: str) -> list[SpecError]:
    sources, targets = {*spec.nodes, START}, {*spec.nodes, END}
    out: list[SpecError] = []

    def bad(label: str, role: str, name: str, known: set[str]) -> None:
        msg = f"{label}: unknown {role} {name!r}; known: {_known(known)}"
        out.append(SpecError(file, "edges", msg))

    for e in spec.edges:
        if isinstance(e, Edge):
            label = f"edge '{e.source} -> {e.target}'"
            if e.source not in sources:
                bad(label, "source", e.source, sources)
            if e.target not in targets:
                bad(label, "target", e.target, targets)
            continue
        label = f"route from {e.source!r}"
        if e.source not in spec.nodes:
            bad(label, "source", e.source, set(spec.nodes))
        for key, target in e.to.items():
            if target not in targets:
                bad(f"{label} key {key!r}", "target", target, targets)
    return out


def _route_fn_errors(spec: FlowSpec, lib: Library, file: str) -> list[SpecError]:
    nodes = lib.code.nodes if lib.code is not None else None
    out: list[SpecError] = []
    for e in spec.edges:
        if not isinstance(e, Edge):
            out += _pool_error(file, "edges", "router", e.route, nodes)
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
    spec: FlowSpec, lib: Library, models: ModelRegistry, *, file: str
) -> list[SpecError]:
    """Collect every problem in a flow, including each referenced agent's own errors."""
    return (
        _node_errors(spec, lib, models, file)
        + _edge_errors(spec, file)
        + _route_fn_errors(spec, lib, file)
        + _shape_errors(spec, file)
    )
