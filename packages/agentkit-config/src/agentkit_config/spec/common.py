from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from agentkit_config.errors import SpecError, SpecErrors, read_utf8

Ref = str


def load_yaml(path: Path) -> dict[str, Any]:
    """Read a YAML mapping; every failure becomes a SpecErrors naming the file."""
    file = str(path)
    try:
        data = yaml.safe_load(read_utf8(path))
    except yaml.YAMLError as exc:
        raise SpecErrors([SpecError(file, "", f"YAML syntax error: {exc}")]) from exc
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


def format_loc(loc: tuple[int | str, ...]) -> str:
    """Render a pydantic error location as `nodes.review` / `edges[2]`."""
    out = ""
    for part in loc:
        if isinstance(part, int):
            out += f"[{part}]"
        else:
            out += f".{part}" if out else part
    return out


def to_spec_errors(
    exc: ValidationError, file: str, tags: frozenset[str] = frozenset()
) -> SpecErrors:
    """Convert a ValidationError, dropping union-tag segments named in `tags` from the path."""
    return SpecErrors(
        [
            SpecError(file, format_loc(tuple(p for p in e["loc"] if p not in tags)), e["msg"])
            for e in exc.errors()
        ]
    )


def parse_model[M: BaseModel](
    path: Path,
    model: type[M],
    convert: Callable[[ValidationError, str], SpecErrors] = to_spec_errors,
) -> M:
    """Load YAML and validate it against `model`; failures become SpecErrors naming the file."""
    data = load_yaml(path)
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise convert(exc, str(path)) from exc
