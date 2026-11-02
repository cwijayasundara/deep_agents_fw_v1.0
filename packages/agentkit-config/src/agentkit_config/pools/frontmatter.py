from __future__ import annotations

from typing import Any

import yaml

from agentkit_config.errors import SpecError, SpecErrors


def split_front_matter(text: str, *, file: str) -> tuple[dict[str, Any], str]:
    """Split optional leading `---` YAML front matter from the body."""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, text
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            try:
                meta = yaml.safe_load("\n".join(lines[1:i]))
            except yaml.YAMLError as exc:
                raise SpecErrors([SpecError(file, "", f"bad front matter: {exc}")]) from exc
            if meta is None:
                meta = {}
            if not isinstance(meta, dict):
                raise SpecErrors([SpecError(file, "", "front matter must be a mapping")])
            return meta, "\n".join(lines[i + 1 :])
    return {}, text
