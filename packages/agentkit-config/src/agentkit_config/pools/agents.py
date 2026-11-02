from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from agentkit_config.errors import SpecError, SpecErrors
from agentkit_config.registry import Registry
from agentkit_config.spec import load_yaml


def _agent_name(path: Path) -> str:
    name = load_yaml(path).get("name")
    if not isinstance(name, str) or not name:
        raise SpecErrors([SpecError(str(path), "name", "missing or not a string")])
    return name


class AgentFileRegistry:
    @staticmethod
    def from_roots(roots: Sequence[Path]) -> Registry[Path]:
        reg: Registry[Path] = Registry("agent")
        for root in roots:
            paths = sorted((root / "agents").glob("*.yaml"))
            if (root / "agent.yaml").is_file():
                paths.append(root / "agent.yaml")
            for path in paths:
                reg.register(_agent_name(path), path, source=str(path))
        return reg
