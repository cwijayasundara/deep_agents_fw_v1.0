"""Open the encrypted Postgres saver and store that back threads and memory.

Checkpoint blobs and writes are AES-encrypted (`msgpack+aes`). Two things stay plaintext JSONB
in `checkpoints`: the `metadata` column, and primitive (str/int/float/bool) top-level state
channels, which LangGraph stores inline in `checkpoint` (Ruling P3). Containers such as
`messages` and `files` are encrypted. Keep user content and secrets out of metadata and out of
primitive top-level channels.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentkit_core import ConfigError
from agentkit_core.settings import find_env_file
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.encrypted import EncryptedSerializer
from langgraph.store.base import TTLConfig
from langgraph.store.postgres.aio import AsyncPostgresStore
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool
from pydantic import Field, SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

AES_KEY_ERROR = "LANGGRAPH_AES_KEY must be 16, 24, or 32 characters"
DATABASE_URL_ERROR = "DATABASE_URL must be set to a Postgres connection URL"
_AES_KEY_LENGTHS = (16, 24, 32)
_SWEEP_INTERVAL_MINUTES = 5


class PersistenceSettings(BaseSettings):
    """Database and encryption settings, read from process env, then the nearest `.env`."""

    model_config = SettingsConfigDict(extra="ignore")

    database_url: SecretStr
    langgraph_aes_key: SecretStr
    pool_max_size: int = Field(default=10, ge=1)
    lock_pool_max_size: int = Field(default=20, ge=1)
    store_default_ttl_minutes: int | None = Field(default=None, ge=1)

    @classmethod
    def from_env(cls, env_file: Path | None | str = "auto") -> PersistenceSettings:
        """Load from the environment, turning missing values into a `ConfigError`."""
        path = find_env_file() if env_file == "auto" else env_file
        try:
            settings = cls(_env_file=path)  # type: ignore[call-arg]
        except ValidationError as exc:
            missing = {str(e["loc"][0]) for e in exc.errors() if e["type"] == "missing"}
            if "langgraph_aes_key" in missing:
                raise ConfigError(AES_KEY_ERROR) from None
            if "database_url" in missing:
                raise ConfigError(DATABASE_URL_ERROR) from None
            raise ConfigError(str(exc)) from None
        check_aes_key(settings.langgraph_aes_key)
        return settings


def check_aes_key(key: SecretStr) -> bytes:
    """The raw AES key bytes; `ConfigError` unless it is 16, 24, or 32 bytes long."""
    raw = key.get_secret_value().encode()
    if len(raw) not in _AES_KEY_LENGTHS:
        raise ConfigError(AES_KEY_ERROR)
    return raw


@dataclass(frozen=True)
class Persistence:
    """One deployment's Postgres handles. `lock_pool` only serves `thread_lock`."""

    pool: AsyncConnectionPool[Any]
    lock_pool: AsyncConnectionPool[Any]
    saver: AsyncPostgresSaver
    store: AsyncPostgresStore


def _pool(url: str, max_size: int, name: str) -> AsyncConnectionPool[Any]:
    kwargs = {"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row}
    return AsyncConnectionPool(
        url, min_size=1, max_size=max_size, kwargs=kwargs, name=name, open=False
    )


@asynccontextmanager
async def open_persistence(settings: PersistenceSettings) -> AsyncIterator[Persistence]:
    """Open pools, set up the encrypted saver and the TTL store, and close all on exit."""
    key = check_aes_key(settings.langgraph_aes_key)
    url = settings.database_url.get_secret_value()
    serde = EncryptedSerializer.from_pycryptodome_aes(key=key)
    ttl = TTLConfig(
        default_ttl=settings.store_default_ttl_minutes,
        sweep_interval_minutes=_SWEEP_INTERVAL_MINUTES,
    )
    async with (
        _pool(url, settings.pool_max_size, "agentkit-saver") as pool,
        _pool(url, settings.lock_pool_max_size, "agentkit-lock") as lock_pool,
    ):
        saver = AsyncPostgresSaver(pool, serde=serde)
        store = AsyncPostgresStore(pool, ttl=ttl)
        await saver.setup()
        await store.setup()
        await store.start_ttl_sweeper()
        try:
            yield Persistence(pool=pool, lock_pool=lock_pool, saver=saver, store=store)
        finally:
            await store.stop_ttl_sweeper(timeout=5)
