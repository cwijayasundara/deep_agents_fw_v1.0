"""Contract: encrypted Postgres checkpoints, concurrent-run behaviour, and store namespaces."""

from __future__ import annotations

import asyncio
import operator
import os
import uuid
from collections import Counter
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager, asynccontextmanager, nullcontext
from datetime import datetime
from typing import Annotated, Any, TypedDict

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.encrypted import EncryptedSerializer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.base import InvalidNamespaceError
from langgraph.store.postgres.aio import AsyncPostgresStore
from psycopg import AsyncConnection
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

DB_URL = os.environ.get("AGENTKIT_TEST_DATABASE_URL", "")
AES_KEY = "0123456789abcdef0123456789abcdef"

pytestmark = [
    pytest.mark.pg,
    pytest.mark.skipif(not DB_URL, reason="AGENTKIT_TEST_DATABASE_URL is not set"),
]


class Turns(TypedDict, total=False):
    turns: Annotated[list[str], operator.add]
    note: str


async def _slow_node(state: Turns) -> Turns:
    await asyncio.sleep(0.3)
    return {"turns": []}


@pytest.fixture
async def pool() -> AsyncIterator[AsyncConnectionPool[Any]]:
    kwargs = {"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row}
    async with AsyncConnectionPool(DB_URL, kwargs=kwargs, open=False) as p:
        yield p


@pytest.fixture
async def app(
    pool: AsyncConnectionPool[Any], monkeypatch: pytest.MonkeyPatch
) -> CompiledStateGraph[Any, Any, Any, Any]:
    monkeypatch.setenv("LANGGRAPH_AES_KEY", AES_KEY)
    saver = AsyncPostgresSaver(pool, serde=EncryptedSerializer.from_pycryptodome_aes())
    await saver.setup()
    graph = StateGraph(Turns)
    graph.add_node("work", _slow_node)
    graph.add_edge(START, "work")
    graph.add_edge("work", END)
    return graph.compile(checkpointer=saver)


@pytest.fixture
async def store(pool: AsyncConnectionPool[Any]) -> AsyncPostgresStore:
    s = AsyncPostgresStore(pool)
    await s.setup()
    return s


def _thread() -> RunnableConfig:
    return {"configurable": {"thread_id": f"contract-{uuid.uuid4()}"}}


async def _rows(pool: AsyncConnectionPool[Any], sql: str, *args: Any) -> list[dict[str, Any]]:
    async with pool.connection() as conn:
        cur = await conn.execute(sql, args)
        rows: list[dict[str, Any]] = await cur.fetchall()
        return rows


async def test_encrypted_roundtrip_leaves_no_plaintext_in_blobs(
    app: CompiledStateGraph[Any, Any, Any, Any], pool: AsyncConnectionPool[Any]
) -> None:
    cfg = _thread()
    tid = cfg["configurable"]["thread_id"]
    await app.ainvoke({"turns": ["PINEAPPLE"], "note": "MANGO"}, cfg)

    assert (await app.aget_state(cfg)).values == {"turns": ["PINEAPPLE"], "note": "MANGO"}
    for table in ("checkpoint_blobs", "checkpoint_writes"):
        rows = await _rows(
            pool,
            f"select type, position('PINEAPPLE'::bytea in blob) > 0 as leak "
            f"from {table} where thread_id = %s",
            tid,
        )
        assert rows, f"{table} has no rows for the thread"
        assert {r["type"] for r in rows} <= {"msgpack+aes", "null+aes"}
        assert not any(r["leak"] for r in rows)

    checkpoints = await _rows(
        pool,
        "select checkpoint::text as body, checkpoint->>'ts' as ts "
        "from checkpoints where thread_id = %s",
        tid,
    )
    assert all(datetime.fromisoformat(r["ts"]) for r in checkpoints)
    assert not any("PINEAPPLE" in r["body"] for r in checkpoints)
    # Primitive (str/int/...) channel values are stored inline, in plaintext JSONB.
    assert any("MANGO" in r["body"] for r in checkpoints)


@asynccontextmanager
async def _advisory_lock(thread_id: str) -> AsyncIterator[None]:
    async with await AsyncConnection.connect(DB_URL, autocommit=True) as conn:
        await conn.execute("select pg_advisory_lock(hashtext(%s))", (thread_id,))
        try:
            yield
        finally:
            await conn.execute("select pg_advisory_unlock(hashtext(%s))", (thread_id,))


async def _two_concurrent_turns(
    app: CompiledStateGraph[Any, Any, Any, Any], *, locked: bool
) -> tuple[list[str], Counter[str | None]]:
    cfg = _thread()
    tid = cfg["configurable"]["thread_id"]
    await app.ainvoke({"turns": ["t0"]}, cfg)

    async def turn(text: str) -> None:
        lock: AbstractAsyncContextManager[None] = _advisory_lock(tid) if locked else nullcontext()
        async with lock:
            await app.ainvoke({"turns": [text]}, cfg)

    await asyncio.gather(turn("a"), turn("b"))
    final = (await app.aget_state(cfg)).values["turns"]
    parents: Counter[str | None] = Counter()
    async for snap in app.aget_state_history(cfg):
        parent = snap.parent_config
        parents[parent["configurable"]["checkpoint_id"] if parent else None] += 1
    return final, parents


async def test_two_concurrent_runs_on_one_thread_lose_an_update(
    app: CompiledStateGraph[Any, Any, Any, Any],
) -> None:
    final, parents = await _two_concurrent_turns(app, locked=False)
    assert final[0] == "t0"
    assert len(final) == 2, f"expected a lost update, got {final}"
    assert max(parents.values()) > 1, "expected the chain to fork"


async def test_advisory_lock_serializes_runs_into_one_linear_chain(
    app: CompiledStateGraph[Any, Any, Any, Any],
) -> None:
    final, parents = await _two_concurrent_turns(app, locked=True)
    assert final[0] == "t0"
    assert sorted(final[1:]) == ["a", "b"]
    assert max(parents.values()) == 1, f"chain forked: {parents}"


async def test_asearch_default_limit_is_ten(store: AsyncPostgresStore) -> None:
    prefix = f"lim-{uuid.uuid4().hex}"
    for i in range(12):
        await store.aput((prefix, "docs"), f"k{i}", {"i": i})
    assert len(await store.asearch((prefix,))) == 10
    assert len(await store.asearch((prefix,), limit=100)) == 12


async def test_asearch_prefix_matches_whole_labels(store: AsyncPostgresStore) -> None:
    tenant = f"t{uuid.uuid4().hex[:8]}"
    await store.aput((tenant, "memories"), "k", {"v": "a"})
    await store.aput((f"{tenant}b", "memories"), "k", {"v": "ab"})
    found = await store.asearch((tenant,), limit=100)
    assert [item.namespace for item in found] == [(tenant, "memories")]


async def test_label_with_a_dot_is_rejected(store: AsyncPostgresStore) -> None:
    with pytest.raises(InvalidNamespaceError):
        await store.aput(("acme.corp", "memories"), "k", {"v": 1})
