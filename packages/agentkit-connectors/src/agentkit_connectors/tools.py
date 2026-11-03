"""Curated connector tools: `kb_search` (pgvector) and `sql_query` (read-only Postgres).

Agents reach databases only through these two tools; raw SQL toolkits are never exposed.
`sql_query` safety is layered (plan Decision 7), and the database role is the real wall:
  1. the connector's DSN logs in as `kb_reader` (`agentkit-kb setup`: SELECT on schema `kb` only,
     `default_transaction_read_only=on`);
  2. every call runs in `BEGIN READ ONLY` and is rolled back;
  3. `SET LOCAL search_path` is the connector's `schemas`;
  4. one statement only: anything after a `;` is refused before the database is touched, and the
     server-side prepared statement cannot hold two commands either;
  5. `SET LOCAL statement_timeout`;
  6. at most `max_rows` rows are fetched (a cursor, not the full result).
Tools return `ERROR: ...` text instead of raising; messages never carry a DSN.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from agentkit_core import BuildContext, ConfigError, resolve_secret
from agentkit_tools import platform_tool
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.tools import BaseTool, StructuredTool
from langchain_postgres import PGEngine, PGVectorStore
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine

from .embeddings import get_embeddings
from .engines import KB_SCHEMA, get_engine, run_on
from .spec import PgVectorSpec, PostgresSpec, library_roots, load_connector

log = logging.getLogger(__name__)

# Extra seconds the client waits beyond statement_timeout before giving up (connect, network).
_CLIENT_GRACE_S = 10.0


class KbError(Exception):
    """A knowledge-base failure whose message is safe to show the agent."""


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


# --- connector resolution -------------------------------------------------------------------

_KINDS: dict[type, str] = {PgVectorSpec: "pgvector", PostgresSpec: "postgres"}


def _kind_problem(name: str, spec: PgVectorSpec | PostgresSpec, tool: str, want: type) -> str:
    return f"connector {name!r} is a {spec.kind} connector; {tool} needs {_KINDS[want]}"


def _connector[S: (PgVectorSpec, PostgresSpec)](
    ctx: BuildContext, name: str, tool: str, want: type[S]
) -> S:
    """Resolve through the roots the agent was validated against (`ctx.library_roots`, set by
    resolve); fall back to cwd / AGENTKIT_LIBRARY_PATH discovery for bare factory calls."""
    roots = ctx.library_roots if ctx.library_roots is not None else library_roots()
    spec = load_connector(name, roots)
    if not isinstance(spec, want):
        raise ConfigError(_kind_problem(name, spec, tool, want))
    return spec


def _validator(tool: str, want: type) -> Callable[[Mapping[str, Any], Any], list[str]]:
    """The `__agentkit_validate__` hook (ruling S3): check `params.connector` against the
    validating library's roots. agentkit-config calls it without importing this package."""

    def check(params: Mapping[str, Any], library: Any) -> list[str]:
        name = params.get("connector")
        if not isinstance(name, str) or not name:
            return [f"{tool} needs params.connector (a connector name)"]
        try:
            spec = load_connector(name, getattr(library, "roots", ()))
        except ConfigError as e:
            return [str(e)]
        return [] if isinstance(spec, want) else [_kind_problem(name, spec, tool, want)]

    return check


# --- kb_search ------------------------------------------------------------------------------


class KbSearchArgs(BaseModel):
    query: str = Field(
        description="What to look up in the knowledge base, phrased as a focused search query."
    )
    k: int | None = Field(
        default=None,
        ge=1,
        le=10,
        description="How many passages to return (1-10); omit for the configured default.",
    )


class KnowledgeBase(Protocol):
    async def search(self, query: str, k: int) -> list[Document]: ...


def qualified_table(table: str) -> str:
    """`kb."<table>"`, quoted for SQL."""
    return f"{KB_SCHEMA}.{_quote_ident(table)}"


async def table_dims(pool: AsyncEngine, table: str) -> tuple[bool, int | None]:
    """(table exists, its `embedding` column's dimension or None when unconstrained)."""
    sql = text(
        "select to_regclass(:t) is not null as present, (select a.atttypmod from"
        " pg_attribute a where a.attrelid = to_regclass(:t) and a.attname = 'embedding'"
        " and not a.attisdropped) as dims"
    )
    async with pool.connect() as conn:
        row = (await conn.execute(sql, {"t": qualified_table(table)})).one()
    return bool(row.present), (row.dims if row.dims and row.dims > 0 else None)


class PgKb:
    """A pgvector table in schema `kb`. The store is created on first use and then held, so
    building an agent never touches the database."""

    def __init__(self, engine: PGEngine, embeddings: Embeddings, table: str) -> None:
        self._engine, self._emb, self._table = engine, embeddings, table
        self._store: PGVectorStore | None = None
        self._dims: int | None = None

    async def _open(self) -> PGVectorStore:
        if self._store is None:
            present, dims = await run_on(self._engine, lambda pool: table_dims(pool, self._table))
            if not present:
                raise KbError(
                    f"knowledge base table {KB_SCHEMA}.{self._table} not found;"
                    " run agentkit-kb ingest"
                )
            store = await PGVectorStore.create(
                self._engine, self._emb, table_name=self._table, schema_name=KB_SCHEMA
            )
            self._store, self._dims = store, dims
        return self._store

    async def search(self, query: str, k: int) -> list[Document]:
        store = await self._open()
        vec = await self._emb.aembed_query(query)
        if self._dims is not None and len(vec) != self._dims:
            raise KbError(
                f"embedding dimension mismatch: {KB_SCHEMA}.{self._table} holds"
                f" {self._dims}-dim vectors but the connector's embeddings give {len(vec)};"
                " re-ingest with the connector's embeddings entry"
            )
        return await store.asimilarity_search_by_vector(vec, k=k)


def _db_message(exc: DBAPIError) -> str | None:
    """The server's error text (no DSN in it), or None for client-side/connection failures."""
    orig = exc.orig
    if getattr(orig, "sqlstate", None) is None:
        return None
    msg = str(orig)
    if msg.startswith("<class '") and ">: " in msg:  # SQLAlchemy's asyncpg adapter prefix
        msg = msg.split(">: ", 1)[1]
    return msg.strip().splitlines()[0] if msg.strip() else None


def make_kb_search_tool(kb: KnowledgeBase, *, default_k: int) -> BaseTool:
    """The `kb_search` tool over any KnowledgeBase. Errors come back as `ERROR: ...` text."""

    async def kb_search(query: str, k: int | None = None) -> str:
        """Search the knowledge base. Returns numbered passages, each with title and source URL.

        Use to answer questions from the curated knowledge base, and cite the URLs you use.
        Do not use for live web facts (use web_search) or to query tables (use sql_query).
        """
        try:
            hits = await kb.search(query, k or default_k)
        except KbError as e:
            return f"ERROR: {e}"
        except DBAPIError as e:
            log.warning("kb_search failed: %s", type(e.orig).__name__)
            detail = _db_message(e)
            return f"ERROR: kb search failed: {detail}" if detail else "ERROR: kb search failed"
        except Exception as e:  # embeddings API, connection, driver: never a traceback
            log.warning("kb_search failed: %s", type(e).__name__)
            return f"ERROR: kb search failed ({type(e).__name__})"
        if not hits:
            return "No results."
        return "\n\n".join(
            f"[{i}] {d.metadata.get('title', '')}\n{d.metadata.get('source_url', '')}\n"
            f"{d.page_content}"
            for i, d in enumerate(hits, 1)
        )

    return StructuredTool.from_function(
        coroutine=kb_search, name="kb_search", args_schema=KbSearchArgs
    )


@platform_tool(owner="platform", version="1.0.0", side_effects="read", classification="internal")
def kb_search(ctx: BuildContext, *, connector: str, k: int = 5) -> BaseTool:
    """Semantic search over a pgvector connector's table in schema `kb`."""
    spec = _connector(ctx, connector, "kb_search", PgVectorSpec)
    engine = get_engine(resolve_secret(spec.dsn, ctx.settings))
    kb = PgKb(engine, get_embeddings(spec.embeddings, ctx.settings), spec.collection)
    return make_kb_search_tool(kb, default_k=k)


# --- sql_query ------------------------------------------------------------------------------


class SqlQueryArgs(BaseModel):
    sql: str = Field(
        description="Exactly one read-only SQL statement (usually SELECT); no ';'-separated"
        " statements. Unqualified table names resolve in the connector's schemas."
    )


@dataclass(frozen=True)
class QueryResult:
    columns: list[str] | None  # None: the statement returns no rows
    rows: Sequence[Sequence[Any]]


class SqlRunner(Protocol):
    async def run(self, sql: str) -> QueryResult: ...


class SqlRefused(Exception):
    """A statement refused by the tool or rejected by the database; safe to show the agent."""


NOT_READ_ONLY = "sql_query connector must log in as a read-only role (e.g. kb_reader)"

# Any row means the login could escape a READ ONLY transaction (COPY TO PROGRAM,
# pg_read_file, ...) or write DDL into a configured schema. Membership, not just identity:
# a member of a superuser role can `set_config('role', ...)` inside one statement. Both the
# login (session_user) and the active role (current_user) are checked, and they must match:
# an admin login with a startup `role` (DSN options, server_settings, ALTER ROLE ... SET role)
# gets back to the admin with `set_config('role', 'none', ...)`.
_PRIVILEGE_CHECK = """
select 1 where session_user <> current_user
union all
select 1 from pg_roles r, unnest(array[current_user, session_user]) as u(name)
  where (r.rolsuper or r.rolbypassrls) and pg_has_role(u.name, r.oid, 'member')
union all
select 1 from unnest(array['pg_execute_server_program', 'pg_read_server_files',
                           'pg_write_server_files', 'pg_read_all_data', 'pg_signal_backend',
                           'pg_read_all_settings', 'pg_read_all_stats']) as g(name),
              unnest(array[current_user, session_user]) as u(name)
  where to_regrole(g.name) is not null and pg_has_role(u.name, g.name, 'member')
union all
select 1 from unnest(cast(:schemas as text[])) as s(name),
              unnest(array[current_user, session_user]) as u(name)
  where exists (select 1 from pg_namespace n where n.nspname = s.name)
    and has_schema_privilege(u.name, s.name, 'CREATE')
limit 1
"""


class PgSql:
    """Runs one statement per call in a rolled-back READ ONLY transaction.

    Before the first statement it checks (once per runner, i.e. per connector engine) that the
    login is a low-privilege role, and refuses to run anything otherwise."""

    def __init__(
        self, engine: PGEngine, *, schemas: Sequence[str], timeout_ms: int, fetch: int
    ) -> None:
        self._engine, self._fetch = engine, fetch
        self._timeout_ms = int(timeout_ms)
        self._schemas = list(schemas)
        self._path = ", ".join(_quote_ident(s) for s in schemas)
        self._role_ok = False

    async def _check_role(self, pool: AsyncEngine) -> None:
        async with pool.connect() as conn:
            row = (await conn.execute(text(_PRIVILEGE_CHECK), {"schemas": self._schemas})).first()
            await conn.rollback()
        if row is not None:
            raise SqlRefused(NOT_READ_ONLY)

    async def _work(self, pool: AsyncEngine, sql: str) -> QueryResult:
        if not self._role_ok:
            await self._check_role(pool)
            self._role_ok = True
        async with pool.connect() as conn:
            try:
                # The first execute autobegins the transaction; READ ONLY before any query.
                await conn.exec_driver_sql("SET TRANSACTION READ ONLY")
                await conn.exec_driver_sql(f"SET LOCAL statement_timeout = {self._timeout_ms}")
                await conn.exec_driver_sql(f"SET LOCAL search_path = {self._path}")
                raw = await conn.get_raw_connection()
                pg: Any = raw.driver_connection  # asyncpg.Connection, inside the transaction
                stmt = await pg.prepare(sql)  # a prepared statement holds one command only
                attrs = stmt.get_attributes()
                if attrs:
                    cur = await stmt.cursor()
                    rows = [tuple(r) for r in await cur.fetch(self._fetch)]
                    result = QueryResult([a.name for a in attrs], rows)
                else:
                    await stmt.fetch()
                    result = QueryResult(None, [])
                if not pg.is_in_transaction():
                    raise SqlRefused("transaction control statements are not allowed")
                return result
            finally:
                await conn.rollback()
                # Session-level advisory locks survive ROLLBACK; never return one to the pool.
                await conn.exec_driver_sql("select pg_advisory_unlock_all()")
                await conn.rollback()

    async def run(self, sql: str) -> QueryResult:
        try:
            return await asyncio.wait_for(
                run_on(self._engine, lambda pool: self._work(pool, sql)),
                self._timeout_ms / 1000 + _CLIENT_GRACE_S,
            )
        except DBAPIError as e:
            detail = _db_message(e)
            if detail is None:
                raise
            raise SqlRefused(detail) from e
        except Exception as e:
            if getattr(e, "sqlstate", None) is not None:  # asyncpg error from the raw connection
                raise SqlRefused(str(e).strip().splitlines()[0]) from e
            raise


def _one_statement(sql: str) -> str:
    s = sql.strip()
    if s.endswith(";"):
        s = s[:-1].rstrip()
    if not s:
        raise SqlRefused("empty statement")
    if ";" in s:
        raise SqlRefused("one statement only (remove everything after the first ';')")
    return s


MAX_CELL_CHARS = 2_000
MAX_COLUMN_CHARS = 200
MAX_OUTPUT_CHARS = 50_000


def _cell(v: Any) -> str:
    s = "" if v is None else str(v)
    if len(s) > MAX_CELL_CHARS:
        s = s[:MAX_CELL_CHARS] + "...[cell truncated]"
    return s.replace("|", "\\|").replace("\r\n", " ").replace("\n", " ")


def _markdown(result: QueryResult, max_rows: int) -> str:
    if result.columns is None:
        return "OK (no rows)"
    names = [
        c if len(c) <= MAX_COLUMN_CHARS else c[:MAX_COLUMN_CHARS] + "..." for c in result.columns
    ]
    lines = [
        "| " + " | ".join(_cell(c) for c in names) + " |",
        "| " + " | ".join("---" for _ in names) + " |",
    ]
    size = sum(len(line) + 1 for line in lines)
    if size > MAX_OUTPUT_CHARS:  # the header alone is too wide: show what fits of it
        marker = f"[output truncated at {MAX_OUTPUT_CHARS} characters: too many columns]"
        return lines[0][: MAX_OUTPUT_CHARS - len(marker) - 5] + " ...\n" + marker
    rows = list(result.rows)
    shown = 0
    for row in rows[:max_rows]:
        line = "| " + " | ".join(_cell(v) for v in row) + " |"
        if size + len(line) + 1 > MAX_OUTPUT_CHARS:
            lines.append(f"[output truncated at {MAX_OUTPUT_CHARS} characters after {shown} rows]")
            return "\n".join(lines)
        lines.append(line)
        size += len(line) + 1
        shown += 1
    if not rows:
        lines.append("(0 rows)")
    elif len(rows) > max_rows:
        lines.append(f"[truncated at {max_rows} rows]")
    return "\n".join(lines)


def make_sql_query_tool(runner: SqlRunner, *, max_rows: int) -> BaseTool:
    """The `sql_query` tool over any SqlRunner (fed `max_rows + 1` rows to detect truncation)."""

    async def sql_query(sql: str) -> str:
        """Run one read-only SQL query and return the rows as a Markdown table.

        Use for exact counts, lists and lookups over the connector's tables.
        Do not use to change data (writes are refused) or for free-text search (use kb_search).
        """
        try:
            result = await runner.run(_one_statement(sql))
        except SqlRefused as e:
            return f"ERROR: {e}"
        except TimeoutError:
            return "ERROR: query timed out"
        except Exception as e:  # connection or driver failure: never a traceback or a DSN
            log.warning("sql_query failed: %s", type(e).__name__)
            return f"ERROR: query failed ({type(e).__name__})"
        return _markdown(result, max_rows)

    return StructuredTool.from_function(
        coroutine=sql_query, name="sql_query", args_schema=SqlQueryArgs
    )


@platform_tool(
    owner="platform", version="1.0.0", side_effects="read", classification="confidential"
)
def sql_query(ctx: BuildContext, *, connector: str) -> BaseTool:
    """Read-only SQL over a postgres connector (connect it as `kb_reader`)."""
    spec = _connector(ctx, connector, "sql_query", PostgresSpec)
    engine = get_engine(resolve_secret(spec.dsn, ctx.settings))
    runner = PgSql(
        engine, schemas=spec.schemas, timeout_ms=spec.statement_timeout_ms, fetch=spec.max_rows + 1
    )
    return make_sql_query_tool(runner, max_rows=spec.max_rows)


# --- hooks read by agentkit-config (duck-typed attributes; config never imports us) ----------


class _Unbound:
    async def search(self, query: str, k: int) -> list[Document]:
        raise KbError("not connected")

    async def run(self, sql: str) -> QueryResult:
        raise SqlRefused("not connected")


setattr(kb_search, "__agentkit_validate__", _validator("kb_search", PgVectorSpec))  # noqa: B010
setattr(sql_query, "__agentkit_validate__", _validator("sql_query", PostgresSpec))  # noqa: B010
# Schema-only builds for `agentkit tools snapshot`, which has no connector to resolve.
setattr(  # noqa: B010
    kb_search, "__agentkit_snapshot__", lambda ctx: make_kb_search_tool(_Unbound(), default_k=5)
)
setattr(  # noqa: B010
    sql_query, "__agentkit_snapshot__", lambda ctx: make_sql_query_tool(_Unbound(), max_rows=200)
)
