"""Governance metadata for tool pool factories, and the checks a tool must pass."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from typing import Any, Literal, TypeVar

from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, field_validator

F = TypeVar("F", bound=Callable[..., Any])

_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
_RUNTIME_ARGS = frozenset({"tenant", "tenant_id", "user", "user_id", "thread_id"})
_ATTR = "__agentkit_tool__"


class ToolMeta(BaseModel):
    """Who owns a tool, which tenants may use it, and what it can touch."""

    model_config = ConfigDict(frozen=True)

    owner: str
    version: str
    tenants: frozenset[str] | None = None  # None: every tenant
    side_effects: Literal["read", "write", "external"]
    identity: Literal["service", "user"] = "service"
    classification: Literal["public", "internal", "confidential"] = "internal"
    examples: tuple[dict[str, Any], ...] = ()

    @field_validator("version")
    @classmethod
    def _semver(cls, v: str) -> str:
        if not _SEMVER.match(v):
            raise ValueError(f"version {v!r} must be MAJOR.MINOR.PATCH integers")
        return v


def platform_tool(
    *,
    owner: str,
    version: str,
    side_effects: Literal["read", "write", "external"],
    tenants: Iterable[str] | None = None,
    identity: Literal["service", "user"] = "service",
    classification: Literal["public", "internal", "confidential"] = "internal",
    examples: Iterable[dict[str, Any]] = (),
) -> Callable[[F], F]:
    """Attach `ToolMeta` to a tool factory `(ctx, **params) -> BaseTool`."""
    meta = ToolMeta(
        owner=owner,
        version=version,
        tenants=None if tenants is None else frozenset(tenants),
        side_effects=side_effects,
        identity=identity,
        classification=classification,
        examples=tuple(examples),
    )

    def decorate(factory: F) -> F:
        setattr(factory, _ATTR, meta)
        return factory

    return decorate


def tool_meta(factory: Callable[..., Any]) -> ToolMeta | None:
    meta = getattr(factory, _ATTR, None)
    return meta if isinstance(meta, ToolMeta) else None


def check_tool_contract(tool: BaseTool) -> list[str]:
    """Return the problems with a built tool; an empty list means it conforms."""
    problems: list[str] = []
    if not (tool.description or "").strip():
        problems.append("empty description")
    schema = tool.tool_call_schema
    json_schema: dict[str, Any] = (
        schema if isinstance(schema, dict) else schema.model_json_schema()  # type: ignore[union-attr]
    )
    props: dict[str, Any] = json_schema.get("properties", {})
    for name, prop in props.items():
        if name in _RUNTIME_ARGS:
            problems.append(f"argument '{name}' must come from runtime context")
        if not str(prop.get("description", "")).strip():
            problems.append(f"argument '{name}' has no description")
    return problems
