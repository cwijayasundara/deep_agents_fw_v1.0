"""flow.yaml -> compiled LangGraph StateGraph: parse -> validate -> build nodes/edges -> compile."""

from __future__ import annotations

import logging
from collections.abc import Hashable
from pathlib import Path
from typing import Any

from agentkit_core import ModelRegistry, Settings
from langchain_core.language_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from agentkit_config.errors import SpecError, SpecErrors
from agentkit_config.flow.nodes import agent_node, interrupt_node
from agentkit_config.flow.validate import validate_flow
from agentkit_config.library import Library
from agentkit_config.load import load_agent
from agentkit_config.pools.code import CodePools
from agentkit_config.spec import AgentNode, Edge, FlowSpec, FnNode, InterruptNode, parse_flow

log = logging.getLogger(__name__)
_ENDPOINTS = {"START": START, "END": END}


def flow_roots(flow_file: Path) -> list[Path]:
    """The flow's dir, its parent (an app dir holding agent.yaml), then the usual library roots."""
    here = flow_file.resolve().parent
    candidates = [here, here.parent, *Library.for_file(flow_file).roots[1:]]
    return [p for p in dict.fromkeys(candidates) if p.is_dir()]


def flow_library(flow_file: Path, code: CodePools | None = None) -> Library:
    return Library.from_roots(flow_roots(flow_file), code)


def _endpoint(name: str) -> str:
    return _ENDPOINTS.get(name, name)


def _require_checkpointer(spec: FlowSpec, file: str, checkpointer: Any) -> None:
    if checkpointer is not None:
        return
    msg = "interrupt nodes need a checkpointer; pass checkpointer= to load_flow"
    SpecErrors(
        [
            SpecError(file, f"nodes.{name}", msg)
            for name, node in spec.nodes.items()
            if isinstance(node, InterruptNode)
        ]
    ).raise_if_errors()


def _action(
    name: str,
    node: AgentNode | FnNode | InterruptNode,
    lib: Library,
    *,
    file: str,
    settings: Settings,
    model: BaseChatModel | None,
) -> Any:  # Any: node callables are typed by a state schema known only at runtime
    path = f"nodes.{name}"
    if isinstance(node, AgentNode):
        agent_file = lib.agents.get(node.agent, file=file, path=f"{path}.agent")
        loaded = load_agent(agent_file, settings=settings, library=lib, model=model)
        return agent_node(loaded, node.input, node.output)
    if isinstance(node, FnNode):
        assert lib.code is not None  # validation guarantees code pools for fn nodes
        return lib.code.nodes.get(node.fn, file=file, path=f"{path}.fn")
    return interrupt_node(name)


def _add_edges(graph: StateGraph[Any], spec: FlowSpec, lib: Library, *, file: str) -> None:
    assert lib.code is not None
    for k, e in enumerate(spec.edges):
        if isinstance(e, Edge):
            graph.add_edge(_endpoint(e.source), _endpoint(e.target))
        else:
            router = lib.code.nodes.get(
                e.route, file=file, path=f"edges[{spec.yaml_index(k)}].route"
            )
            path_map: dict[Hashable, str] = {key: _endpoint(target) for key, target in e.to.items()}
            graph.add_conditional_edges(e.source, router, path_map)


def load_flow(
    path: str | Path,
    *,
    settings: Settings,
    library: Library | None = None,
    model: BaseChatModel | None = None,
    checkpointer: BaseCheckpointSaver[Any] | None = None,
) -> CompiledStateGraph[Any, Any, Any, Any]:
    """Validate the whole flow (agents included) before building anything, then compile."""
    path = Path(path)
    file = str(path)
    lib = library if library is not None else flow_library(path, CodePools.from_entry_points())
    spec = parse_flow(path)
    problems = validate_flow(spec, lib, ModelRegistry.default(), file=file)
    for w in (p for p in problems if p.severity == "warning"):
        log.warning("%s", w)
    SpecErrors(problems).raise_if_errors()
    _require_checkpointer(spec, file, checkpointer)
    assert lib.code is not None
    state = lib.code.schemas.get(spec.state, file=file, path="state")
    graph: StateGraph[Any] = StateGraph(state)
    for name, node in spec.nodes.items():
        graph.add_node(name, _action(name, node, lib, file=file, settings=settings, model=model))
    _add_edges(graph, spec, lib, file=file)
    return graph.compile(checkpointer=checkpointer)
