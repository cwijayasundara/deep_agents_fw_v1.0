from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from agentkit_config.errors import read_utf8
from agentkit_config.pools.frontmatter import split_front_matter
from agentkit_config.registry import Registry

ALLOWED_VARS = {"agent_name", "date"}
_VAR = re.compile(r"\{\{\s*(\w+)\s*\}\}")


@dataclass(frozen=True)
class Prompt:
    name: str
    text: str
    source: str


def variables(text: str) -> set[str]:
    return set(_VAR.findall(text))


def render(prompt: Prompt, *, agent_name: str, date: str) -> str:
    values = {"agent_name": agent_name, "date": date}
    return _VAR.sub(lambda m: values.get(m.group(1), m.group(0)), prompt.text)


class PromptRegistry:
    @staticmethod
    def from_roots(roots: Sequence[Path]) -> Registry[Prompt]:
        reg: Registry[Prompt] = Registry("prompt")
        for root in roots:
            base = root / "prompts"
            for path in sorted(base.glob("**/*.md")):
                name = path.relative_to(base).with_suffix("").as_posix()
                _, body = split_front_matter(read_utf8(path), file=str(path))
                prompt = Prompt(name, body.rstrip("\n"), str(path))
                reg.register(name, prompt, source=str(path))
        return reg
