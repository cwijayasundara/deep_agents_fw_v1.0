from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import cache

from agentkit_core import Settings
from langchain_postgres import PGEngine, PGVectorStore
from sqlalchemy.ext.asyncio import AsyncEngine

from .embeddings import get_embeddings
from .secrets import EnvSecrets, SecretsProvider
from .spec import PgVectorSpec

KB_SCHEMA = "kb"  # knowledge-base tables live here; `agentkit-kb setup` grants kb_reader SELECT


def _async_url(dsn: str) -> str:
    for plain in ("postgresql://", "postgres://"):
        if dsn.startswith(plain):
            return "postgresql+asyncpg://" + dsn[len(plain) :]
    return dsn


@cache
def get_engine(dsn: str) -> PGEngine:
    """One pooled engine per DSN per process; the pool connects lazily on first use."""
    return PGEngine.from_connection_string(_async_url(dsn))


async def run_on[T](engine: PGEngine, work: Callable[[AsyncEngine], Awaitable[T]]) -> T:
    """Run `work(pool)` on the engine's own event loop.

    PGEngine binds its asyncpg pool to a background loop; using the pool from any other loop
    breaks pooled connections. langchain-postgres exposes no public accessor for either, so the
    private attributes are read here and nowhere else (pinned langchain-postgres==0.0.19)."""
    return await engine._run_as_async(work(engine._pool))


def get_vectorstore(
    spec: PgVectorSpec, settings: Settings, secrets: SecretsProvider | None = None
) -> PGVectorStore:
    engine = get_engine((secrets or EnvSecrets()).resolve(spec.dsn))
    return PGVectorStore.create_sync(
        engine,
        get_embeddings(spec.embeddings, settings),
        table_name=spec.collection,
        schema_name=KB_SCHEMA,
    )
