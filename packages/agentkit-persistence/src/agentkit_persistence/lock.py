"""Serialize runs on one thread with a Postgres advisory lock.

Two concurrent runs on one thread fork the checkpoint chain and lose an update; holding
`pg_advisory_lock(hashtext(thread_id))` across each run serializes them into one chain. The lock
pins a connection for the whole run, so it comes from `Persistence.lock_pool`, never the saver's
pool: a run waiting on the lock cannot starve the saver of connections. `hashtext` is 32-bit, so
two different threads can rarely share a lock; that only serializes them, it never merges state.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from .open import Persistence


@asynccontextmanager
async def thread_lock(persistence: Persistence, thread_id: str) -> AsyncIterator[None]:
    """Hold the thread's advisory lock for the duration of the block."""
    async with persistence.lock_pool.connection() as conn:
        await conn.execute("select pg_advisory_lock(hashtext(%s))", (thread_id,))
        try:
            yield
        finally:
            await conn.execute("select pg_advisory_unlock(hashtext(%s))", (thread_id,))
