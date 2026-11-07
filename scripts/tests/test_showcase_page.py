from __future__ import annotations

import json
import re

import pytest
from showcase import __main__ as page
from showcase.redact import DENYLIST, ROOT, assert_clean

KEYS = {
    "matrix",
    "assemblies",
    "bench",
    "replay",
    "report",
    "positioning",
    "generated_at",
    "git_sha",
}


def _data(html: str) -> dict:
    m = re.search(r'<script id="data" type="application/json">(.*?)</script>', html, re.DOTALL)
    assert m, "embedded data block missing"
    return json.loads(m.group(1))


@pytest.fixture(scope="module")
def snapshot() -> str:
    return page.render(snapshot=True)


def test_snapshot_is_self_contained(snapshot):
    assert "<script src=" not in snapshot
    assert '<link rel="stylesheet" href="http' not in snapshot
    assert not re.search(r"<(script|link|img|iframe)[^>]+(src|href)=[\"']https?:", snapshot)


def test_snapshot_has_no_denylisted_text(snapshot):
    assert_clean(snapshot)
    low = snapshot.lower()
    for phrase in DENYLIST:
        assert phrase.lower() not in low, phrase


def test_snapshot_has_no_machine_state(snapshot):
    for needle in ("FIREWORKS_API_KEY", '"machine"', str(ROOT)):
        assert needle not in snapshot, needle
    # Whole key only: the KB prerequisites legitimately name KB_DATABASE_URL (a kb_reader DSN).
    assert not re.search(r"(?<![A-Z_])DATABASE_URL", snapshot)


def test_embedded_data_round_trips(snapshot):
    data = _data(snapshot)
    assert set(data) == KEYS
    assert set(data["assemblies"]) == set(data["matrix"]["agents"])
    policy = next(r for r in data["matrix"]["rows"] if r["part"] == "tenant policy")
    assert set(policy["cells"].values()) == {"example tenant: read, external"}


def test_builds_without_replay(monkeypatch, tmp_path):
    monkeypatch.setattr(page, "REPLAY", tmp_path / "missing.json")
    monkeypatch.setattr(page, "REPORT", tmp_path / "missing.md")
    data = _data(page.render(snapshot=True))
    assert data["replay"] is None
    assert data["report"] is None


def test_serve_may_add_machine_block():
    data = _data(page.render(snapshot=False))
    assert set(data) == KEYS | {"machine"}


def test_coming_items_named(snapshot):
    positioning = _data(snapshot)["positioning"]
    rows = positioning["not_built"] + positioning["components"]
    for term in ("MCP", "HITL", "sandbox", "crons", "Slack"):
        hits = [r for r in rows if term.lower() in r["name"].lower()]
        assert hits, term
        assert all(r["agentkit"] == "coming" for r in hits), term
    assert "configuration bounded by guardrails the config cannot remove" in snapshot
