"""Shared fixtures for the persistence tests.

`pg` tests use AGENTKIT_TEST_DATABASE_URL and skip (naming that variable) when it is unset.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Callable

import pytest
from agentkit_persistence import Persistence, PersistenceSettings, open_persistence
from pydantic import SecretStr

AES_KEY = "0123456789abcdef0123456789abcdef"
SettingsFactory = Callable[..., PersistenceSettings]


def _db_url() -> str:
    url = os.environ.get("AGENTKIT_TEST_DATABASE_URL", "")
    if not url:
        pytest.skip("AGENTKIT_TEST_DATABASE_URL is not set")
    return url


@pytest.fixture
def pg_settings() -> SettingsFactory:
    url = _db_url()

    def make(**overrides: object) -> PersistenceSettings:
        values: dict[str, object] = {
            "database_url": SecretStr(url),
            "langgraph_aes_key": SecretStr(AES_KEY),
        }
        return PersistenceSettings.model_validate({**values, **overrides})

    return make


@pytest.fixture
async def persistence(pg_settings: SettingsFactory) -> AsyncIterator[Persistence]:
    async with open_persistence(pg_settings()) as p:
        yield p


@pytest.fixture
def thread_id() -> str:
    return f"persist-{uuid.uuid4()}"
