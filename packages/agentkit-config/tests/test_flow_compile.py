from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, TypedDict

import pytest
from agentkit_config import CodePools, Library, SpecErrors
from agentkit_config.flow.compile import load_flow
from agentkit_config.flow.nodes import agent_node, interrupt_node
from agentkit_core import PlatformContext, Settings
from agentkit_deep.testing import ctx
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

HEAD = "apiVersion: agentkit/v1\nkind: Flow\nname: f\nstate: t.S\n"
INTERRUPT_FLOW = (
    "nodes:\n  a: {fn: t.step}\n  review: {interrupt: true}\n"
    "edges:\n  - START -> a -> review -> END\n"
)


class S(TypedDict, total=False):
    x: str
    n: int
    ok: str


def step(state: S) -> dict[str, Any]:
    return {"x": "stepped", "n": state.get("n", 0) + 1}


def who(state: S, runtime: Any) -> dict[str, Any]:
    return {"x": f"{runtime.context.tenant}/{runtime.context.thread_id}"}


def route(state: S) -> str:
    return "again" if state["n"] < 3 else "done"


def write(tmp_path: Path, body: str) -> tuple[Path, Library]:
    f = tmp_path / "flow.yaml"
    f.write_text(HEAD + body, encoding="utf-8")
    pools = CodePools.from_entry_points().override(
        schemas={"t.S": S}, nodes={"t.step": step, "t.route": route, "t.who": who}
    )
    return f, Library.from_roots([tmp_path], pools)


def settings() -> Settings:
    return Settings(_env_file=None)


async def test_fn_flow_with_router_loops_then_ends(tmp_path: Path) -> None:
    body = (
        "nodes:\n  a: {fn: t.step}\n"
        "edges:\n  - START -> a\n  - from: a\n    route: t.route\n    to: {again: a, done: END}\n"
    )
    f, lib = write(tmp_path, body)
    graph = load_flow(f, settings=settings(), library=lib)
    assert await graph.ainvoke({"n": 0}) == {"x": "stepped", "n": 3}


def test_validation_errors_raise(tmp_path: Path) -> None:
    f, lib = write(tmp_path, "nodes:\n  a: {fn: t.nope}\nedges:\n  - START -> a -> END\n")
    with pytest.raises(SpecErrors, match="t.nope"):
        load_flow(f, settings=settings(), library=lib)


def test_interrupt_requires_checkpointer(tmp_path: Path) -> None:
    f, lib = write(tmp_path, INTERRUPT_FLOW)
    with pytest.raises(SpecErrors, match="checkpointer") as ei:
        load_flow(f, settings=settings(), library=lib)
    assert ei.value.errors[0].path == "nodes.review"


async def test_interrupt_pauses_and_merges_mapping(tmp_path: Path) -> None:
    f, lib = write(tmp_path, INTERRUPT_FLOW)
    graph = load_flow(f, settings=settings(), library=lib, checkpointer=InMemorySaver())
    cfg = {"configurable": {"thread_id": "t"}}
    paused = await graph.ainvoke({"n": 0}, cfg)
    assert paused["__interrupt__"][0].value == {"node": "review"}
    done = await graph.ainvoke(Command(resume={"ok": "yes"}), cfg)
    assert done == {"x": "stepped", "n": 1, "ok": "yes"}


async def test_interrupt_resume_non_mapping_raises(tmp_path: Path) -> None:
    f, lib = write(tmp_path, INTERRUPT_FLOW)
    graph = load_flow(f, settings=settings(), library=lib, checkpointer=InMemorySaver())
    cfg = {"configurable": {"thread_id": "t"}}
    await graph.ainvoke({"n": 0}, cfg)
    with pytest.raises(TypeError, match="Mapping"):
        await graph.ainvoke(Command(resume="approve"), cfg)


def test_interrupt_node_payload_names_node() -> None:
    from unittest.mock import patch

    with patch("agentkit_config.flow.nodes.interrupt", return_value={"ok": "y"}) as fake:
        assert interrupt_node("review")({}) == {"ok": "y"}
    fake.assert_called_once_with({"node": "review"})


def test_missing_start_edge_is_spec_error(tmp_path: Path) -> None:
    f, lib = write(tmp_path, "nodes: {}\nedges: []\n")
    with pytest.raises(SpecErrors, match="edge from START"):
        load_flow(f, settings=settings(), library=lib)


class _Graph:
    def __init__(self) -> None:
        self.seen: list[str] = []

        self.contexts: list[object] = []

    async def ainvoke(self, inputs: dict[str, Any], *, context: object = None) -> dict[str, Any]:
        self.seen.append(inputs["messages"][0].content)
        self.contexts.append(context)
        return {"files": {"/out.md": {"content": ["line1", "line2"]}}}


RT: Any = SimpleNamespace(context=ctx())


class _Spec:
    output = "/out.md"


class _Loaded:
    def __init__(self) -> None:
        self.graph = _Graph()
        self.spec = _Spec()


async def test_agent_node_single_field_message() -> None:
    loaded = _Loaded()
    node = agent_node(loaded, "q", "d")  # type: ignore[arg-type]
    assert await node({"q": "what?"}, RT) == {"d": "line1\nline2"}
    assert loaded.graph.seen == ["what?"]


async def test_agent_node_sections_skip_missing_fields() -> None:
    loaded = _Loaded()
    node = agent_node(loaded, ["q", "c"], "d")  # type: ignore[arg-type]
    await node({"q": "what?"}, RT)
    await node({"q": "what?", "c": "add sources"}, RT)
    assert loaded.graph.seen == ["## q\nwhat?", "## q\nwhat?\n\n## c\nadd sources"]


async def test_agent_node_forwards_the_flow_context() -> None:
    loaded = _Loaded()
    c = ctx(tenant="acme", thread_id="flow-1")
    await agent_node(loaded, "q", "d")({"q": "what?"}, SimpleNamespace(context=c))  # type: ignore[arg-type]
    assert loaded.graph.contexts == [c]


async def test_flow_compiles_with_platform_context(tmp_path: Path) -> None:
    f, lib = write(tmp_path, "nodes:\n  a: {fn: t.who}\nedges:\n  - START -> a -> END\n")
    graph = load_flow(f, settings=settings(), library=lib)
    assert graph.context_schema is PlatformContext
    out = await graph.ainvoke({"n": 0}, context=ctx(tenant="acme", thread_id="th"))
    assert out["x"] == "acme/th"
