from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .context import PlatformContext
from .registry import ModelSpec
from .settings import Settings


@dataclass(frozen=True)
class BuildContext:
    """What a pool factory may read when building a tool or middleware."""

    settings: Settings
    model: ModelSpec
    agent_name: str
    platform: PlatformContext | None = None  # build-time only; nothing requires it yet
    # The library roots the agent was validated against (`Library.roots`), so factories that
    # look up library files (e.g. connectors) resolve exactly what validate checked.
    library_roots: tuple[Path, ...] | None = None
