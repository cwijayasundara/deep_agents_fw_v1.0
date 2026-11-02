from __future__ import annotations

from functools import partial
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Discriminator,
    Field,
    Tag,
    field_validator,
    model_validator,
)

from agentkit_config.spec.common import parse_model, to_spec_errors

_NODE_KEYS = ("agent", "fn", "interrupt")
_NODE_TAGS = {"agent": "agent_node", "fn": "fn_node", "interrupt": "interrupt_node"}
_TAGS = frozenset({*_NODE_TAGS.values(), "edge_item", "route_item", "str", "list[str]"})
_PLAIN_EDGE_MSG = "plain edges must use the string form 'A -> B'; mappings need `route`"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class AgentNode(_Strict):
    agent: str
    input: str | Annotated[list[str], Field(min_length=1)]
    output: str


class FnNode(_Strict):
    fn: str


class InterruptNode(_Strict):
    interrupt: Literal[True]


def _node_tag(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    present = [k for k in _NODE_KEYS if k in value]
    return _NODE_TAGS[present[0]] if len(present) == 1 else None


NodeSpec = Annotated[
    Annotated[AgentNode, Tag("agent_node")]
    | Annotated[FnNode, Tag("fn_node")]
    | Annotated[InterruptNode, Tag("interrupt_node")],
    Discriminator(
        _node_tag,
        custom_error_type="node_kind",
        custom_error_message="node must have exactly one of: agent, fn, interrupt",
    ),
]


class Edge(_Strict):
    source: str
    target: str

    @model_validator(mode="before")
    @classmethod
    def _plain_mapping(cls, value: Any) -> Any:
        if isinstance(value, dict) and "from" in value:
            raise ValueError(_PLAIN_EDGE_MSG)
        return value


class Route(_Strict):
    source: str = Field(alias="from")
    route: str
    to: dict[str, str]


def _edge_tag(value: Any) -> str:
    if isinstance(value, dict) and "route" in value:
        return "route_item"
    if isinstance(value, Route):
        return "route_item"
    return "edge_item"


EdgeItem = Annotated[
    Annotated[Edge, Tag("edge_item")] | Annotated[Route, Tag("route_item")],
    Discriminator(_edge_tag),
]


def _expand_chain(text: str) -> list[Edge]:
    names = [n.strip() for n in text.split("->")]
    if len(names) < 2 or not all(names):
        raise ValueError(f"edge chain {text!r} needs at least two names, like 'A -> B'")
    return [Edge(source=a, target=b) for a, b in zip(names, names[1:], strict=False)]


class FlowSpec(_Strict):
    apiVersion: Literal["agentkit/v1"]
    kind: Literal["Flow"]
    name: str
    description: str = ""
    state: str
    nodes: dict[str, NodeSpec]
    edges: list[EdgeItem]

    @field_validator("edges", mode="before")
    @classmethod
    def _expand_strings(cls, value: Any) -> Any:
        if not isinstance(value, list):
            return value
        out: list[Any] = []
        for item in value:
            if isinstance(item, str):
                out.extend(_expand_chain(item))
            else:
                out.append(item)
        return out


def parse_flow(path: Path) -> FlowSpec:
    return parse_model(path, FlowSpec, partial(to_spec_errors, tags=_TAGS))
