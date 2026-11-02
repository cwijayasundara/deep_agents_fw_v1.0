from __future__ import annotations

from dataclasses import dataclass

from .registry import ModelSpec
from .settings import Settings


@dataclass(frozen=True)
class BuildContext:
    """What a pool factory may read when building a tool or middleware."""

    settings: Settings
    model: ModelSpec
    agent_name: str
