from __future__ import annotations

import json
from pathlib import Path

import pytest
from platform_catalog import collect
from showcase.model import build_assembly
from showcase.replay import replay_from_spans

FIXTURE = Path(__file__).parent / "fixtures" / "spans_min.jsonl"
USAGE = [
    {"input_tokens": 1000, "output_tokens": 200, "decisions_input_tokens": 30, "cost_usd": 0.01},
    {"input_tokens": 500, "output_tokens": 100, "decisions_input_tokens": 0, "cost_usd": 0.005},
]


@pytest.fixture(scope="module")
def replay() -> dict:
    return replay_from_spans(FIXTURE, USAGE)


def test_events_ordered_and_typed(replay) -> None:
    ev = replay["events"]
    assert [e["t"] for e in ev] == sorted(e["t"] for e in ev)
    assert ev[0]["t"] >= 0
    kinds = {e["kind"] for e in ev}
    assert {"model", "tool", "subagent", "guard", "limit", "pii", "output"} <= kinds
    assert replay["question"].startswith("Compare platforms")
    assert replay["model"]
    pii = next(e for e in ev if e["kind"] == "pii")
    assert pii["part_id"] == "mw:pii:email" and "[REDACTED_EMAIL]" in pii["detail"]
    lim = next(e for e in ev if e["kind"] == "limit")
    assert lim["part_id"] == "mw:tool_call_limit:web_search"


def test_detail_truncated_to_240(replay) -> None:
    assert all(len(e["detail"]) <= 240 for e in replay["events"])
    assert any(len(e["detail"]) == 240 for e in replay["events"])  # the long model reply was cut


def test_part_ids_match_assembly_scheme(replay) -> None:
    cat = collect()
    app = next(a for a in cat["apps"] if a["name"] == "research_agent")
    ids = {layer["id"] for layer in build_assembly(app, cat)["layers"]} | {"output"}
    assert {e["part_id"] for e in replay["events"]} <= ids


def test_totals_sum_usage_rows(replay) -> None:
    assert replay["totals"] == {"tokens": 1830, "cost_usd": 0.015}


def test_cost_null_when_ledger_has_no_cost() -> None:
    rows = [{"input_tokens": 10, "output_tokens": 5}]
    assert replay_from_spans(FIXTURE, rows)["totals"] == {"tokens": 15, "cost_usd": None}


def test_subagent_model_calls_included(replay) -> None:
    sub = [e for e in replay["events"] if e["label"] == "researcher · model call"]
    assert len(sub) == 1
    assert sub[0]["kind"] == "model" and sub[0]["part_id"] == "model:fireworks-glm"


def test_secrets_and_dsns_absent(replay) -> None:
    raw = FIXTURE.read_text()
    assert "postgresql://" in raw and "sk-abcdef" in raw  # the fixture really holds them
    dump = json.dumps(replay)
    assert "postgresql://" not in dump and "sk-abcdef" not in dump


def test_main_agent_strong_tier_maps_to_primary_model(replay) -> None:
    main = [e for e in replay["events"] if e["kind"] == "model" and "model call" not in e["label"]]
    assert main and main[0]["label"] == "glm-5p3"  # non-flash, main agent
    assert all(e["part_id"] == "model:fireworks-glm" for e in main)
