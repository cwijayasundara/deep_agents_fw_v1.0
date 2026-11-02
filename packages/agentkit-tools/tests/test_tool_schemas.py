"""The whole installed `agentkit.tools` pool must match `tool_schemas.json` (ruling S1)."""

from __future__ import annotations

from pathlib import Path

from agentkit_config.pools.code import CodePools
from agentkit_config.toolpolicy import build_pool_tools, current_snapshot, diff_snapshot
from agentkit_tools import check_tool_contract

SNAPSHOT = Path(__file__).resolve().parents[1] / "tool_schemas.json"


def test_pool_matches_snapshot() -> None:
    import json

    saved = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    problems = diff_snapshot(current_snapshot(CodePools.from_entry_points()), saved)
    assert problems == []


def test_every_pool_tool_meets_the_contract() -> None:
    for name, tool in build_pool_tools(CodePools.from_entry_points()).items():
        assert check_tool_contract(tool) == [], name


def test_schema_change_without_major_bump_names_the_fix() -> None:
    saved = {"x": {"version": "1.2.0", "schema": {"properties": {"a": {}}}}}
    cur = {"x": {"version": "1.3.0", "schema": {"properties": {"b": {}}}}}
    assert diff_snapshot(cur, saved) == [
        "schema of 'x' changed; bump its major version (1.2.0 -> 2.0.0) and "
        "run agentkit tools snapshot"
    ]


def test_version_bump_with_same_schema_asks_for_snapshot() -> None:
    saved = {"x": {"version": "1.0.0", "schema": {"p": 1}}}
    cur = {"x": {"version": "2.0.0", "schema": {"p": 1}}}
    assert diff_snapshot(cur, saved) == ["snapshot of 'x' is stale; run agentkit tools snapshot"]


def test_major_bump_with_changed_schema_asks_for_snapshot() -> None:
    saved = {"x": {"version": "1.0.0", "schema": {"p": 1}}}
    cur = {"x": {"version": "2.0.0", "schema": {"p": 2}}}
    assert diff_snapshot(cur, saved) == ["snapshot of 'x' is stale; run agentkit tools snapshot"]
