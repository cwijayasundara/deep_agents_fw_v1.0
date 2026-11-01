from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from .settings import ConfigError, Provider

TIERS = ("fast", "default", "strong")


@dataclass(frozen=True)
class ModelSpec:
    provider: Provider
    model_id: str
    kwargs: dict[str, Any] = field(default_factory=dict, hash=False, compare=False)


class ModelRegistry:
    """Maps a logical entry name + tier to a concrete (provider, model id)."""

    def __init__(self, entries: dict[str, dict[str, Any]], default_entry: str | None = None):
        self._entries = entries
        self.default_entry = default_entry or next(iter(entries))

    @classmethod
    def from_yaml_text(cls, text: str) -> ModelRegistry:
        raw = yaml.safe_load(text) or {}
        models = raw.get("models")
        if not models:
            raise ConfigError("registry has no 'models'")
        return cls(models, raw.get("default_provider"))

    @classmethod
    def from_file(cls, path: str | Path) -> ModelRegistry:
        return cls.from_yaml_text(Path(path).read_text())

    @classmethod
    def default(cls) -> ModelRegistry:
        text = resources.files("agentkit_core").joinpath("models.yaml").read_text()
        return cls.from_yaml_text(text)

    def names(self) -> list[str]:
        return list(self._entries)

    def resolve(self, name: str | None = None, tier: str = "default") -> ModelSpec:
        name = name or self.default_entry
        if name not in self._entries:
            raise ConfigError(f"unknown model entry '{name}'; known: {', '.join(self._entries)}")
        if tier not in TIERS:
            raise ConfigError(f"unknown tier '{tier}'; expected one of {TIERS}")
        entry = self._entries[name]
        provider = Provider(entry.get("provider", name))
        return ModelSpec(provider, entry[tier], dict(entry.get("kwargs", {})))
