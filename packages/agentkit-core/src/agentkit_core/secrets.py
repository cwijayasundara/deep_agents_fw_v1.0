"""The `agentkit.secrets` seam: `<scheme>://<name>` refs resolved by named providers."""

from __future__ import annotations

import os
from typing import Protocol

from .seams import Seam, provider
from .settings import ConfigError, Settings


class SecretsProvider(Protocol):
    def resolve(self, name: str) -> str:
        """Return the secret for `name` (the part after `scheme://`)."""
        ...


class _EnvSecrets:
    def resolve(self, name: str) -> str:
        value = os.environ.get(name)
        if not value:
            raise ConfigError(f"secret env://{name} is not set")
        return value


@provider(owner="platform", version="1.0.0")
def env_secrets(settings: Settings) -> SecretsProvider:
    """`env://VAR`. Errors name the variable, never a value."""
    return _EnvSecrets()


SECRETS: Seam[SecretsProvider] = Seam("agentkit.secrets", "secrets")


def resolve_secret(ref: str, settings: Settings) -> str:
    scheme, sep, name = ref.partition("://")
    if not sep or not scheme or not name:
        raise ConfigError(f"unsupported secret ref {ref!r}: expected <scheme>://<name>")
    try:
        factory = SECRETS.get(scheme, settings.deployment_tenant)
    except ConfigError as e:
        raise ConfigError(f"unsupported secret ref scheme {scheme!r}: {e}") from e
    return factory(settings).resolve(name)
