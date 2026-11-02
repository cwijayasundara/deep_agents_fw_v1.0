"""Suite-wide isolation from the ambient deployment tenant.

Tests assume the deployment tenant is "default". An exported AGENTKIT_TENANT, or one in the
repo `.env` (which `Settings` prefers over the process env), would otherwise leak into every
agent built in a test. Live tests keep the real `.env` (they need its API keys).
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from agentkit_core import Settings
from agentkit_deep.factory import _process_tenant


@pytest.fixture(autouse=True)
def _default_deployment_tenant(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    monkeypatch.delenv("AGENTKIT_TENANT", raising=False)
    if request.node.get_closest_marker("live") is None:
        monkeypatch.setitem(Settings.model_config, "env_file", None)
    _process_tenant.cache_clear()
    yield
    _process_tenant.cache_clear()


@pytest.fixture(autouse=True)
def _fresh_shared_breakers() -> Iterator[None]:
    """Process-wide circuit breakers must not carry failures from one test into the next."""
    from agentkit_middleware import reset_shared_breakers

    reset_shared_breakers()
    yield
    reset_shared_breakers()
