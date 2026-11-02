from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, model_validator

from agentkit_config.errors import SpecError, SpecErrors

Ref = str


def load_yaml(path: Path) -> dict[str, Any]:
    """Read a YAML mapping; every failure becomes a SpecErrors naming the file."""
    file = str(path)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise SpecErrors([SpecError(file, "", f"YAML syntax error: {exc}")]) from exc
    except OSError as exc:
        raise SpecErrors([SpecError(file, "", f"cannot read file: {exc}")]) from exc
    if data is None:
        raise SpecErrors([SpecError(file, "", "file is empty")])
    if not isinstance(data, dict):
        kind = type(data).__name__
        raise SpecErrors([SpecError(file, "", f"top level must be a mapping, got {kind}")])
    return data


class ToolRef(BaseModel):
    """A tool by name, optionally with params: `web_search` or `{fetch_url: {max_chars: 1}}`."""

    model_config = ConfigDict(extra="forbid")

    name: str
    params: dict[str, Any] = {}

    def __init__(self, name: str | None = None, params: dict[str, Any] | None = None, **kw: Any):
        if name is not None:
            kw["name"] = name
        if params is not None:
            kw["params"] = params
        super().__init__(**kw)

    @model_validator(mode="before")
    @classmethod
    def _from_shorthand(cls, value: Any) -> Any:
        if isinstance(value, str):
            return {"name": value}
        if isinstance(value, dict) and "name" not in value and len(value) == 1:
            ((name, params),) = value.items()
            if params is None:
                params = {}
            if not isinstance(params, dict):
                raise ValueError(f"params for {name!r} must be a mapping")
            return {"name": name, "params": params}
        return value
