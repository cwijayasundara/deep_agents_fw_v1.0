from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from importlib.metadata import entry_points
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.tools import BaseTool

from agentkit_config.registry import Registry

ToolFactory = Callable[..., BaseTool]
MiddlewareFactory = Callable[..., AgentMiddleware]


def _load[T](group: str, kind: str) -> Registry[T]:
    reg = Registry[T](kind)
    for ep in entry_points(group=group):
        reg.register(ep.name, ep.load(), source=f"entry point {group}:{ep.name}")
    return reg


@dataclass(frozen=True)
class CodePools:
    """Python-registered pools, discovered through entry points."""

    tools: Registry[ToolFactory]
    middleware: Registry[MiddlewareFactory]
    nodes: Registry[Callable[..., Any]]
    schemas: Registry[type]

    @classmethod
    def from_entry_points(cls) -> CodePools:
        return cls(
            _load("agentkit.tools", "tool"),
            _load("agentkit.middleware", "middleware"),
            _load("agentkit.nodes", "node"),
            _load("agentkit.schemas", "schema"),
        )

    def override(self, **pools: Mapping[str, Any]) -> CodePools:
        """Replace named entries, e.g. `override(tools={"web_search": fake})`."""
        unknown = set(pools) - {"tools", "middleware", "nodes", "schemas"}
        if unknown:
            raise TypeError(f"unknown pool(s): {', '.join(sorted(unknown))}")
        return replace(self, **{k: getattr(self, k).replaced(v) for k, v in pools.items()})


def factory_meta(factory: Callable[..., Any]) -> Any | None:
    """The `@platform_tool` metadata of a pool factory, or None.

    Read duck-typed (`__agentkit_tool__`, a pydantic model) because agentkit-config does not
    depend on agentkit-tools."""
    meta = getattr(factory, "__agentkit_tool__", None)
    return meta if hasattr(meta, "model_dump") else None


def meta_dict(meta: Any) -> dict[str, Any]:
    """JSON-ready metadata with `tenants` sorted, so output is stable."""
    d: dict[str, Any] = meta.model_dump(mode="json")
    if d.get("tenants") is not None:
        d["tenants"] = sorted(d["tenants"])
    return d


def check_params(factory: Callable[..., Any], params: Mapping[str, Any]) -> str | None:
    """Return the TypeError message if `factory(ctx, **params)` can't bind, else None."""
    try:
        inspect.signature(factory).bind(None, **params)
    except TypeError as e:
        return str(e)
    return None


__all__ = [
    "CodePools",
    "MiddlewareFactory",
    "ToolFactory",
    "check_params",
    "factory_meta",
    "meta_dict",
]
