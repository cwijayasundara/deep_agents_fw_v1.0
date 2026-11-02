from pathlib import Path

import pytest
from agentkit_config.errors import SpecErrors
from agentkit_config.spec import (
    AgentNode,
    Edge,
    FnNode,
    InterruptNode,
    Route,
    parse_flow,
)

SPEC_EXAMPLE = """\
apiVersion: agentkit/v1
kind: Flow
name: research_with_review
state: research.ReviewState            # state-schema pool
nodes:
  research: {agent: research_agent, input: question, output: draft}   # agent node
  critique: {fn: research.critique}                                    # function node
  review:   {interrupt: true}                                          # human-in-the-loop pause
edges:
  - START -> research -> critique
  - from: critique
    route: research.needs_rework       # router pool fn: state -> key
    to: {rework: research, ok: review}
  - review -> END
"""

HEAD = "apiVersion: agentkit/v1\nkind: Flow\nname: f\nstate: s.S\n"


def write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "flow.yaml"
    p.write_text(text)
    return p


def errors_of(tmp_path: Path, text: str) -> list[tuple[str, str]]:
    with pytest.raises(SpecErrors) as ei:
        parse_flow(write(tmp_path, text))
    return [(e.path, e.message) for e in ei.value.errors]


def test_parses_spec_example(tmp_path: Path) -> None:
    flow = parse_flow(write(tmp_path, SPEC_EXAMPLE))
    assert flow.name == "research_with_review"
    assert flow.state == "research.ReviewState"
    assert flow.nodes["research"] == AgentNode(
        agent="research_agent", input="question", output="draft"
    )
    assert flow.nodes["critique"] == FnNode(fn="research.critique")
    assert flow.nodes["review"] == InterruptNode(interrupt=True)
    assert flow.edges == [
        Edge(source="START", target="research"),
        Edge(source="research", target="critique"),
        Route(
            source="critique",
            route="research.needs_rework",
            to={"rework": "research", "ok": "review"},
        ),
        Edge(source="review", target="END"),
    ]


def test_chain_expands(tmp_path: Path) -> None:
    flow = parse_flow(write(tmp_path, HEAD + "nodes: {}\nedges:\n  - 'A->B  ->  C'\n"))
    assert flow.edges == [Edge(source="A", target="B"), Edge(source="B", target="C")]


def test_single_name_chain_error(tmp_path: Path) -> None:
    errs = errors_of(tmp_path, HEAD + "nodes: {}\nedges:\n  - A\n")
    assert errs and errs[0][0] == "edges" and "at least two names" in errs[0][1]


def test_node_with_two_kinds_error(tmp_path: Path) -> None:
    text = HEAD + "nodes:\n  a: {fn: x.y, interrupt: true}\n  b: {}\nedges: []\n"
    errs = errors_of(tmp_path, text)
    assert [p for p, _ in errs] == ["nodes.a", "nodes.b"]
    assert all("exactly one of" in m for _, m in errs)


def test_input_list_accepted(tmp_path: Path) -> None:
    text = HEAD + "nodes:\n  a: {agent: x, input: [q, ctx], output: o}\nedges: []\n"
    node = parse_flow(write(tmp_path, text)).nodes["a"]
    assert isinstance(node, AgentNode) and node.input == ["q", "ctx"]
    bad = HEAD + "nodes:\n  a: {agent: x, input: [], output: o}\nedges: []\n"
    assert errors_of(tmp_path, bad)[0][0] == "nodes.a.input"


def test_plain_mapping_edge_error(tmp_path: Path) -> None:
    errs = errors_of(tmp_path, HEAD + "nodes: {}\nedges:\n  - A -> B\n  - {from: A, to: {k: B}}\n")
    assert errs[0][0] == "edges[1]" and "string form" in errs[0][1]
