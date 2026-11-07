from __future__ import annotations

import pytest
from showcase import redact
from showcase.redact import DENYLIST, assert_clean, example_tenant_policy, scrub


def test_scrub_drops_denylisted_items():
    obj = {"notes": ["fine item", "Pending AES key rotation work", "also fine"], "x": "P10 open"}
    out = scrub(obj)
    assert out == {"notes": ["fine item", "also fine"]}
    assert obj["notes"][1].startswith("Pending")  # input untouched


def test_scrub_strips_machine_state():
    root = str(redact.ROOT)
    obj = {
        "env": {"A": 1},
        "env_keys": {"FIREWORKS_API_KEY": True},
        "keys_set": ["A"],
        "dotenv": ["B"],
        "dsn": "postgresql://x",
        "key_env": "OPENAI_API_KEY",
        "key_set": True,
        "allowed_side_effects": "write",
        "path": f"{root}/apps/x",
        "models": [{"name": "m", "key_env": "K", "key_set": False}],
        "keep": "relative/path",
    }
    assert scrub(obj) == {"models": [{"name": "m"}], "keep": "relative/path"}


def test_denylist_scrubbed_from_replay_and_report():
    text = (
        "The platform ships a guard tier for every tool call and records spans. "
        "Operators still owe key rotation for the AES key. "
        "Each tenant gets its own Postgres and a stamped environment file for deployment. "
        "Evals gate every change before it merges into the main branch of the repository."
    )
    assert len(text) > 200
    out = scrub({"report": text})["report"]
    assert_clean(out)
    assert "guard tier" in out and "stamped environment" in out and "Evals gate" in out
    assert "rotation" not in out
    with pytest.raises(ValueError, match="key rotation"):
        assert_clean(text)


def test_denylist_has_all_phrases():
    assert "P3 " in DENYLIST and len(DENYLIST) == 13


def test_example_tenant_policy():
    assert example_tenant_policy() == ["read", "external"]


def test_policy_ignores_os_environ(monkeypatch):
    monkeypatch.setenv("AGENTKIT_ALLOWED_SIDE_EFFECTS", "write")
    assert example_tenant_policy() == ["read", "external"]
