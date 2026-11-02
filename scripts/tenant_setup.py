"""Set up one tenant's database and report what changed (run by scripts/stamp_tenant.sh).

Runs `open_persistence` (checkpoint and store migrations) and the cost ledger's `setup`
(`agentkit_usage`), with DATABASE_URL and LANGGRAPH_AES_KEY from the environment. Prints how many
migrations each step applied, so a second stamp shows it changed nothing.

Exit codes: 0 ok, 2 bad persistence config or unreachable database.
"""

from __future__ import annotations

import asyncio
import sys

from agentkit_core import ConfigError
from agentkit_persistence import PersistenceSettings, open_persistence
from agentkit_telemetry import setup
from psycopg import AsyncConnection, OperationalError

TABLES = ("checkpoint_migrations", "store_migrations")


async def applied(settings: PersistenceSettings) -> dict[str, int]:
    """Migrations recorded per table (0 when the table does not exist yet)."""
    url = settings.database_url.get_secret_value()
    timeout = max(1, int(settings.connect_timeout_seconds))
    try:
        conn = await AsyncConnection.connect(url, connect_timeout=timeout)
    except OperationalError as e:
        raise ConfigError(f"cannot connect to DATABASE_URL ({str(e).splitlines()[0]})") from None
    async with conn:
        counts: dict[str, int] = {}
        for table in TABLES:
            row = await (await conn.execute("select to_regclass(%s)", (table,))).fetchone()
            if row is None or row[0] is None:
                counts[table] = 0
                continue
            cur = await conn.execute(f"select count(*) from {table}")  # fixed table names only
            counts[table] = int((await cur.fetchone() or (0,))[0])
        return counts


async def main() -> int:
    try:
        settings = PersistenceSettings.from_env()
        before = await applied(settings)
        async with open_persistence(settings) as p:
            await setup(p)
        after = await applied(settings)
    except ConfigError as e:
        print(f"ConfigError: {e}", file=sys.stderr)
        return 2
    new = {t: after[t] - before[t] for t in TABLES}
    detail = ", ".join(f"{t} {after[t]} (+{new[t]})" for t in TABLES)
    verdict = "no new migrations" if not any(new.values()) else f"{sum(new.values())} applied"
    print(f"setup: {verdict}; {detail}; agentkit_usage ready")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
