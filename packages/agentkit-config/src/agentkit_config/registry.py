from __future__ import annotations

from collections.abc import Mapping

from agentkit_config.errors import SpecError, SpecErrors


class Registry[T]:
    """Named values of one kind (prompt, skill, ...) with duplicate and unknown-name errors."""

    def __init__(self, kind: str, entries: Mapping[str, T] | None = None) -> None:
        self.kind = kind
        self._entries: dict[str, T] = dict(entries or {})
        self._sources: dict[str, str] = {name: "<preset>" for name in self._entries}

    def register(self, name: str, value: T, *, source: str) -> None:
        if name in self._entries:
            first = self._sources[name]
            msg = f"duplicate {self.kind} {name!r}: defined in both {first} and {source}"
            raise SpecErrors([SpecError(source, "", msg)])
        self._entries[name] = value
        self._sources[name] = source

    def get(self, name: str, *, file: str, path: str) -> T:
        if name not in self._entries:
            known = ", ".join(self.names()) or "(none)"
            msg = f"unknown {self.kind} {name!r}; known: {known}"
            raise SpecErrors([SpecError(file, path, msg)])
        return self._entries[name]

    def names(self) -> list[str]:
        return sorted(self._entries)

    def __contains__(self, name: object) -> bool:
        return name in self._entries

    def replaced(self, overrides: Mapping[str, T]) -> Registry[T]:
        new = Registry[T](self.kind, self._entries)
        new._sources = dict(self._sources)
        for name, value in overrides.items():
            new._entries[name] = value
            new._sources[name] = "<override>"
        return new
