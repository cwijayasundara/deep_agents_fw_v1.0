from __future__ import annotations

import os
from typing import Protocol

from agentkit_core import ConfigError


class SecretsProvider(Protocol):
    def resolve(self, ref: str) -> str: ...


class EnvSecrets:
    """`env://VAR` only. Errors name the variable, never a value."""

    def resolve(self, ref: str) -> str:
        scheme, sep, name = ref.partition("://")
        if scheme != "env" or not sep or not name:
            raise ConfigError(
                f"unsupported secret ref scheme in '{scheme or ref}' (only env://VAR)"
            )
        value = os.environ.get(name)
        if not value:
            raise ConfigError(f"connector secret env://{name} is not set")
        return value
