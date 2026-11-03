from importlib.metadata import EntryPoint
from pathlib import Path

import pytest
from agentkit_core import ConfigError, Seam, provider, provider_meta
from agentkit_core import seams as seams_mod

GROUP = "agentkit.test_seam"


def _ep(name: str, attr: str) -> EntryPoint:
    return EntryPoint(name, f"tests_seam_fixtures:{attr}", GROUP)


@pytest.fixture
def seam(monkeypatch):
    # --import-mode=importlib keeps the tests dir off sys.path; add it for EntryPoint.load.
    monkeypatch.syspath_prepend(str(Path(__file__).parent))
    eps = [_ep("alpha", "alpha"), _ep("beta", "beta_b_only")]
    monkeypatch.setattr(seams_mod, "entry_points", lambda group: eps)
    return Seam[str](GROUP, "test")


def test_get_returns_the_factory(seam):
    import tests_seam_fixtures

    assert seam.get("alpha", "tenant-a") is tests_seam_fixtures.alpha
    assert seam.get("beta", "tenant-b") is tests_seam_fixtures.beta_b_only


def test_names_hide_other_tenants_providers(seam):
    assert seam.names("tenant-a") == ["alpha"]
    assert seam.names("tenant-b") == ["alpha", "beta"]


def test_restricted_provider_error_names_tenant(seam):
    with pytest.raises(
        ConfigError, match="test provider 'beta' is not available to tenant 'tenant-a'"
    ):
        seam.get("beta", "tenant-a")


def test_unknown_provider_lists_known(seam):
    with pytest.raises(ConfigError, match=r"unknown test provider 'nope'; known: alpha$"):
        seam.get("nope", "tenant-a")


def test_duplicate_names_fail_naming_both_entry_points(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parent))
    eps = [_ep("alpha", "alpha"), _ep("alpha", "alpha_again")]
    monkeypatch.setattr(seams_mod, "entry_points", lambda group: eps)
    s = Seam[str](GROUP, "test")
    with pytest.raises(ConfigError) as ei:
        s.names("tenant-a")
    msg = str(ei.value)
    assert "duplicate test provider 'alpha'" in msg
    assert "tests_seam_fixtures:alpha" in msg and "tests_seam_fixtures:alpha_again" in msg


def test_provider_meta_validates_version():
    with pytest.raises(ValueError):
        provider(owner="x", version="1.0")

    @provider(owner="x", version="1.2.3")
    def f(settings): ...

    assert provider_meta(f).version == "1.2.3"
    assert provider_meta(lambda s: s) is None
