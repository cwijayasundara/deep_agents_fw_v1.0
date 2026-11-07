from __future__ import annotations

import random

import pytest
from agentkit_config.stack import STACK_ORDER
from platform_catalog import collect
from showcase.model import build_assembly, build_matrix

PARTS = [
    "model", "fallback", "prompt", "tools", "subagents", "connectors", "skills",
    "middleware", "guards", "memory", "tenant policy", "evals",
    "MCP", "HITL approval", "sandbox", "crons/ambient", "Slack/channel",
]  # fmt: skip


@pytest.fixture(scope="module")
def catalog() -> dict:
    return collect()


def _row(m: dict, part: str) -> dict:
    return next(r for r in m["rows"] if r["part"] == part)


def test_matrix_rows_and_agents(catalog) -> None:
    m = build_matrix(catalog["apps"])
    assert m["agents"] == ["kb_agent", "research_agent"]
    assert [r["part"] for r in m["rows"]] == PARTS


def test_guards_row_is_platform(catalog) -> None:
    assert _row(build_matrix(catalog["apps"]), "guards")["origin"] == "platform"


def test_tools_row_is_config(catalog) -> None:
    assert _row(build_matrix(catalog["apps"]), "tools")["origin"] == "config"


def test_skills_row_says_supported(catalog) -> None:
    cells = _row(build_matrix(catalog["apps"]), "skills")["cells"]
    assert set(cells.values()) == {"supported; none in library yet"}


def test_coming_rows_present(catalog) -> None:
    rows = [r for r in build_matrix(catalog["apps"])["rows"] if r["origin"] == "coming"]
    assert [r["part"] for r in rows] == PARTS[-5:]
    assert all(set(r["cells"].values()) == {"coming (Phase 2)"} for r in rows)


def test_matrix_handles_three_agents(catalog) -> None:
    base = catalog["apps"][0]
    apps = [{**base, "name": n} for n in ("c", "a", "b")]
    m = build_matrix(apps)
    assert m["agents"] == ["a", "b", "c"]
    assert all(len(r["cells"]) == 3 for r in m["rows"])
    assert _row(m, "guards")["origin"] == "platform"
    assert _row(m, "tools")["origin"] == "config"


def test_tool_ref_dict_renders_name_and_connector(catalog) -> None:
    cell = _row(build_matrix(catalog["apps"]), "tools")["cells"]["kb_agent"]
    assert "kb_search (kb-docs)" in cell
    assert "{" not in cell


def _app(catalog, name: str) -> dict:
    return next(a for a in catalog["apps"] if a["name"] == name)


def test_assembly_guards_first_and_fixed(catalog) -> None:
    layers = build_assembly(_app(catalog, "kb_agent"), catalog)["layers"]
    guards = [x for x in layers if x["kind"] == "guard"]
    assert guards and layers[: len(guards)] == guards
    assert all(g["fixed"] for g in guards)
    assert not any(x["fixed"] for x in layers if x["kind"] != "guard")
    assert not any(x["source"].startswith("/") for x in layers)


def test_assembly_middleware_in_stack_order(catalog) -> None:
    app = _app(catalog, "kb_agent")
    mws = list(app["spec"]["middleware"])
    random.Random(1).shuffle(mws)
    shuffled = {**app, "spec": {**app["spec"], "middleware": mws}}
    layers = build_assembly(shuffled, catalog)["layers"]
    types = [x["id"].split(":")[1] for x in layers if x["kind"] == "middleware"]
    rank = [STACK_ORDER.index(t) for t in types]
    assert rank == sorted(rank)
    assert len(set(x["id"] for x in layers)) == len(layers)


def test_every_part_line_links_to_a_layer(catalog) -> None:
    for app in catalog["apps"]:
        asm = build_assembly(app, catalog)
        ids = {x["id"] for x in asm["layers"]}
        linked = {ln["part_id"] for ln in asm["lines"] if ln["part_id"]}
        assert linked and linked <= ids
        assert len(asm["lines"]) == len(asm["yaml"].splitlines())
