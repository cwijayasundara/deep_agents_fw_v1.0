"""Pool-wide tool views: the `agentkit tools` listing and the tool schema snapshot."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agentkit_core import BuildContext, ModelRegistry, Settings
from langchain_core.tools import BaseTool

from agentkit_config.pools.code import CodePools, factory_meta, meta_dict


def list_lines(code: CodePools, tenant: str) -> list[str]:
    """One `name version side_effects classification owner tenants` line per tool for `tenant`."""
    lines: list[str] = []
    for name in code.tools.names():
        meta = factory_meta(code.tools.get(name, file="<tools>", path=name))
        if meta is None:
            lines.append(f"{name} - - - - *")
            continue
        m = meta_dict(meta)
        if m["tenants"] is not None and tenant not in m["tenants"]:
            continue
        tenants = ",".join(m["tenants"]) if m["tenants"] is not None else "*"
        cols = (name, m["version"], m["side_effects"], m["classification"], m["owner"], tenants)
        lines.append(" ".join(cols))
    return lines


def build_pool_tools(code: CodePools) -> dict[str, BaseTool]:
    """Build every pool tool with fake settings and its default params."""
    settings = Settings(_env_file=None, tavily_api_key="snapshot-fake")  # type: ignore[call-arg,arg-type]
    ctx = BuildContext(settings, ModelRegistry.default().resolve(), "snapshot")
    return {n: code.tools.get(n, file="<tools>", path=n)(ctx) for n in code.tools.names()}


def current_snapshot(code: CodePools) -> dict[str, Any]:
    """`{name: {"version": ..., "schema": ...}}` for the installed `agentkit.tools` pool."""
    out: dict[str, Any] = {}
    for name, tool in build_pool_tools(code).items():
        meta = factory_meta(code.tools.get(name, file="<tools>", path=name))
        schema = tool.tool_call_schema
        out[name] = {
            "version": meta.version if meta is not None else None,
            "schema": schema if isinstance(schema, dict) else schema.model_json_schema(),  # type: ignore[union-attr]
        }
    return out


def _major(version: str | None) -> int | None:
    return int(version.split(".")[0]) if version else None


def diff_snapshot(current: dict[str, Any], saved: dict[str, Any]) -> list[str]:
    """Problems between the live pool and the saved snapshot; empty means they agree."""
    fix = "run agentkit tools snapshot"
    out: list[str] = []
    for name in sorted(current.keys() | saved.keys()):
        if name not in saved:
            out.append(f"tool {name!r} is not in the snapshot; {fix}")
            continue
        if name not in current:
            out.append(f"tool {name!r} left the pool; {fix}")
            continue
        cur, old = current[name], saved[name]
        same_schema = cur["schema"] == old["schema"]
        if same_schema and cur["version"] == old["version"]:
            continue
        old_major = _major(old["version"])
        if not same_schema and _major(cur["version"]) == old_major:
            if old_major is None:
                out.append(f"schema of {name!r} changed; {fix}")
            else:
                new = f"{old_major + 1}.0.0"
                msg = f"schema of {name!r} changed; bump its major version "
                out.append(f"{msg}({old['version']} -> {new}) and {fix}")
        else:
            out.append(f"snapshot of {name!r} is stale; {fix}")
    return out


def default_snapshot_path() -> Path:
    """`tool_schemas.json` beside the agentkit-tools package (a source checkout)."""
    import importlib.util

    spec = importlib.util.find_spec("agentkit_tools")
    if spec is None or spec.origin is None:
        raise FileNotFoundError("agentkit-tools is not installed; pass --file")
    return Path(spec.origin).resolve().parents[2] / "tool_schemas.json"


def write_snapshot(path: Path, snap: dict[str, Any]) -> None:
    path.write_text(json.dumps(snap, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_snapshot(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data
