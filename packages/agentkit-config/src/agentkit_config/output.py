from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def read_output(result: Mapping[str, Any], path: str | None) -> str:
    """The agent's answer: the file at `path` when set, else the last AI message."""
    if path is not None:
        f = result.get("files", {}).get(path)
        if f is None:
            return ""
        content = f["content"] if isinstance(f, dict) else f
        return "\n".join(content) if isinstance(content, list) else str(content)
    for msg in reversed(result.get("messages", [])):
        if getattr(msg, "type", None) == "ai":
            content = msg.content
            return content if isinstance(content, str) else str(content)
    return ""
