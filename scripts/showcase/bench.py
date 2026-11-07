"""Bench data for the showcase page: clonable templates, part options, rule hints, run commands.

Everything is generated from the catalog; the rule hints are data that the page's JS evaluates.
"""

from __future__ import annotations

import copy

from showcase.redact import example_tenant_policy

KB_TOOLS = ("kb_search", "sql_query")
SUFFIX = " — `agentkit validate` is the authority"

RULES = [
    {
        "id": "side_effect_not_allowed",
        "message": "A tool's side-effect class is not in the tenant's allowed side effects"
        + SUFFIX,
    },
    {
        "id": "missing_require_output",
        "message": "The agent sets an output path but has no require_output middleware" + SUFFIX,
    },
    {
        "id": "unknown_part",
        "message": "A tool, subagent, connector or middleware type is not in the library" + SUFFIX,
    },
    {
        "id": "kb_tool_without_connector",
        "message": "kb_search and sql_query need a connector parameter" + SUFFIX,
    },
    {
        "id": "subagent_unknown_tool",
        "message": "A subagent uses a tool that is not registered" + SUFFIX,
    },
]

_BASE_COMMANDS = ["uv run agentkit validate {file}", "uv run research --agent {file}"]
_KB_PREREQS = [
    "export KB_DATABASE_URL=<kb_reader DSN>",
    "export KB_READER_DATABASE_URL=<kb_reader DSN>",
    "uv run agentkit-kb setup   # admin DSN; then: uv run agentkit-kb ingest",
]


def _tool_names(spec: dict) -> list[str]:
    out = []
    for t in spec.get("tools") or []:
        out.append(t if isinstance(t, str) else next(iter(t)))
    return out


def build_bench(catalog: dict) -> dict:
    templates = []
    for app in catalog["apps"]:
        spec = copy.deepcopy(app["spec"])
        uses_kb = any(n in KB_TOOLS for n in _tool_names(spec))
        templates.append(
            {
                "name": app["name"],
                "base": app["name"],
                "spec": spec,
                "commands": "kb" if uses_kb else "research",
            }
        )
    tools = [
        {
            "name": t["name"],
            "side_effect": (t.get("meta") or {}).get("side_effects"),
            "params": copy.deepcopy(t.get("params") or []),
        }
        for t in catalog["tools"]
    ]
    return {
        "templates": templates,
        "options": {
            "tools": tools,
            "subagents": [
                {"name": s["name"], "tools": list(s.get("tools") or [])}
                for s in catalog["subagents"]
            ],
            "connectors": [{"name": c["name"], "kind": c["kind"]} for c in catalog["connectors"]],
            "middleware": list(catalog["middleware"]["factories"]),
            "skills": [],
        },
        "policy": {
            "example_tenant": example_tenant_policy(),
            "classes": ["read", "write", "external"],
        },
        "rules": copy.deepcopy(RULES),
        "commands": {
            "research": list(_BASE_COMMANDS),
            "kb": _BASE_COMMANDS + _KB_PREREQS,
        },
    }
