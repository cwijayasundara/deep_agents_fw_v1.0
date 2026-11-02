from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from agentkit_config.registry import Registry
from agentkit_config.spec import SubAgentSpec, parse_subagent


class SubagentRegistry:
    @staticmethod
    def from_roots(roots: Sequence[Path]) -> Registry[SubAgentSpec]:
        reg: Registry[SubAgentSpec] = Registry("subagent")
        for root in roots:
            for path in sorted((root / "subagents").glob("*.yaml")):
                spec = parse_subagent(path)
                reg.register(spec.name, spec, source=str(path))
        return reg
