"""Redaction for the showcase snapshot: denylist scrub, machine-state removal, example policy.

Sentence rule for long text (over 200 characters): split on sentence boundaries (". ", "! ",
"? " and newlines) and drop only the sentences containing a denylisted phrase. Shorter strings
that contain a phrase are dropped whole (list items and dict values); the denylist always wins.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent

DENYLIST: tuple[str, ...] = (
    "P10",
    "P3 ",
    "thread-to-user binding",
    "primitive state plaintext",
    "AES key rotation",
    "key rotation",
    "only env://",
    "env:// secrets",
    "never pruned",
    "tenant filter",
    "innermost guard",
    "Open items",
    "decision debt",
)

# Machine state: env/.env key names and set-or-not flags, DSNs. The last three come from
# platform_catalog.collect(): `key_env`/`key_set` (per model/embedding) and `allowed_side_effects`
# (read from os.environ; the page shows the example tenant policy instead).
DROP_KEYS = frozenset(
    {"env", "env_keys", "keys_set", "dotenv", "dsn", "key_env", "key_set", "allowed_side_effects"}
)

_SENTENCE = re.compile(r"(?<=[.!?]) +|\n")


def _hit(text: str) -> str | None:
    low = text.lower()
    return next((p for p in DENYLIST if p.lower() in low), None)


def _text(s: str) -> str | None:
    """Scrubbed string, or None when the whole string is dropped."""
    if s.startswith(str(ROOT)):
        return None
    if _hit(s) is None:
        return s
    if len(s) <= 200:
        return None
    kept = [p for p in _split_keep(s) if _hit(p) is None]
    return "".join(kept).strip() or None


def _split_keep(s: str) -> list[str]:
    """Sentences with their trailing separators, so kept text rejoins unchanged."""
    out, pos = [], 0
    for m in _SENTENCE.finditer(s):
        out.append(s[pos : m.end()])
        pos = m.end()
    out.append(s[pos:])
    return out


def scrub(obj: Any) -> Any:
    """Deep copy of `obj` without denylisted text or machine state."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in DROP_KEYS:
                continue
            c = scrub(v)
            if c is not _DROP:
                out[k] = c
        return out
    if isinstance(obj, (list, tuple)):
        items = [c for c in (scrub(v) for v in obj) if c is not _DROP]
        return items if isinstance(obj, list) else tuple(items)
    if isinstance(obj, str):
        t = _text(obj)
        return _DROP if t is None else t
    return obj


_DROP: Any = object()


def assert_clean(text: str) -> None:
    hit = _hit(text)
    if hit is not None:
        raise ValueError(f"denylisted phrase in output: {hit!r}")


def example_tenant_policy() -> list[str]:
    """Side-effect classes of the example tenant, parsed from deploy/tenants/example.env only."""
    for line in (ROOT / "deploy/tenants/example.env").read_text().splitlines():
        key, _, val = line.partition("=")
        if key.strip() == "AGENTKIT_ALLOWED_SIDE_EFFECTS":
            return [c.strip() for c in val.split(",") if c.strip()]
    return ["read", "external"]
