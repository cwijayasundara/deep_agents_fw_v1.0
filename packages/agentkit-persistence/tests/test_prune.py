from __future__ import annotations

import operator
from datetime import timedelta
from typing import Annotated, TypedDict

import pytest
from agentkit_persistence import Persistence, prune
from agentkit_persistence.prune import main, parse_age
from langgraph.graph import END, START, StateGraph


class Turns(TypedDict, total=False):
    turns: Annotated[list[str], operator.add]


def _noop(state: Turns) -> Turns:
    return {"turns": []}


async def _seed(p: Persistence, thread_id: str) -> None:
    g = StateGraph(Turns)
    g.add_node("work", _noop)
    g.add_edge(START, "work")
    g.add_edge("work", END)
    await g.compile(checkpointer=p.saver).ainvoke(
        {"turns": ["x"]}, {"configurable": {"thread_id": thread_id}}
    )


async def _backdate(p: Persistence, thread_id: str, days: int) -> None:
    async with p.pool.connection() as conn:
        await conn.execute(
            "update checkpoints set checkpoint = jsonb_set(checkpoint, '{ts}', "
            "to_jsonb(to_char((now() - make_interval(days => %s)) at time zone 'UTC', "
            '\'YYYY-MM-DD"T"HH24:MI:SS.US"+00:00"\'))) where thread_id = %s',
            (days, thread_id),
        )


async def _exists(p: Persistence, thread_id: str) -> bool:
    async with p.pool.connection() as conn:
        cur = await conn.execute(
            "select count(*) as n from checkpoints where thread_id = %s", (thread_id,)
        )
        row = await cur.fetchone()
        return bool(row["n"])


@pytest.mark.parametrize(
    ("text", "age"),
    [("30d", timedelta(days=30)), ("12h", timedelta(hours=12)), ("45m", timedelta(minutes=45))],
)
def test_parse_age(text: str, age: timedelta) -> None:
    assert parse_age(text) == age


@pytest.mark.parametrize("text", ["", "30", "d", "-1d", "3w", "1.5d"])
def test_parse_age_rejects(text: str) -> None:
    with pytest.raises(ValueError, match="older-than"):
        parse_age(text)


def test_cli_without_aes_key_prints_config_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://unused@127.0.0.1:1/x")
    monkeypatch.delenv("LANGGRAPH_AES_KEY", raising=False)
    monkeypatch.setattr("agentkit_persistence.open.find_env_file", lambda: None)
    assert main(["--older-than", "30d"]) == 2
    err = capsys.readouterr().err
    assert "ConfigError: LANGGRAPH_AES_KEY must be 16, 24, or 32 characters" in err


@pytest.mark.pg
async def test_prune_deletes_old_keeps_fresh_and_is_idempotent(
    persistence: Persistence, thread_id: str
) -> None:
    old, fresh = f"{thread_id}-old", f"{thread_id}-fresh"
    await _seed(persistence, old)
    await _seed(persistence, fresh)
    await _backdate(persistence, old, 40)

    assert await prune(persistence, timedelta(days=30)) >= 1
    assert not await _exists(persistence, old)
    assert await _exists(persistence, fresh)
    assert await prune(persistence, timedelta(days=30)) == 0


def test_cli_unreachable_database_exits_2_with_one_line(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://agentkit:pw@127.0.0.1:1/agentkit")
    monkeypatch.setenv("LANGGRAPH_AES_KEY", "k" * 32)
    monkeypatch.setenv("PG_CONNECT_TIMEOUT_SECONDS", "0.5")
    monkeypatch.setattr("agentkit_persistence.open.find_env_file", lambda: None)
    assert main(["--older-than", "30d"]) == 2
    err = capsys.readouterr().err
    assert err.startswith("ConfigError: cannot connect to DATABASE_URL") and err.count("\n") == 1
