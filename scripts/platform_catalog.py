#!/usr/bin/env -S uv run python
"""Live catalog of the agentkit platform, served as a visual web app.

Introspects the installed workspace -- entry points, tool governance metadata, the model
registry, library pools (prompts, subagents, skills, connectors), app YAML files, eval
datasets and baselines -- and renders it as a single-page dashboard, so the answer to
"what is already there?" is always read from the repo, never hand-written.

    uv run python scripts/platform_catalog.py --serve [--port 8765] [--open]
    uv run python scripts/platform_catalog.py --write catalog.html   # standalone file
    uv run python scripts/platform_catalog.py --json                 # raw catalog to stdout

Stdlib + pyyaml only; works offline; no secrets are read (only key *names* and whether
they are set).
"""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import inspect
import json
import os
import re
import tomllib
import webbrowser
from dataclasses import asdict
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml
from agentkit_deep import GUARD_LAYERS, MEMORY_ROUTES

ROOT = Path(__file__).resolve().parent.parent
EP_GROUPS = (
    "agentkit.tools",
    "agentkit.middleware",
    "agentkit.nodes",
    "agentkit.schemas",
    "agentkit.search_backends",
    "agentkit.secrets",
)
PINNED = ("deepagents", "langchain", "langchain-core", "langgraph", "langgraph-checkpoint-postgres")
KNOWN_KEYS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "FIREWORKS_API_KEY",
    "PARALLEL_API_KEY",
    "BRAVE_API_KEY",
    "TAVILY_API_KEY",
    "DATABASE_URL",
    "LANGGRAPH_AES_KEY",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "AGENTKIT_TENANT",
    "AGENTKIT_ALLOWED_SIDE_EFFECTS",
    "AGENTKIT_LIBRARY_PATH",
)
FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
# Reference data comes from agentkit_deep (GUARD_LAYERS, MEMORY_ROUTES); the default
# StateBackend is not a route, so it is appended here.
MEMORY_TIERS = [
    *(asdict(r) for r in MEMORY_ROUTES),
    {
        "path": "everything else (/report.md, scratch)",
        "backend": "StateBackend",
        "namespace": "thread files channel",
        "scope": "this thread only",
        "writable": True,
    },
]
GUARDS = [asdict(g) for g in GUARD_LAYERS]


def _front(text: str) -> dict:
    m = FRONT_MATTER.match(text)
    return yaml.safe_load(m.group(1)) or {} if m else {}


def _yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text()) or {}


def _packages() -> list[dict]:
    out = []
    for pyproject in sorted(
        [*ROOT.glob("packages/*/pyproject.toml"), *ROOT.glob("apps/*/pyproject.toml")]
    ):
        proj = tomllib.loads(pyproject.read_text()).get("project", {})
        out.append(
            {
                "dir": str(pyproject.parent.relative_to(ROOT)),
                "name": proj.get("name", "?"),
                "version": proj.get("version", "?"),
                "description": (proj.get("description") or "").rstrip("."),
                "entry_point_groups": sorted((proj.get("entry-points") or {}).keys()),
            }
        )
    return out


def _entry_points() -> list[dict]:
    out = []
    for group in EP_GROUPS:
        for ep in importlib.metadata.entry_points(group=group):
            out.append(
                {
                    "group": group,
                    "name": ep.name,
                    "target": ep.value,
                    "dist": ep.dist.name if ep.dist else "?",
                }
            )
    return sorted(out, key=lambda e: (e["group"], e["name"]))


def _tool_params(name: str) -> list[dict]:
    schema_file = ROOT / "packages/agentkit-tools/tool_schemas.json"
    if not schema_file.exists():
        return []
    schema = json.loads(schema_file.read_text()).get(name, {}).get("schema", {})
    props = schema.get("properties", {})
    required = set(schema.get("required", []))
    return [
        {
            "name": n,
            "type": p.get("type", "?"),
            "required": n in required,
            "description": p.get("description", ""),
        }
        for n, p in props.items()
    ]


def _tools() -> list[dict]:
    out = []
    for ep in importlib.metadata.entry_points(group="agentkit.tools"):
        item = {
            "name": ep.name,
            "factory": ep.value,
            "meta": None,
            "params": _tool_params(ep.name),
            "error": None,
        }
        try:
            factory = ep.load()
            meta = getattr(factory, "__agentkit_tool__", None)
            if meta is not None:
                d = meta.model_dump()
                d["tenants"] = sorted(d["tenants"]) if d["tenants"] else None
                item["meta"] = d
        except Exception as e:  # a broken factory must not kill the catalog
            item["error"] = f"{type(e).__name__}: {e}"
        out.append(item)
    return sorted(out, key=lambda t: t["name"])


def _middleware() -> dict:
    from agentkit_config.stack import SINGLETONS, STACK_ORDER

    builtins = []
    try:
        import agentkit_middleware.factories as f

        builtins = sorted(
            n
            for n, fn in inspect.getmembers(f, inspect.isfunction)
            if not n.startswith("_") and "ctx" in inspect.signature(fn).parameters
        )
    except Exception:
        pass
    return {
        "canonical_order": list(STACK_ORDER),
        "singletons": sorted(SINGLETONS),
        "factories": builtins,
        "fixed_guards": GUARDS,
    }


def _models(env_keys: set[str]) -> dict:
    from agentkit_core.settings import _ENV_VAR  # provider -> env var (private but stable)

    data = _yaml(ROOT / "packages/agentkit-core/src/agentkit_core/models.yaml")
    models = []
    for name, spec in (data.get("models") or {}).items():
        provider = spec.get("provider", name)
        env = _ENV_VAR.get(provider, f"{provider.upper()}_API_KEY")
        env_keys.add(env)
        models.append(
            {
                "name": name,
                "provider": provider,
                "tiers": {k: v for k, v in spec.items() if k not in ("provider", "kwargs")},
                "key_env": env,
                "key_set": env in env_keys,
            }
        )
    embeddings = [
        {
            "name": n,
            "model": (s.get("model") if isinstance(s, dict) else s),
            "dims": (s.get("dimensions") if isinstance(s, dict) else None),
            "key_env": "FIREWORKS_API_KEY",
            "key_set": "FIREWORKS_API_KEY" in env_keys,
        }
        for n, s in (data.get("embeddings") or {}).items()
    ]
    return {"models": models, "embeddings": embeddings}


def _library_roots() -> list[Path]:
    roots = [ROOT / "libraries"]
    extra = os.environ.get("AGENTKIT_LIBRARY_PATH", "")
    roots += [Path(p) for p in extra.split(os.pathsep) if p]
    return [r for r in roots if r.is_dir()]


def _prompts() -> list[dict]:
    labels = {}
    for root in _library_roots():
        f = root / "prompts/labels.yaml"
        if f.exists():
            labels = _yaml(f)
    out = {}
    for root in _library_roots():
        for md in sorted((root / "prompts").rglob("*.md")):
            parts = md.relative_to(root / "prompts").with_suffix("").parts
            if len(parts) >= 2 and re.fullmatch(r"v\d+\.\d+\.\d+", md.stem):
                name, version = "/".join(parts[:-1]), md.stem[1:]
            else:
                name, version = "/".join(parts), "0.0.0 (unversioned)"
            fm = _front(md.read_text())
            entry = out.setdefault(
                name, {"name": name, "versions": [], "labels": labels.get(name, {})}
            )
            entry["versions"].append(
                {
                    "version": version,
                    "owner": fm.get("owner", ""),
                    "description": fm.get("description", ""),
                }
            )
    return sorted(out.values(), key=lambda p: p["name"])


def _subagents() -> list[dict]:
    out = []
    for root in _library_roots():
        for f in sorted((root / "subagents").glob("*.yaml")):
            spec = _yaml(f)
            out.append(
                {
                    k: spec.get(k)
                    for k in (
                        "name",
                        "description",
                        "prompt",
                        "tools",
                        "model",
                        "tier",
                        "response_schema",
                    )
                }
            )
    return out


def _skills() -> list[dict]:
    out = []
    for root in _library_roots():
        for skill_md in sorted((root / "skills").glob("*/SKILL.md")):
            fm = _front(skill_md.read_text())
            out.append(
                {
                    "name": fm.get("name", skill_md.parent.name),
                    "description": fm.get("description", ""),
                    "dir": str(skill_md.parent.relative_to(ROOT)),
                }
            )
    return out


def _connectors() -> list[dict]:
    out = []
    for root in _library_roots():
        for f in sorted((root / "connectors").glob("*.yaml")):
            spec = _yaml(f)
            out.append(
                {
                    "name": f.stem,
                    "kind": spec.get("kind", "?"),
                    "config": {k: v for k, v in spec.items() if k not in ("kind", "name")},
                }
            )
    return out


def _apps() -> list[dict]:
    out = []
    for agent_file in sorted(ROOT.glob("apps/*/agent.yaml")):
        spec = _yaml(agent_file)
        app = {
            "name": spec.get("name", agent_file.parent.name),
            "dir": str(agent_file.parent.relative_to(ROOT)),
            "model": spec.get("model"),
            "tier": spec.get("tier"),
            "selection": spec.get("selection"),
            "prompt": spec.get("prompt"),
            "tools": spec.get("tools", []),
            "subagents": [
                s if isinstance(s, str) else s.get("name") for s in spec.get("subagents", [])
            ],
            "middleware": [m["type"] for m in spec.get("middleware", [])],
            "output": spec.get("output"),
            "flows": [],
            "evals": _evals(agent_file.parent),
            "yaml": agent_file.read_text(),
            "spec": spec,
        }
        for flow_file in sorted(agent_file.parent.glob("flows/*.yaml")):
            flow = _yaml(flow_file)
            app["flows"].append(
                {
                    "name": flow.get("name", flow_file.stem),
                    "nodes": list((flow.get("nodes") or {}).keys()),
                    "interrupts": [
                        n
                        for n, v in (flow.get("nodes") or {}).items()
                        if isinstance(v, dict) and v.get("interrupt")
                    ],
                }
            )
        out.append(app)
    return out


def _evals(app_dir: Path) -> list[dict]:
    out = []
    for f in sorted((app_dir / "evals").iterdir()):
        if f.suffix == ".jsonl":
            lines = [ln for ln in f.read_text().splitlines() if ln.strip()]
            kinds = {}
            for ln in lines:
                try:
                    case = json.loads(ln)
                except json.JSONDecodeError:
                    continue
                k = case.get("kind", "single_step" if "expect_call" in case else "full")
                kinds[k] = kinds.get(k, 0) + 1
            out.append({"file": f.name, "cases": len(lines), "kinds": kinds})
        elif f.name == "gates.yaml":
            gates = _yaml(f)
            out.append(
                {
                    "file": f.name,
                    "metrics": sorted((gates.get("metrics") or gates or {}).keys())
                    if isinstance(gates, dict)
                    else [],
                }
            )
        elif f.name.startswith("baseline") and f.suffix == ".json":
            base = json.loads(f.read_text())
            out.append(
                {
                    "file": f.name,
                    "aggregate": base.get("aggregate", {}),
                    "recorded": base.get("date", ""),
                }
            )
    return out


def _dotenv_keys() -> set[str]:
    f = ROOT / ".env"
    if not f.exists():
        return set()
    return {
        k.split("=", 1)[0].strip()
        for k in f.read_text().splitlines()
        if "=" in k and not k.strip().startswith("#")
    }


def collect() -> dict:
    dotenv = _dotenv_keys()
    env_keys = {k for k in KNOWN_KEYS if k in os.environ or k in dotenv}
    key_state = dict.fromkeys(KNOWN_KEYS, False) | {k: True for k in env_keys}
    from agentkit_tools.factories import AUTO_ORDER

    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "pins": {
            p: (importlib.metadata.version(p) if _dist(p) else "not installed") for p in PINNED
        },
        "env_keys": {k: v for k, v in sorted(key_state.items())},
        "packages": _packages(),
        "entry_points": _entry_points(),
        "tools": _tools(),
        "middleware": _middleware(),
        "search": {"auto_order": list(AUTO_ORDER), "keyless_last_resort": "duckduckgo"},
        "models": _models(env_keys),
        "prompts": _prompts(),
        "subagents": _subagents(),
        "skills": _skills(),
        "connectors": _connectors(),
        "apps": _apps(),
        "memory_tiers": MEMORY_TIERS,
        "policy": {
            "side_effect_classes": ["read", "write", "external"],
            "allowed_side_effects": os.environ.get(
                "AGENTKIT_ALLOWED_SIDE_EFFECTS", "read,external (default)"
            ),
            "tenant_env_file": "deploy/tenants/<t>.env via `make stamp TENANT=<t>`",
        },
    }


def _dist(name: str) -> bool:
    try:
        importlib.metadata.version(name)
        return True
    except importlib.metadata.PackageNotFoundError:
        return False


# ----------------------------- serving ------------------------------------


def _load_html() -> str:
    return (Path(__file__).parent / "catalog.html").read_text()


def _standalone_html(catalog: dict) -> str:
    payload = json.dumps(catalog).replace("</", "<\\/")
    return _load_html().replace("__CATALOG_JSON__", payload)


def serve(catalog: dict, port: int, open_browser: bool) -> None:
    html = _standalone_html(catalog)
    raw = json.dumps(catalog, indent=1).encode()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/catalog.json":
                self._send(raw, "application/json")
            else:
                self._send(html.encode(), "text/html")

        def _send(self, body: bytes, ctype: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", f"{ctype}; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a) -> None:  # silence request logging
            pass

    url = f"http://127.0.0.1:{port}"
    print(f"agentkit platform catalog: {url}  (Ctrl-C to stop)")
    if open_browser:
        webbrowser.open(url)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--serve", action="store_true", help="serve the dashboard (default if no other mode)"
    )
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--open", action="store_true", help="open the browser")
    ap.add_argument("--write", metavar="PATH", help="write a standalone HTML file and exit")
    ap.add_argument("--json", action="store_true", help="print the raw catalog JSON and exit")
    args = ap.parse_args()

    catalog = collect()
    if args.json:
        print(json.dumps(catalog, indent=1))
    elif args.write:
        Path(args.write).write_text(_standalone_html(catalog))
        print(f"wrote {args.write} (open it directly in a browser)")
    else:
        serve(catalog, args.port, args.open)


if __name__ == "__main__":
    main()
