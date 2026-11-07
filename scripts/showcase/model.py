"""Data model for the showcase page: the recipe matrix and per-agent assembly.

Everything here is derived from the catalog (`platform_catalog.collect()`) and the app YAML;
nothing is hand-written per agent.

Layer ids (replay reuses them): `guard:<Class>`, `mw:<type>` (`mw:tool_call_limit:<tool>`,
`mw:pii:<pii type>` when a type repeats), `model:<name>`, `tool:<name>`, `subagent:<name>`.
"""

from __future__ import annotations

import importlib.metadata
import re
from pathlib import Path

from agentkit_config.stack import STACK_ORDER
from agentkit_deep import GUARD_LAYERS, MEMORY_ROUTES

ROOT = Path(__file__).resolve().parent.parent.parent
COMING = "coming (Phase 2)"
COMING_ROWS = ("MCP", "HITL approval", "sandbox", "crons/ambient", "Slack/channel")
GUARDS_SOURCE = "packages/agentkit-deep/src/agentkit_deep/factory.py"
MODELS_SOURCE = "packages/agentkit-core/src/agentkit_core/models.yaml"
_PLATFORM_PARTS = {"guards", "memory", "tenant policy"}


def _tool_name(ref) -> str:
    return ref if isinstance(ref, str) else next(iter(ref))


def _tool_label(ref) -> str:
    if isinstance(ref, str):
        return ref
    name = next(iter(ref))
    params = ref[name] or {}
    conn = params.get("connector") if isinstance(params, dict) else None
    return f"{name} ({conn})" if conn else name


def _fallback_models(spec: dict) -> list[str]:
    for m in spec.get("middleware") or []:
        if m.get("type") == "model_fallback":
            return list((m.get("params") or {}).get("models") or [])
    return []


def _join(items) -> str:
    items = list(items)
    return ", ".join(items) if items else "none"


def _mw_summary(types: list[str]) -> str:
    counts: dict[str, int] = {}
    for t in types:
        counts[t] = counts.get(t, 0) + 1
    return _join(f"{t} x{n}" if n > 1 else t for t, n in counts.items())


def _eval_summary(evals: list[dict]) -> str:
    cases = sum(e.get("cases", 0) for e in evals)
    gated = any(e.get("file") == "gates.yaml" for e in evals)
    if not cases and not gated:
        return "none"
    return f"{cases} cases" + ("; gated" if gated else "")


def build_matrix(apps: list[dict], skills: list[dict] | None = None) -> dict:
    """Rows of parts by agent; `origin` says whether the platform or the config supplies it."""
    apps = sorted(apps, key=lambda a: a["name"])
    skill_cell = _join(s["name"] for s in skills) if skills else "supported; none in library yet"
    guard_cell = ", ".join(g.name for g in GUARD_LAYERS)
    memory_cell = ", ".join(r.path for r in MEMORY_ROUTES)

    def per_app(fn) -> dict[str, str]:
        return {a["name"]: fn(a) for a in apps}

    def spec_of(a: dict) -> dict:
        return a.get("spec") or {}

    parts = [
        ("model", per_app(lambda a: _join([a["model"]] if a.get("model") else []))),
        ("fallback", per_app(lambda a: _join(_fallback_models(spec_of(a))))),
        ("prompt", per_app(lambda a: a.get("prompt") or "none")),
        ("tools", per_app(lambda a: _join(_tool_label(t) for t in a.get("tools") or []))),
        ("subagents", per_app(lambda a: _join(a.get("subagents") or []))),
        (
            "connectors",
            per_app(
                lambda a: _join(
                    dict.fromkeys(
                        c
                        for t in a.get("tools") or []
                        if not isinstance(t, str)
                        for c in [(t[next(iter(t))] or {}).get("connector")]
                        if c
                    )
                )
            ),
        ),
        ("skills", per_app(lambda a: skill_cell)),
        ("middleware", per_app(lambda a: _mw_summary(a.get("middleware") or []))),
        ("guards", per_app(lambda a: guard_cell)),
        ("memory", per_app(lambda a: memory_cell)),
        (
            "tenant policy",
            per_app(lambda a: "allowed side effects set per tenant stamp"),
        ),
        ("evals", per_app(lambda a: _eval_summary(a.get("evals") or []))),
    ]
    rows = []
    for part, cells in parts:
        same = len(set(cells.values())) <= 1
        origin = "platform" if same and part in _PLATFORM_PARTS else "config"
        rows.append({"part": part, "cells": cells, "origin": origin})
    for part in COMING_ROWS:
        rows.append({"part": part, "cells": per_app(lambda a: COMING), "origin": "coming"})
    return {"agents": [a["name"] for a in apps], "rows": rows}


# ------------------------------- assembly ---------------------------------


def _module_source(target: str) -> str:
    """Repo-relative file for an entry-point target like `pkg.mod:attr`."""
    mod = target.split(":")[0]
    rel = mod.replace(".", "/") + ".py"
    for hit in sorted(ROOT.glob(f"packages/*/src/{rel}")) + sorted(ROOT.glob(f"apps/*/src/{rel}")):
        return str(hit.relative_to(ROOT))
    return rel


def _entry_targets(group: str, catalog: dict) -> dict[str, str]:
    eps = {e["name"]: e["target"] for e in catalog.get("entry_points", []) if e["group"] == group}
    if not eps:
        eps = {e.name: e.value for e in importlib.metadata.entry_points(group=group)}
    return eps


def _mw_id(item: dict) -> str:
    t = item["type"]
    params = item.get("params") or {}
    if t == "tool_call_limit" and params.get("tool_name"):
        return f"mw:{t}:{params['tool_name']}"
    if t == "pii" and params.get("type"):
        return f"mw:{t}:{params['type']}"
    return f"mw:{t}"


def build_assembly(app: dict, catalog: dict) -> dict:
    spec = app.get("spec") or {}
    text = app.get("yaml") or ""
    mw_src = _entry_targets("agentkit.middleware", catalog)
    tool_src = _entry_targets("agentkit.tools", catalog)
    sub_desc = {s["name"]: s.get("description") or "" for s in catalog.get("subagents", [])}

    layers: list[dict] = [
        {
            "id": f"guard:{g.name}",
            "kind": "guard",
            "label": f"{g.name}: {g.checks}",
            "source": GUARDS_SOURCE,
            "fixed": True,
        }
        for g in GUARD_LAYERS
    ]

    def model_layer(name: str, role: str) -> dict:
        return {
            "id": f"model:{name}",
            "kind": "model",
            "label": f"{name} ({role})",
            "source": MODELS_SOURCE,
            "fixed": False,
        }

    if spec.get("model"):
        layers.append(model_layer(spec["model"], "primary"))
    for name in _fallback_models(spec):
        layers.append(model_layer(name, "fallback"))

    rank = {t: i for i, t in enumerate(STACK_ORDER)}
    mws = sorted(spec.get("middleware") or [], key=lambda m: rank.get(m["type"], len(rank)))
    for m in mws:
        params = m.get("params") or {}
        detail = ", ".join(f"{k}={v}" for k, v in params.items() if k != "models")
        layers.append(
            {
                "id": _mw_id(m),
                "kind": "middleware",
                "label": m["type"] + (f" ({detail})" if detail else ""),
                "source": _module_source(mw_src.get(m["type"], "")),
                "fixed": False,
            }
        )
    for ref in spec.get("tools") or []:
        name = _tool_name(ref)
        layers.append(
            {
                "id": f"tool:{name}",
                "kind": "tool",
                "label": _tool_label(ref),
                "source": _module_source(tool_src.get(name, "")),
                "fixed": False,
            }
        )
    for sub in spec.get("subagents") or []:
        name = sub if isinstance(sub, str) else sub.get("name")
        desc = sub_desc.get(name, "")
        layers.append(
            {
                "id": f"subagent:{name}",
                "kind": "subagent",
                "label": f"{name}: {desc}" if desc else name,
                "source": f"libraries/subagents/{name}.yaml",
                "fixed": False,
            }
        )

    ids = {layer["id"] for layer in layers}
    yaml_mw = [_mw_id(m) for m in spec.get("middleware") or []]
    mw_cursor = 0
    lines = []
    section = None
    for n, raw in enumerate(text.splitlines(), start=1):
        part_ids: list[str] = []
        top = re.match(r"^([A-Za-z_]+):\s*(.*)$", raw)
        if top:
            key, rest = top.group(1), top.group(2).strip()
            section = key
            if key == "model" and rest:
                part_ids = [f"model:{rest}"]
            elif key in ("tools", "subagents") and rest.startswith("["):
                prefix = "tool" if key == "tools" else "subagent"
                part_ids = [f"{prefix}:{i}" for i in re.findall(r"[A-Za-z_][\w-]*", rest)]
            elif key == "output" and "mw:require_output" in ids:
                part_ids = ["mw:require_output"]
        elif re.match(r"^\s*-\s", raw) and section == "tools":
            m = re.match(r"^\s*-\s*\{?\s*([A-Za-z_][\w-]*)", raw)
            part_ids = [f"tool:{m.group(1)}" if m else None]
        elif re.match(r"^\s*-\s", raw) and section == "subagents":
            m = re.match(r"^\s*-\s*\{?\s*(?:name:\s*)?([A-Za-z_][\w-]*)", raw)
            part_ids = [f"subagent:{m.group(1)}" if m else None]
        elif re.match(r"^\s*-\s", raw) and section == "middleware":
            if mw_cursor < len(yaml_mw):
                part_ids = [yaml_mw[mw_cursor]]
                mw_cursor += 1
        part_ids = [p for p in part_ids if p in ids]
        lines.append({"n": n, "text": raw, "part_ids": part_ids})
    return {"yaml": text, "lines": lines, "layers": layers}
