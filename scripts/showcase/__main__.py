"""One chassis, many agents: the showcase page generator.

Run from `scripts/` (or with PYTHONPATH=scripts):
    python -m showcase --serve [--port 8766] [--open]   # live page for the meeting (team view)
    python -m showcase --write PATH                      # self-contained customer snapshot
"""

from __future__ import annotations

import argparse
import json
import subprocess
import webbrowser
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import platform_catalog
import yaml

from showcase.bench import build_bench
from showcase.model import build_assembly, build_matrix
from showcase.redact import ROOT, assert_clean, example_tenant_policy, scrub

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / "page.html"
POSITIONING = HERE / "positioning.yaml"
REPLAY = ROOT / "evidence/showcase/replay.json"
REPORT = ROOT / "evidence/showcase/report.md"
PLACEHOLDER = "/*__SHOWCASE__*/"


def _git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _matrix(catalog: dict) -> dict:
    matrix = build_matrix(catalog["apps"], catalog["skills"])
    label = "example tenant: " + ", ".join(example_tenant_policy())
    for row in matrix["rows"]:
        if row["part"] == "tenant policy":
            row["cells"] = {agent: label for agent in matrix["agents"]}
    return matrix


def _machine(catalog: dict) -> dict:
    """Team-only view of this machine: which known keys are set (names and flags, never values)."""
    keys = catalog.get("env_keys") or {}
    return {"keys": [{"name": k, "set": bool(v)} for k, v in sorted(keys.items())]}


def build_data(snapshot: bool) -> dict:
    catalog = platform_catalog.collect()
    data = {
        "matrix": _matrix(catalog),
        "assemblies": {a["name"]: build_assembly(a, catalog) for a in catalog["apps"]},
        "bench": build_bench(catalog),
        "replay": json.loads(REPLAY.read_text()) if REPLAY.is_file() else None,
        "report": REPORT.read_text() if REPORT.is_file() else None,
        "positioning": yaml.safe_load(POSITIONING.read_text()),
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "git_sha": _git_sha(),
    }
    data = scrub(data)
    if not snapshot:
        data["machine"] = _machine(catalog)
    return data


def render(snapshot: bool) -> str:
    payload = json.dumps(build_data(snapshot)).replace("</", "<\\/")
    html = TEMPLATE.read_text().replace(PLACEHOLDER, payload)
    assert_clean(html)
    return html


def serve(port: int, open_browser: bool) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            body = render(snapshot=False).encode()  # rebuilt per request: edits show on reload
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a) -> None:
            pass

    url = f"http://127.0.0.1:{port}"
    print(f"agentkit showcase: {url}  (Ctrl-C to stop)")
    if open_browser:
        webbrowser.open(url)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m showcase", description=__doc__)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--serve", action="store_true", help="serve the live page (team view)")
    mode.add_argument("--write", metavar="PATH", help="write the self-contained snapshot")
    ap.add_argument("--port", type=int, default=8766)
    ap.add_argument("--open", action="store_true", help="open the browser")
    args = ap.parse_args()
    if args.write:
        path = Path(args.write)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render(snapshot=True))
        print(f"wrote {args.write}")
    else:
        serve(args.port, args.open)


if __name__ == "__main__":
    main()
