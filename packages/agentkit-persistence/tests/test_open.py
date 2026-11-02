from __future__ import annotations

import operator
import uuid
from typing import Annotated, Any, TypedDict

import pytest
from agentkit_core import ConfigError, PlatformContext, store_namespace
from agentkit_persistence import Persistence, PersistenceSettings, open_persistence
from langgraph.graph import END, START, StateGraph
from pydantic import SecretStr

KEY_ERROR = "LANGGRAPH_AES_KEY must be 16, 24, or 32 characters"


class Turns(TypedDict, total=False):
    turns: Annotated[list[str], operator.add]


def _noop(state: Turns) -> Turns:
    return {"turns": []}


def _graph(p: Persistence) -> Any:
    g = StateGraph(Turns)
    g.add_node("work", _noop)
    g.add_edge(START, "work")
    g.add_edge("work", END)
    return g.compile(checkpointer=p.saver, store=p.store)


@pytest.mark.parametrize("key", ["", "short", "x" * 31, "x" * 33])
async def test_bad_aes_key_refuses_to_start(key: str) -> None:
    settings = PersistenceSettings(
        database_url=SecretStr("postgresql://unused@127.0.0.1:1/x"),
        langgraph_aes_key=SecretStr(key),
    )
    with pytest.raises(ConfigError, match=KEY_ERROR):
        async with open_persistence(settings):
            pass


def test_from_env_with_key_unset_raises_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://a@b/c")
    monkeypatch.delenv("LANGGRAPH_AES_KEY", raising=False)
    with pytest.raises(ConfigError, match=KEY_ERROR):
        PersistenceSettings.from_env(env_file=None)


def test_from_env_requires_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("LANGGRAPH_AES_KEY", "k" * 16)
    with pytest.raises(ConfigError, match="DATABASE_URL must be set"):
        PersistenceSettings.from_env(env_file=None)


def test_from_env_reads_both_and_hides_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://a@b/c")
    monkeypatch.setenv("LANGGRAPH_AES_KEY", "k" * 24)
    s = PersistenceSettings.from_env(env_file=None)
    assert s.database_url.get_secret_value() == "postgresql://a@b/c"
    assert (s.pool_max_size, s.lock_pool_max_size, s.store_default_ttl_minutes) == (10, 20, None)
    assert "k" * 24 not in repr(s)


@pytest.mark.pg
async def test_setup_is_idempotent(pg_settings: Any) -> None:
    for _ in range(2):
        async with open_persistence(pg_settings()) as p:
            assert p.pool is not p.lock_pool
            async with p.pool.connection() as conn:
                cur = await conn.execute("select to_regclass('checkpoints') is not null as ok")
                assert (await cur.fetchone())["ok"]


@pytest.mark.pg
async def test_encrypted_roundtrip(persistence: Persistence, thread_id: str) -> None:
    app = _graph(persistence)
    cfg: Any = {"configurable": {"thread_id": thread_id}}
    await app.ainvoke({"turns": ["PINEAPPLE"]}, cfg)
    assert (await app.aget_state(cfg)).values == {"turns": ["PINEAPPLE"]}
    async with persistence.pool.connection() as conn:
        cur = await conn.execute(
            "select type, position('PINEAPPLE'::bytea in blob) > 0 as leak "
            "from checkpoint_blobs where thread_id = %s",
            (thread_id,),
        )
        rows: list[dict[str, Any]] = await cur.fetchall()
    assert rows and all(r["type"].endswith("+aes") and not r["leak"] for r in rows)


@pytest.mark.pg
async def test_store_write_under_store_namespace(persistence: Persistence, thread_id: str) -> None:
    tenant = f"t{uuid.uuid4().hex[:8]}"
    ctx = PlatformContext(
        tenant=tenant,
        product="agentkit",
        team="platform",
        user_id="u1",
        thread_id=thread_id,
        agent_name="research_agent",
        agent_version="0.1.0",
    )
    ns = store_namespace(ctx, "user", "memories")
    await persistence.store.aput(ns, "note", {"text": "hello"})
    found = await persistence.store.asearch((tenant,), limit=100)
    assert [(i.namespace, i.key, i.value) for i in found] == [(ns, "note", {"text": "hello"})]


async def test_unreachable_database_raises_one_line_config_error() -> None:
    settings = PersistenceSettings(
        database_url=SecretStr("postgresql://agentkit:pw@127.0.0.1:1/agentkit"),
        langgraph_aes_key=SecretStr("k" * 32),
        connect_timeout_seconds=0.5,
    )
    with pytest.raises(ConfigError, match="cannot connect to DATABASE_URL") as info:
        async with open_persistence(settings):
            pass
    assert "\n" not in str(info.value) and "pw" not in str(info.value)
