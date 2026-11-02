from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from agentkit_config.errors import SpecError, SpecErrors
from agentkit_config.spec.common import ToolRef, load_yaml

API_VERSION = "agentkit/v1"
_UNION_TAGS = {"str", "SubAgentSpec"}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MiddlewareRef(_Strict):
    type: str
    params: dict[str, Any] = {}
    enabled: bool = True


class SubAgentSpec(_Strict):
    apiVersion: str = API_VERSION
    kind: Literal["SubAgent"] = "SubAgent"
    name: str
    description: str
    prompt: str
    tools: list[ToolRef] = []
    skills: list[str] = []
    middleware: list[MiddlewareRef] = []
    model: str | None = None
    tier: str | None = None
    response_schema: str | None = None

    @field_validator("apiVersion")
    @classmethod
    def _check_version(cls, v: str) -> str:
        if v != API_VERSION:
            raise ValueError(f"apiVersion must be {API_VERSION!r}, got {v!r}")
        return v


SubagentEntry = str | SubAgentSpec


class AgentSpec(_Strict):
    apiVersion: Literal["agentkit/v1"]
    kind: Literal["Agent"]
    name: str
    description: str = ""
    version: str = "0.1.0"
    tags: list[str] = []
    model: str
    tier: str = "default"
    selection: Literal["decisions"] | None = None
    prompt: str
    tools: list[ToolRef] = []
    skills: list[str] = []
    subagents: list[SubagentEntry] = []
    middleware: list[MiddlewareRef] = []
    output: str | None = None


def _format_loc(loc: tuple[int | str, ...]) -> str:
    out = ""
    for part in loc:
        if isinstance(part, int):
            out += f"[{part}]"
        else:
            out += f".{part}" if out else part
    return out


def _to_spec_errors(exc: ValidationError, file: str) -> SpecErrors:
    errors = exc.errors()
    # A subagent entry is `str | SubAgentSpec`; when the model branch reported problems the
    # str-branch complaint is noise.
    model_entries = {
        tuple(e["loc"][: e["loc"].index("SubAgentSpec")])
        for e in errors
        if "SubAgentSpec" in e["loc"]
    }
    out: list[SpecError] = []
    for e in errors:
        loc = tuple(e["loc"])
        if "str" in loc and loc[: loc.index("str")] in model_entries:
            continue
        loc = tuple(p for p in loc if p not in _UNION_TAGS)
        out.append(SpecError(file, _format_loc(loc), e["msg"]))
    return SpecErrors(out)


def _parse[M: BaseModel](path: Path, model: type[M]) -> M:
    data = load_yaml(path)
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise _to_spec_errors(exc, str(path)) from exc


def parse_agent(path: Path) -> AgentSpec:
    return _parse(path, AgentSpec)


def parse_subagent(path: Path) -> SubAgentSpec:
    return _parse(path, SubAgentSpec)
