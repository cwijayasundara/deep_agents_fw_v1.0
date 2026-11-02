import pytest
from agentkit_core import PlatformContext, Settings, check_user_id, store_namespace
from pydantic import ValidationError


def ctx(**kw: str) -> PlatformContext:
    base = {
        "tenant": "acme",
        "product": "agentkit",
        "team": "platform",
        "user_id": "u1",
        "thread_id": "t-1",
        "agent_name": "research_agent",
        "agent_version": "0.1.0",
    }
    return PlatformContext(**{**base, **kw})


@pytest.mark.parametrize("field", ["tenant", "product", "team", "user_id", "agent_name"])
@pytest.mark.parametrize("bad", ["a.b", "", "Acme", "-x", "a" * 64])
def test_label_rejects_bad_values(field: str, bad: str) -> None:
    with pytest.raises(ValidationError, match=field):
        ctx(**{field: bad})


def test_label_accepts_dashes_underscores_and_digits() -> None:
    assert ctx(tenant="t-1_a", user_id="0").tenant == "t-1_a"


def test_store_namespace_user_and_global() -> None:
    c = ctx()
    assert store_namespace(c, "user", "memories") == (
        "acme",
        "agentkit",
        "platform",
        "u1",
        "memories",
    )
    assert store_namespace(c, "global", "org") == ("acme", "agentkit", "platform", "global", "org")


def test_store_namespace_rejects_dotted_kind() -> None:
    with pytest.raises(ValueError, match="kind"):
        store_namespace(ctx(), "user", "a.b")


def test_context_is_frozen() -> None:
    c = ctx()
    with pytest.raises(ValidationError):
        c.tenant = "other"  # type: ignore[misc]


def test_thread_id_and_version_are_free_text() -> None:
    c = ctx(thread_id="7c3e-UUID.ish", agent_version="1.2.3")
    assert c.thread_id == "7c3e-UUID.ish"


def test_deployment_tenant_defaults_and_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AGENTKIT_TENANT", raising=False)
    assert Settings(_env_file=None).deployment_tenant == "default"
    monkeypatch.setenv("AGENTKIT_TENANT", "acme")
    assert Settings(_env_file=None).deployment_tenant == "acme"
    assert Settings(_env_file=None, deployment_tenant="beta").deployment_tenant == "beta"


def test_deployment_tenant_must_be_a_label(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENTKIT_TENANT", "acme.corp")
    with pytest.raises(ValidationError, match="AGENTKIT_TENANT|deployment_tenant"):
        Settings(_env_file=None)


def test_build_context_platform_is_optional() -> None:
    from agentkit_core import BuildContext, ModelSpec, Provider

    b = BuildContext(Settings(_env_file=None), ModelSpec(Provider.ANTHROPIC, "m"), "a")
    assert b.platform is None
    assert BuildContext(b.settings, b.model, "a", platform=ctx()).platform == ctx()


def test_user_id_global_is_reserved() -> None:
    """Ruling P8: `global` is store_namespace's tenant-wide owner slot, never a user."""
    with pytest.raises(ValidationError, match="user_id") as ei:
        ctx(user_id="global")
    assert "reserved" in str(ei.value)
    with pytest.raises(ValueError, match="reserved"):
        check_user_id("global")
    assert check_user_id("u1") == "u1"
