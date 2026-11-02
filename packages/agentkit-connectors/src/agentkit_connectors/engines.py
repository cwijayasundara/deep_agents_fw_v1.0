from __future__ import annotations

from functools import cache

from agentkit_core import Settings
from langchain_postgres import PGEngine, PGVectorStore

from .embeddings import get_embeddings
from .secrets import EnvSecrets, SecretsProvider
from .spec import PgVectorSpec


def _async_url(dsn: str) -> str:
    for plain in ("postgresql://", "postgres://"):
        if dsn.startswith(plain):
            return "postgresql+asyncpg://" + dsn[len(plain) :]
    return dsn


@cache
def get_engine(dsn: str) -> PGEngine:
    """One pooled engine per DSN per process; the pool connects lazily on first use."""
    return PGEngine.from_connection_string(_async_url(dsn))


def get_vectorstore(
    spec: PgVectorSpec, settings: Settings, secrets: SecretsProvider | None = None
) -> PGVectorStore:
    engine = get_engine((secrets or EnvSecrets()).resolve(spec.dsn))
    return PGVectorStore.create_sync(
        engine, get_embeddings(spec.embeddings, settings), table_name=spec.collection
    )
