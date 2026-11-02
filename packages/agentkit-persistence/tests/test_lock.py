from __future__ import annotations

import asyncio
import operator
from collections import Counter
from typing import Annotated, Any, TypedDict

import pytest
from agentkit_persistence import Persistence, thread_lock
from langgraph.graph import END, START, StateGraph

pytestmark = pytest.mark.pg


class Turns(TypedDict, total=False):
    turns: Annotated[list[str], operator.add]


async def _slow(state: Turns) -> Turns:
    await asyncio.sleep(0.3)
    return {"turns": []}


def _graph(p: Persistence) -> Any:
    g = StateGraph(Turns)
    g.add_node("work", _slow)
    g.add_edge(START, "work")
    g.add_edge("work", END)
    return g.compile(checkpointer=p.saver)


async def test_two_concurrent_locked_runs_make_one_linear_chain(
    persistence: Persistence, thread_id: str
) -> None:
    app = _graph(persistence)
    cfg: Any = {"configurable": {"thread_id": thread_id}}
    await app.ainvoke({"turns": ["t0"]}, cfg)

    async def turn(text: str) -> None:
        async with thread_lock(persistence, thread_id):
            await app.ainvoke({"turns": [text]}, cfg)

    await asyncio.gather(turn("a"), turn("b"))
    final = (await app.aget_state(cfg)).values["turns"]
    assert final[0] == "t0" and sorted(final[1:]) == ["a", "b"]
    parents: Counter[str | None] = Counter()
    async for snap in app.aget_state_history(cfg):
        parent = snap.parent_config
        parents[parent["configurable"]["checkpoint_id"] if parent else None] += 1
    assert max(parents.values()) == 1, f"chain forked: {parents}"


async def test_lock_uses_the_lock_pool_and_releases(
    persistence: Persistence, thread_id: str
) -> None:
    async with thread_lock(persistence, thread_id):
        assert persistence.lock_pool.get_stats()["pool_size"] >= 1
        async with persistence.pool.connection() as conn:
            cur = await conn.execute(
                "select pg_try_advisory_lock(hashtext(%s)) as got", (thread_id,)
            )
            assert not (await cur.fetchone())["got"], "lock not held while inside"
    async with persistence.pool.connection() as conn:
        cur = await conn.execute("select pg_try_advisory_lock(hashtext(%s)) as got", (thread_id,))
        assert (await cur.fetchone())["got"], "lock not released on exit"
        await conn.execute("select pg_advisory_unlock(hashtext(%s))", (thread_id,))


async def test_lock_releases_when_the_body_raises(persistence: Persistence, thread_id: str) -> None:
    with pytest.raises(RuntimeError):
        async with thread_lock(persistence, thread_id):
            raise RuntimeError("boom")
    async with thread_lock(persistence, thread_id):
        pass


async def test_lock_pool_reset_releases_a_leaked_session_lock(
    persistence: Persistence, thread_id: str
) -> None:
    # Simulate a cancelled unlock: take the lock and return the connection still holding it.
    async with persistence.lock_pool.connection() as conn:
        await conn.execute("select pg_advisory_lock(hashtext(%s))", (thread_id,))
    await asyncio.sleep(0.2)  # the pool runs `reset` in a background worker
    async with persistence.pool.connection() as conn:
        cur = await conn.execute("select pg_try_advisory_lock(hashtext(%s)) as got", (thread_id,))
        assert (await cur.fetchone())["got"], "lock leaked past the lock pool's reset"
        await conn.execute("select pg_advisory_unlock(hashtext(%s))", (thread_id,))
