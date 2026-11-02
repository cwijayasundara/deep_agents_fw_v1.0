"""The cost ledger: one usage row per agent run, written to `agentkit_usage` through Persistence.

`on_llm_end` carries `usage_metadata` but not the run's metadata, and `on_chat_model_start`
carries the metadata but no usage, so the ledger maps every run id to its root run and sums
there. Decisions selection usage arrives as a `DECISIONS_USAGE_EVENT` custom event. A run with
no model call and no selection (e.g. one the tenant guard refused) writes no row.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import astuple, dataclass, field, fields
from typing import TYPE_CHECKING, Any
from uuid import UUID

from agentkit_middleware import DECISIONS_USAGE_EVENT
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult

if TYPE_CHECKING:
    from agentkit_persistence import Persistence

log = logging.getLogger(__name__)

_DDL = (
    """create table if not exists agentkit_usage (
        run_id uuid primary key,
        tenant text not null,
        thread_id text not null,
        model text not null,
        input_tokens bigint not null,
        output_tokens bigint not null,
        cached_input_tokens bigint not null,
        decisions_input_tokens bigint not null,
        decisions_output_tokens bigint not null,
        created_at timestamptz not null default now()
    )""",
    "create index if not exists agentkit_usage_tenant_created on agentkit_usage"
    " (tenant, created_at)",
)


@dataclass(frozen=True)
class UsageRow:
    tenant: str
    thread_id: str
    run_id: UUID
    model: str
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    decisions_input_tokens: int
    decisions_output_tokens: int


_COLUMNS = ", ".join(f.name for f in fields(UsageRow))
_INSERT = (
    f"insert into agentkit_usage ({_COLUMNS}) values ({', '.join(['%s'] * len(fields(UsageRow)))})"
    " on conflict (run_id) do nothing"
)


async def setup(persistence: Persistence) -> None:
    """Create `agentkit_usage` if it is missing (idempotent; Ruling P1).

    Runs in one transaction under an advisory lock: concurrent first-time `create table if not
    exists` calls can otherwise fail on Postgres's catalog unique index."""
    async with persistence.pool.connection() as conn, conn.transaction():
        await conn.execute("select pg_advisory_xact_lock(hashtext('agentkit_usage'))")
        for statement in _DDL:
            await conn.execute(statement)


@dataclass
class _Run:
    tenant: str
    thread_id: str
    models: set[str] = field(default_factory=set)
    calls: int = 0
    input: int = 0
    output: int = 0
    cached: int = 0
    decisions_input: int = 0
    decisions_output: int = 0


class CostLedger(AsyncCallbackHandler):
    """Callback handler that aggregates token usage per root run into `rows` (and Postgres)."""

    def __init__(self, persistence: Persistence | None = None) -> None:
        self.persistence = persistence
        self.rows: list[UsageRow] = []
        self.model_calls = 0
        self._runs: dict[UUID, _Run] = {}  # root run id -> its running totals
        self._root: dict[UUID, UUID] = {}  # every live run id -> its root run id

    def row(self, run_id: UUID) -> UsageRow | None:
        return next((r for r in self.rows if r.run_id == run_id), None)

    def summary(self) -> str:
        n = len(self.rows)
        i = sum(r.input_tokens for r in self.rows)
        o = sum(r.output_tokens for r in self.rows)
        c = sum(r.cached_input_tokens for r in self.rows)
        di = sum(r.decisions_input_tokens for r in self.rows)
        return (
            f"usage: {n} run{'s' if n != 1 else ''}, {self.model_calls} model calls,"
            f" input {i} (cached {c}), output {o}, decisions input {di}"
        )

    def _track(
        self, run_id: UUID, parent_run_id: UUID | None, metadata: Mapping[str, Any] | None
    ) -> _Run | None:
        if parent_run_id is None:
            md = metadata or {}
            self._root[run_id] = run_id
            run = _Run(str(md.get("tenant", "")), str(md.get("thread_id", "")))
            self._runs[run_id] = run
            return run
        root = self._root.get(parent_run_id)
        if root is None:
            return None
        self._root[run_id] = root
        return self._runs.get(root)

    def _of(self, run_id: UUID) -> _Run | None:
        root = self._root.get(run_id)
        return self._runs.get(root) if root is not None else None

    async def on_chain_start(self, serialized: Any, inputs: Any, **kw: Any) -> None:
        self._track(kw["run_id"], kw.get("parent_run_id"), kw.get("metadata"))

    async def on_tool_start(self, serialized: Any, input_str: str, **kw: Any) -> None:
        self._track(kw["run_id"], kw.get("parent_run_id"), kw.get("metadata"))

    async def on_chat_model_start(self, serialized: Any, messages: Any, **kw: Any) -> None:
        self._model_start(serialized, kw)

    async def on_llm_start(self, serialized: Any, prompts: Any, **kw: Any) -> None:
        self._model_start(serialized, kw)

    def _model_start(self, serialized: Any, kw: Mapping[str, Any]) -> None:
        md = kw.get("metadata") or {}
        run = self._track(kw["run_id"], kw.get("parent_run_id"), md)
        if run is None:
            return
        run.tenant = run.tenant or str(md.get("tenant", ""))
        name = md.get("ls_model_name") or (serialized or {}).get("name") or "unknown"
        run.models.add(str(name))

    async def on_llm_end(self, response: LLMResult, **kw: Any) -> None:
        run = self._of(kw["run_id"])
        if run is not None:
            run.calls += 1
            for gen in (g for gens in response.generations for g in gens):
                usage = getattr(getattr(gen, "message", None), "usage_metadata", None) or {}
                run.input += usage.get("input_tokens", 0)
                run.output += usage.get("output_tokens", 0)
                run.cached += (usage.get("input_token_details") or {}).get("cache_read", 0)
        await self._end(kw["run_id"])

    async def on_custom_event(self, name: str, data: Any, **kw: Any) -> None:
        run = self._of(kw["run_id"])
        if name == DECISIONS_USAGE_EVENT and run is not None and isinstance(data, Mapping):
            run.decisions_input += int(data.get("input_tokens", 0))
            run.decisions_output += int(data.get("output_tokens", 0))

    async def on_chain_end(self, outputs: Any, **kw: Any) -> None:
        await self._end(kw["run_id"])

    async def on_chain_error(self, error: BaseException, **kw: Any) -> None:
        await self._end(kw["run_id"])

    async def on_llm_error(self, error: BaseException, **kw: Any) -> None:
        await self._end(kw["run_id"])

    async def _end(self, run_id: UUID) -> None:
        run = self._runs.pop(run_id, None)
        if run is None:  # not a root run
            return
        self._root = {k: v for k, v in self._root.items() if v != run_id}
        if run.calls == 0 and not (run.decisions_input or run.decisions_output):
            return
        row = UsageRow(
            tenant=run.tenant,
            thread_id=run.thread_id,
            run_id=run_id,
            model=",".join(sorted(run.models)) or "unknown",
            input_tokens=run.input,
            output_tokens=run.output,
            cached_input_tokens=run.cached,
            decisions_input_tokens=run.decisions_input,
            decisions_output_tokens=run.decisions_output,
        )
        self.rows.append(row)
        self.model_calls += run.calls
        if self.persistence is not None:
            await self._write(self.persistence, row)

    async def _write(self, p: Persistence, row: UsageRow) -> None:
        try:
            async with p.pool.connection() as conn:
                await conn.execute(_INSERT, astuple(row))
        except Exception as e:  # a lost usage row must not fail the run
            reason = f"{type(e).__name__}: {e}"
            log.warning("usage row for run %s not written (%s)", row.run_id, reason)
