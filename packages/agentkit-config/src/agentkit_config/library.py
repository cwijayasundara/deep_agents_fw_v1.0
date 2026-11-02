from __future__ import annotations

import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentkit_config.pools import (
    AgentFileRegistry,
    Prompt,
    PromptRegistry,
    Skill,
    SkillRegistry,
    SubagentRegistry,
)
from agentkit_config.registry import Registry
from agentkit_config.spec import SubAgentSpec


@dataclass(frozen=True)
class Library:
    roots: tuple[Path, ...]
    prompts: Registry[Prompt]
    skills: Registry[Skill]
    subagents: Registry[SubAgentSpec]
    agents: Registry[Path]
    code: Any | None = None  # CodePools, set by Task 4

    @classmethod
    def from_roots(cls, roots: Sequence[Path], code: Any | None = None) -> Library:
        rs = tuple(roots)
        return cls(
            rs,
            PromptRegistry.from_roots(rs),
            SkillRegistry.from_roots(rs),
            SubagentRegistry.from_roots(rs),
            AgentFileRegistry.from_roots(rs),
            code,
        )

    @classmethod
    def for_file(cls, path: Path, code: Any | None = None) -> Library:
        """Roots: the file's directory, nearest `libraries/` ancestor, AGENTKIT_LIBRARY_PATH."""
        here = path.resolve().parent
        candidates = [here]
        for ancestor in (here, *here.parents):
            if (ancestor / "libraries").is_dir():
                candidates.append(ancestor / "libraries")
                break
        env = os.environ.get("AGENTKIT_LIBRARY_PATH", "")
        candidates.extend(Path(p) for p in env.split(os.pathsep) if p)
        roots = [p for p in candidates if p.is_dir()]
        return cls.from_roots(roots, code)
