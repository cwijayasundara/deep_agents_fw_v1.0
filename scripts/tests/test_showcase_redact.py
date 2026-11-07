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


def test_scrub_drops_denylisted_and_path_keys():
    root = str(redact.ROOT)
    obj = {"AES key rotation": 1, f"{root}/x": 2, "ok": {"Open items": 3, "fine": 4}}
    assert scrub(obj) == {"ok": {"fine": 4}}
    assert scrub("key rotation") is None


def test_assert_clean_is_case_insensitive():
    for bad in ("KEY ROTATION", "see open items here"):
        with pytest.raises(ValueError):
            assert_clean(bad)


def test_embedded_root_path_is_machine_state():
    root = str(redact.ROOT)
    assert scrub({"a": f"see {root}/apps"}) == {}
    long = (
        "Intro sentence that is harmless and goes on. " * 3
        + f"Edit {root}/a. "
        + "Tail is fine. " * 10
    )
    out = scrub(long)
    assert root not in out and "Tail is fine" in out
    assert redact.contains_local_path(f"x {root}")
    with pytest.raises(ValueError):
        assert_clean(f"<p>{root}</p>")


def test_policy_parsing_and_missing_key(tmp_path):
    f = tmp_path / "t.env"
    f.write_text('AGENTKIT_ALLOWED_SIDE_EFFECTS="read, write"  # note\n')
    assert example_tenant_policy(f) == ["read", "write"]
    f.write_text("OTHER=1\n")
    with pytest.raises(ValueError):
        example_tenant_policy(f)
