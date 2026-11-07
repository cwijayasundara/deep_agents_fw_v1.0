"""Turn one recorded research run (collector spans + ledger rows) into the page's replay events.

CLI: python -m showcase.replay <spans.jsonl> <usage.json> > replay.json

Span shapes come from the tenant collector's OTLP file (deploy/otel-out/<tenant>/spans.jsonl):
Langfuse observations, whose input/output ride in `langfuse.observation.input|output`. Payloads
are only present when the run set AGENTKIT_TRACE_PAYLOADS=1.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from showcase.redact import assert_clean, scrub

DETAIL_MAX = 240
_IN, _OUT = "langfuse.observation.input", "langfuse.observation.output"
_SECRETS = re.compile(r"postgres(?:ql)?://\S+|\bsk-[A-Za-z0-9_-]{8,}|\bfw_[A-Za-z0-9]{8,}")
_PII_SPAN = re.compile(r"^PIIMiddleware\[(\w+)\]\.(?:before|after)_model$")
_LIMIT_SPAN = re.compile(r"^ToolCallLimitMiddleware\[(\w+)\]\.after_model$")
_LIMIT_MSG = "Tool call limit exceeded"
_CARD_MASK = re.compile(r"\*{4}[-\s*]*\d{4}")
_TOOLS = ("web_search", "fetch_url")


def _attrs(span: dict) -> dict[str, str]:
    out = {}
    for a in span.get("attributes", []):
        v = a.get("value", {})
        out[a["key"]] = next(iter(v.values())) if v else ""
    return out


def _load(path: Path) -> list[dict]:
    spans: list[dict] = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        for rs in json.loads(line).get("resourceSpans", []):
            for ss in rs.get("scopeSpans", []):
                spans.extend(ss.get("spans", []))
    return sorted(spans, key=lambda s: int(s["startTimeUnixNano"]))


def _detail(text: str) -> str:
    text = _SECRETS.sub("[secret]", " ".join(str(text).split()))
    cleaned = scrub(text) or ""
    return cleaned if len(cleaned) <= DETAIL_MAX else cleaned[: DETAIL_MAX - 1] + "…"


def _json(s: str) -> Any:
    try:
        return json.loads(s)
    except (TypeError, ValueError):
        return None


def _first_text(payload: Any) -> str:
    """The first human-readable message content in an observation payload."""
    if isinstance(payload, dict):
        msgs = payload.get("messages")
        if isinstance(msgs, list) and msgs:
            return _first_text(msgs[0])
        return str(payload.get("content") or payload.get("description") or "")
    if isinstance(payload, list) and payload:
        return _first_text(payload[-1])
    return str(payload or "")


def _clean(text: str) -> str:
    return _SECRETS.sub("[secret]", scrub(text) or "")


def _marker(kind: str, text: str) -> str | None:
    """PII middleware output marker: langchain's `[REDACTED_<TYPE>]`, or a card mask."""
    tag = f"[REDACTED_{kind.upper()}]"
    if tag in text:
        return tag
    if kind == "credit_card" and (m := _CARD_MASK.search(text)):
        return m.group(0)
    return None


def _snippet(text: str, marker: str) -> str:
    """The marker with its surrounding words, cut at the JSON string's quotes."""
    pat = r'[^"\\]{0,70}' + re.escape(marker) + r'[^"\\]{0,60}'
    m = re.search(pat, text)
    return m.group(0) if m else marker


def replay_from_spans(spans_path: Path, usage_rows: list[dict]) -> dict:
    spans = _load(Path(spans_path))
    if not spans:
        raise ValueError(f"no spans in {spans_path}")
    t0 = int(spans[0]["startTimeUnixNano"])
    parent = {s["spanId"]: s.get("parentSpanId", "") for s in spans}
    name_of = {s["spanId"]: s["name"] for s in spans}

    def subagent_of(span: dict) -> str:
        pid = span.get("parentSpanId", "")
        while pid:
            if name_of.get(pid) == "researcher":
                return "researcher"
            pid = parent.get(pid, "")
        return ""

    events: list[dict] = []
    seen: set[str] = set()
    question, model = "", ""

    def add(span: dict, kind: str, label: str, part_id: str, detail: str) -> None:
        t = (int(span["startTimeUnixNano"]) - t0) / 1e9
        events.append(
            {"t": round(t, 2), "kind": kind, "label": label, "part_id": part_id,
             "detail": _detail(detail)}
        )  # fmt: skip

    for s in spans:
        name, a = s["name"], _attrs(s)
        inp, out = a.get(_IN, ""), a.get(_OUT, "")
        if name == "research_agent" and not question:
            question = _clean(_first_text(_json(inp)))
        elif (m := _PII_SPAN.match(name)) and (mark := _marker(m.group(1), out)):
            pid = f"mw:pii:{m.group(1)}"
            if pid not in seen:
                seen.add(pid)
                add(s, "pii", f"PII {m.group(1)} masked", pid, _snippet(out, mark))
        elif (m := _LIMIT_SPAN.match(name)) and _LIMIT_MSG in out:
            pid = f"mw:tool_call_limit:{m.group(1)}"
            if pid not in seen:
                seen.add(pid)
                add(s, "limit", f"{m.group(1)} call limit reached", pid, _snippet(out, _LIMIT_MSG))
        elif name.endswith("Middleware.before_agent") and name.startswith("TenantGuard"):
            add(
                s, "guard", "Tenant guard", "guard:TenantGuardMiddleware", "Run bound to its tenant"
            )
        elif name == "ChatFireworks":
            mname = a.get("langfuse.observation.model.name", "").rsplit("/", 1)[-1]
            model = model or mname
            body = _json(out)
            text = (body.get("content") if isinstance(body, dict) else "") or out
            calls = body.get("tool_calls") if isinstance(body, dict) else None
            detail = text or ", ".join(c.get("name", "") for c in calls or [])
            who = subagent_of(s)
            label = f"{who} · model call" if who else (mname or "model")
            # Always the primary layer: the tier is selection, not fallback.
            add(s, "model", label, "model:fireworks-glm", detail)
        elif name == "task":
            body = _json(inp) or {}
            add(
                s, "subagent", "researcher", "subagent:researcher", str(body.get("description", ""))
            )
        elif name in _TOOLS:
            body = _json(inp) or {}
            arg = body.get("query") or body.get("url") or ""
            add(s, "tool", name, f"tool:{name}", str(arg))
        elif name == "write_file":
            body = _json(inp) or {}
            if body.get("file_path") == "/report.md":
                add(s, "output", "report.md written", "output", "Report written to /report.md")

    events.sort(key=lambda e: e["t"])
    tokens = sum(
        int(r.get("input_tokens") or 0) + int(r.get("output_tokens") or 0)
        + int(r.get("decisions_input_tokens") or 0) + int(r.get("decisions_output_tokens") or 0)
        for r in usage_rows
    )  # fmt: skip
    costs = [float(r["cost_usd"]) for r in usage_rows if r.get("cost_usd") is not None]
    cost = round(sum(costs), 6) if costs else None
    return {"question": question, "model": model, "events": events,
            "totals": {"tokens": tokens, "cost_usd": cost}}  # fmt: skip


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python -m showcase.replay <spans.jsonl> <usage.json>", file=sys.stderr)
        return 2
    rows = json.loads(Path(argv[1]).read_text())
    text = json.dumps(replay_from_spans(Path(argv[0]), rows), indent=1, ensure_ascii=False)
    assert_clean(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
