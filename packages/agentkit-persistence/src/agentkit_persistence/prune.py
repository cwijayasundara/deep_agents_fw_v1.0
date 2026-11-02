"""Delete threads whose newest checkpoint is older than a cutoff (`agentkit-prune`).

The age comes from the checkpoint's `ts` field (pinned by the pg contract suite). Deletion goes
through the saver's `adelete_thread`, so checkpoints, blobs and writes all go. Running it twice
deletes nothing the second time.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from collections.abc import Sequence
from datetime import timedelta

from agentkit_core import ConfigError

from .open import Persistence, PersistenceSettings, open_persistence

_AGE = re.compile(r"^(\d+)([dhm])$")
_UNITS = {"d": "days", "h": "hours", "m": "minutes"}
_STALE_THREADS = """
    select thread_id from checkpoints
    group by thread_id
    having max((checkpoint->>'ts')::timestamptz) < now() - %s
"""


def parse_age(text: str) -> timedelta:
    """`30d`, `12h` or `45m` as a timedelta."""
    match = _AGE.match(text)
    if not match:
        raise ValueError(f"--older-than must look like 30d, 12h or 45m, got {text!r}")
    return timedelta(**{_UNITS[match.group(2)]: int(match.group(1))})


async def prune(persistence: Persistence, older_than: timedelta) -> int:
    """Delete every thread whose newest checkpoint is older than `older_than`; return the count."""
    async with persistence.pool.connection() as conn:
        cur = await conn.execute(_STALE_THREADS, (older_than,))
        thread_ids = [row["thread_id"] for row in await cur.fetchall()]
    for thread_id in thread_ids:
        await persistence.saver.adelete_thread(thread_id)
    return len(thread_ids)


async def _run(older_than: timedelta) -> int:
    async with open_persistence(PersistenceSettings.from_env()) as persistence:
        return await prune(persistence, older_than)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agentkit-prune", description="Delete threads idle longer than --older-than."
    )
    parser.add_argument("--older-than", required=True, help="age cutoff: 30d, 12h or 45m")
    args = parser.parse_args(argv)
    try:
        older_than = parse_age(args.older_than)
        count = asyncio.run(_run(older_than))
    except (ConfigError, ValueError) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(f"pruned {count} threads")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
