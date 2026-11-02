from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from agentkit_config.errors import SpecError, SpecErrors, read_utf8
from agentkit_config.pools.frontmatter import split_front_matter
from agentkit_config.registry import Registry


@dataclass(frozen=True)
class Skill:
    name: str
    dir: Path
    tools: frozenset[str]


def _read_skill(skill_md: Path) -> Skill:
    file = str(skill_md)
    meta, _ = split_front_matter(read_utf8(skill_md), file=file)
    dirname = skill_md.parent.name
    if meta.get("name") != dirname:
        msg = f"front matter name {meta.get('name')!r} does not match directory {dirname!r}"
        raise SpecErrors([SpecError(file, "name", msg)])
    tools: set[str] = set()
    extra = meta.get("metadata") or {}
    if isinstance(extra, dict):
        tools.update(str(t) for t in extra.get("include_tools") or [])
    tools.update(str(meta.get("allowed-tools") or "").split())
    return Skill(dirname, skill_md.parent, frozenset(tools))


class SkillRegistry:
    @staticmethod
    def from_roots(roots: Sequence[Path]) -> Registry[Skill]:
        reg: Registry[Skill] = Registry("skill")
        for root in roots:
            for skill_md in sorted((root / "skills").glob("*/SKILL.md")):
                skill = _read_skill(skill_md)
                reg.register(skill.name, skill, source=str(skill_md))
        return reg
