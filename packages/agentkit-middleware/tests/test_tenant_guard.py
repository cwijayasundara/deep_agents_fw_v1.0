from types import SimpleNamespace

import pytest
from agentkit_core import PlatformContext
from agentkit_middleware import MissingPlatformContext, TenantGuardMiddleware, TenantMismatch


def ctx(tenant: str) -> PlatformContext:
    return PlatformContext(
        tenant=tenant,
        product="agentkit",
        team="platform",
        user_id="u1",
        thread_id="t",
        agent_name="a",
        agent_version="0",
    )


def rt(context: object) -> object:
    return SimpleNamespace(context=context)


def test_match_passes() -> None:
    guard = TenantGuardMiddleware("acme")
    assert guard.before_agent({}, rt(ctx("acme"))) is None  # type: ignore[arg-type]


def test_mismatch_raises_with_both_tenants() -> None:
    guard = TenantGuardMiddleware("acme")
    with pytest.raises(TenantMismatch, match="run tenant 'other' != deployment tenant 'acme'"):
        guard.before_agent({}, rt(ctx("other")))  # type: ignore[arg-type]


def test_missing_context_raises() -> None:
    guard = TenantGuardMiddleware("acme")
    with pytest.raises(MissingPlatformContext, match="context=PlatformContext"):
        guard.before_agent({}, rt(None))  # type: ignore[arg-type]


def test_wrong_context_type_raises() -> None:
    guard = TenantGuardMiddleware("acme")
    with pytest.raises(MissingPlatformContext, match="dict"):
        guard.before_agent({}, rt({"tenant": "acme"}))  # type: ignore[arg-type]


def test_guard_rejects_bad_deployment_tenant() -> None:
    with pytest.raises(ValueError, match="deployment tenant"):
        TenantGuardMiddleware("acme.corp")
