"""Entry-point seams: named, versioned, optionally tenant-private provider factories."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from importlib.metadata import EntryPoint, entry_points
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, field_validator

from .settings import ConfigError, Settings

F = TypeVar("F", bound=Callable[..., Any])

_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
_ATTR = "__agentkit_provider__"


class ProviderMeta(BaseModel):
    """Who owns a provider and which tenants may use it (None = every tenant)."""

    model_config = ConfigDict(frozen=True)

    owner: str
    version: str
    tenants: frozenset[str] | None = None

    @field_validator("version")
    @classmethod
    def _semver(cls, v: str) -> str:
        if not _SEMVER.match(v):
            raise ValueError(f"version {v!r} must be MAJOR.MINOR.PATCH integers")
        return v


def provider(*, owner: str, version: str, tenants: Iterable[str] | None = None) -> Callable[[F], F]:
    """Attach ProviderMeta to a provider factory."""
    meta = ProviderMeta(
        owner=owner, version=version, tenants=None if tenants is None else frozenset(tenants)
    )

    def deco(fn: F) -> F:
        setattr(fn, _ATTR, meta)
        return fn

    return deco


def provider_meta(factory: object) -> ProviderMeta | None:
    return getattr(factory, _ATTR, None)


class Seam[T]:
    """A named extension point backed by an entry-point group."""

    def __init__(self, group: str, kind: str) -> None:
        self.group = group
        self.kind = kind

    def _discover(self) -> dict[str, EntryPoint]:
        found: dict[str, EntryPoint] = {}
        for ep in entry_points(group=self.group):
            if ep.name in found:
                raise ConfigError(
                    f"duplicate {self.kind} provider {ep.name!r}: "
                    f"{found[ep.name].value} and {ep.value}"
                )
            found[ep.name] = ep
        return found

    @staticmethod
    def _visible(factory: object, tenant: str) -> bool:
        meta = provider_meta(factory)
        return meta is None or meta.tenants is None or tenant in meta.tenants

    def names(self, tenant: str) -> list[str]:
        return sorted(
            name for name, ep in self._discover().items() if self._visible(ep.load(), tenant)
        )

    def get(self, name: str, tenant: str) -> Callable[[Settings], T]:
        found = self._discover()
        if name not in found:
            known = ", ".join(self.names(tenant)) or "(none)"
            raise ConfigError(f"unknown {self.kind} provider {name!r}; known: {known}")
        factory: Callable[[Settings], T] = found[name].load()
        if not self._visible(factory, tenant):
            raise ConfigError(
                f"{self.kind} provider {name!r} is not available to tenant {tenant!r}"
            )
        return factory
