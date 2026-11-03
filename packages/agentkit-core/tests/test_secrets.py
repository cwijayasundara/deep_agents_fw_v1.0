import logging
from importlib.metadata import EntryPoint, entry_points
from pathlib import Path

import pytest
from agentkit_core import ConfigError, Settings, resolve_secret
from agentkit_core import seams as seams_mod


def test_env_ref_resolves(monkeypatch):
    monkeypatch.setenv("KB_X", "postgresql://u:hunter2@h/db")
    assert resolve_secret("env://KB_X", Settings()) == "postgresql://u:hunter2@h/db"


def test_missing_env_var_names_the_var_not_a_value(monkeypatch, caplog):
    monkeypatch.setenv("OTHER", "hunter2")
    monkeypatch.delenv("KB_MISSING", raising=False)
    with (
        caplog.at_level(logging.DEBUG),
        pytest.raises(ConfigError, match=r"secret env://KB_MISSING is not set"),
    ):
        resolve_secret("env://KB_MISSING", Settings())
    assert "hunter2" not in caplog.text


def test_ref_without_scheme_is_rejected():
    with pytest.raises(ConfigError, match=r"expected <scheme>://<name>"):
        resolve_secret("KB_X", Settings())


def test_unknown_scheme_is_unsupported():
    with pytest.raises(ConfigError, match="unsupported secret ref scheme 'vault'"):
        resolve_secret("vault://x", Settings())


def test_fake_scheme_resolves_through_entry_points(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parent))
    fake = EntryPoint("test", "tests_seam_fixtures:fake_secrets", "agentkit.secrets")
    real = list(entry_points(group="agentkit.secrets"))
    monkeypatch.setattr(seams_mod, "entry_points", lambda group: [*real, fake])
    assert resolve_secret("test://k", Settings()) == "v-k"
