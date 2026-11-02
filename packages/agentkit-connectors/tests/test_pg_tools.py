"""Real-database tests for kb_search, sql_query and `agentkit-kb setup/ingest`.

`pg` tests use AGENTKIT_TEST_DATABASE_URL (an admin DSN) and skip, naming it, when it is unset.
WARNING: point it only at a throwaway database (a `make stamp TENANT=kbtest` tenant or the
agentkit-dev database): these tests create schema `kb`, reset role `kb_reader`'s password, and
create and drop tables in `kb`. Embeddings are fake and deterministic; no model API is called.
"""

from __future__ import annotations

import hashlib
import math
import os
import secrets
import uuid
from pathlib import Path

import asyncpg
import pytest
from agentkit_connectors import tools
from agentkit_connectors.kb_cli import ingest, main, setup
from agentkit_connectors.spec import PgVectorSpec
from agentkit_core import BuildContext, ModelRegistry, Settings
from langchain_core.embeddings import Embeddings
from sqlalchemy.engine import make_url

pytestmark = pytest.mark.pg


def _admin_url() -> str:
    url = os.environ.get("AGENTKIT_TEST_DATABASE_URL", "")
    if not url:
        pytest.skip("AGENTKIT_TEST_DATABASE_URL is not set")
    return url


class FakeEmbeddings(Embeddings):
    """Bag of words hashed into `dims` buckets, L2-normalised: same words, close vectors."""

    def __init__(self, dims: int) -> None:
        self.dims = dims

    def _vec(self, text: str) -> list[float]:
        v = [0.0] * self.dims
        for w in text.lower().split():
            w = "".join(ch for ch in w if ch.isalnum())
            if w:
                v[int(hashlib.sha256(w.encode()).hexdigest(), 16) % self.dims] += 1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)


@pytest.fixture
def admin_url() -> str:
    return _admin_url()


@pytest.fixture
async def reader(admin_url, monkeypatch) -> str:
    """Run setup (twice: idempotent) and return the kb_reader DSN."""
    pw = secrets.token_urlsafe(24)
    monkeypatch.setenv("KBTEST_READER_PASSWORD", pw)
    await setup(admin_url, pw)
    await setup(admin_url, pw)
    url = make_url(admin_url).set(username="kb_reader", password=pw)
    return url.render_as_string(hide_password=False)


@pytest.fixture
async def kb_table(admin_url, reader):
    """kb.t with 3 rows, created by the admin after setup (default privileges apply)."""
    conn = await asyncpg.connect(admin_url)
    await conn.execute("drop table if exists kb.t")
    await conn.execute("create table kb.t (id int primary key, name text)")
    await conn.execute("insert into kb.t values (1, 'one'), (2, 'two'), (3, 'three')")
    yield conn
    await conn.execute("drop table if exists kb.t")
    await conn.close()


def _lib(root: Path, monkeypatch, **dsns: str) -> None:
    d = root / "connectors"
    d.mkdir(parents=True, exist_ok=True)
    for name, text in (
        (
            "kbsql",
            "kind: postgres\ndsn: env://KBTEST_SQL_URL\nschemas: [kb]\n"
            "statement_timeout_ms: 1000\nmax_rows: 2\n",
        ),
    ):
        (d / f"{name}.yaml").write_text(text)
    monkeypatch.setenv("AGENTKIT_LIBRARY_PATH", str(root))
    for var, value in dsns.items():
        monkeypatch.setenv(var, value)


def _ctx() -> BuildContext:
    s = Settings(_env_file=None, fireworks_api_key="fake")  # type: ignore[arg-type]
    return BuildContext(s, ModelRegistry.default().resolve(), "t")


async def test_setup_is_idempotent_and_role_is_read_only(admin_url, reader):
    conn = await asyncpg.connect(admin_url)
    try:
        role = await conn.fetchrow(
            "select rolsuper, rolcanlogin, rolcreaterole, rolcreatedb, rolbypassrls,"
            " rolconfig from pg_roles where rolname = 'kb_reader'"
        )
        assert role["rolcanlogin"] and not role["rolsuper"]
        assert not (role["rolcreaterole"] or role["rolcreatedb"] or role["rolbypassrls"])
        assert "default_transaction_read_only=on" in role["rolconfig"]
        assert await conn.fetchval("select has_schema_privilege('kb_reader', 'kb', 'USAGE')")
        assert not await conn.fetchval("select has_schema_privilege('kb_reader', 'kb', 'CREATE')")
        assert not await conn.fetchval(
            "select has_schema_privilege('kb_reader', 'public', 'CREATE')"
        )
    finally:
        await conn.close()
    r = await asyncpg.connect(reader)  # the password set by setup works
    try:
        assert await r.fetchval("select current_user") == "kb_reader"
    finally:
        await r.close()


async def test_sql_query_reads_and_truncates(tmp_path, monkeypatch, reader, kb_table):
    _lib(tmp_path, monkeypatch, KBTEST_SQL_URL=reader)
    t = tools.sql_query(_ctx(), connector="kbsql")
    out = await t.ainvoke({"sql": "select id, name from t order by id"})  # search_path = kb
    assert out == "| id | name |\n| --- | --- |\n| 1 | one |\n| 2 | two |\n[truncated at 2 rows]"
    assert await t.ainvoke({"sql": "select current_user as u;"}) == "| u |\n| --- |\n| kb_reader |"


HOSTILE = [
    "insert into kb.t values (99, 'x')",
    "with d as (delete from kb.t returning *) select * from d",
    "update kb.t set name = 'pwned'",
    "set role agentkit",
    "set session authorization agentkit",
    "select pg_sleep(10)",
    "select 1; delete from kb.t",
    "commit",
    "create table kb.evil (id int)",
    "select * from public.agentkit_usage",
    "select * from agentkit_usage",
]


@pytest.mark.parametrize("sql", HOSTILE)
async def test_hostile_sql_returns_error_and_writes_nothing(
    tmp_path, monkeypatch, reader, kb_table, sql
):
    _lib(tmp_path, monkeypatch, KBTEST_SQL_URL=reader)
    t = tools.sql_query(_ctx(), connector="kbsql")
    before = await kb_table.fetch("select id, name from kb.t order by id")
    out = await t.ainvoke({"sql": sql})
    assert out.startswith("ERROR: "), out
    assert await kb_table.fetch("select id, name from kb.t order by id") == before
    assert await kb_table.fetchval("select to_regclass('kb.evil')") is None
    # The pooled connection is clean afterwards: the next call still runs read-only as kb_reader.
    assert (await t.ainvoke({"sql": "select current_setting('transaction_read_only') as ro"})) == (
        "| ro |\n| --- |\n| on |"
    )


async def test_role_is_the_wall_even_in_a_read_write_transaction(reader, kb_table):
    """Layer 1 alone: as kb_reader, with READ ONLY explicitly turned off, writes still fail."""
    import asyncpg.exceptions as pgx

    r = await asyncpg.connect(reader)
    try:
        for sql in (
            "insert into kb.t values (99, 'x')",
            "delete from kb.t",
            "create table kb.evil (id int)",
            "create table public.evil (id int)",
            "select * from public.agentkit_usage",
        ):
            await r.execute("begin read write")  # overrides the role's read-only default
            try:
                with pytest.raises(pgx.InsufficientPrivilegeError):
                    await r.execute(sql)
            finally:
                await r.execute("rollback")
    finally:
        await r.close()
    assert await kb_table.fetchval("select count(*) from kb.t") == 3


async def test_session_settings_do_not_leak_between_calls(tmp_path, monkeypatch, reader, kb_table):
    _lib(tmp_path, monkeypatch, KBTEST_SQL_URL=reader)
    t = tools.sql_query(_ctx(), connector="kbsql")
    for sql in ("set statement_timeout = 0", "set search_path = public", "reset role"):
        assert await t.ainvoke({"sql": sql}) == "OK (no rows)"
    out = await t.ainvoke({"sql": "select current_setting('statement_timeout') as s"})
    assert out == "| s |\n| --- |\n| 1s |"
    assert await t.ainvoke({"sql": "show search_path"}) == "| search_path |\n| --- |\n| kb |"
    assert (await t.ainvoke({"sql": "select pg_sleep(10)"})).startswith("ERROR: canceling")


async def test_usage_table_exists_so_the_public_check_is_meaningful(admin_url, reader):
    conn = await asyncpg.connect(admin_url)
    try:
        assert await conn.fetchval("select to_regclass('public.agentkit_usage')") is not None
        assert not await conn.fetchval(
            "select has_table_privilege('kb_reader', 'public.agentkit_usage', 'SELECT')"
        )
    finally:
        await conn.close()


@pytest.fixture
async def collection(admin_url):
    name = f"kbtest_{uuid.uuid4().hex[:8]}"
    yield name
    conn = await asyncpg.connect(admin_url)
    await conn.execute(f'drop table if exists kb."{name}"')
    await conn.close()


def _docs(root: Path) -> list[Path]:
    texts = {
        "apples.md": "# Apples\n\nApples grow in an orchard. Red apples and green apples.\n",
        "boats.md": "# Boats\n\nBoats sail on the sea with a mast and a keel.\n",
        "docs/clouds.md": "# Clouds\n\nClouds float in the sky and bring rain.\n",
    }
    paths = []
    for rel, text in texts.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        paths.append(p)
    return paths


async def _count(admin_url: str, collection: str) -> int:
    conn = await asyncpg.connect(admin_url)
    try:
        return int(await conn.fetchval(f'select count(*) from kb."{collection}"'))
    finally:
        await conn.close()


async def test_ingest_then_kb_search_and_dimension_mismatch(
    tmp_path, monkeypatch, admin_url, reader, collection
):
    spec = PgVectorSpec(
        kind="pgvector", dsn="env://KBTEST_KB_URL", collection=collection, embeddings="x"
    )
    monkeypatch.setenv("KBTEST_KB_URL", admin_url)
    paths = _docs(tmp_path)
    base = "https://example.test/blob/main"
    emb = FakeEmbeddings(768)
    n = await ingest(spec, paths, source_base=base, root=tmp_path, embeddings=emb, dims=768)
    assert n == 3
    await ingest(spec, paths, source_base=base, root=tmp_path, embeddings=emb, dims=768)
    assert await _count(admin_url, collection) == 3  # re-ingest upserts, no duplicates

    store = tools.PgKb(tools.get_engine(admin_url), FakeEmbeddings(768), collection)
    t = tools.make_kb_search_tool(store, default_k=3)
    out = await t.ainvoke({"query": "red apples orchard"})
    assert out.startswith(f"[1] Apples\n{base}/apples.md\n# Apples"), out
    out = await t.ainvoke({"query": "clouds rain sky", "k": 1})
    assert out.startswith(f"[1] Clouds\n{base}/docs/clouds.md\n") and "[2]" not in out

    wrong = tools.make_kb_search_tool(
        tools.PgKb(tools.get_engine(admin_url), FakeEmbeddings(1536), collection), default_k=3
    )
    out = await wrong.ainvoke({"query": "apples"})
    assert out.startswith("ERROR: embedding dimension mismatch"), out
    assert "768" in out and "1536" in out

    missing = tools.make_kb_search_tool(
        tools.PgKb(tools.get_engine(admin_url), FakeEmbeddings(768), "no_such_table"), default_k=3
    )
    assert (await missing.ainvoke({"query": "x"})).startswith("ERROR: knowledge base table")

    # kb_search works read-only: the same search through the kb_reader DSN.
    as_reader = tools.make_kb_search_tool(
        tools.PgKb(tools.get_engine(reader), FakeEmbeddings(768), collection), default_k=3
    )
    out = await as_reader.ainvoke({"query": "red apples orchard"})
    assert out.startswith(f"[1] Apples\n{base}/apples.md\n"), out

    # kb_reader got SELECT on the new table through setup's default privileges.
    r = await asyncpg.connect(reader)
    try:
        assert await r.fetchval(f'select count(*) from kb."{collection}"') == 3
    finally:
        await r.close()


def test_kb_cli_setup_twice_never_prints_the_password(tmp_path, monkeypatch, capsys, admin_url):
    _lib(tmp_path, monkeypatch, KBTEST_ADMIN_URL=admin_url)
    (tmp_path / "connectors" / "admin.yaml").write_text(
        "kind: postgres\ndsn: env://KBTEST_ADMIN_URL\nschemas: [kb]\n"
    )
    pw = secrets.token_urlsafe(24)
    monkeypatch.setenv("KBTEST_READER_PASSWORD", pw)
    args = ["setup", "--connector", "admin", "--reader-password-env", "KBTEST_READER_PASSWORD"]
    assert main(args) == 0
    assert main(args) == 0
    out = capsys.readouterr()
    assert pw not in out.out + out.err
    assert "kb_reader" in out.out


async def test_sql_query_refuses_a_privileged_login(tmp_path, monkeypatch, admin_url, reader):
    """Review fix: an admin DSN could COPY ... TO PROGRAM / pg_read_file inside READ ONLY."""
    _lib(tmp_path, monkeypatch, KBTEST_SQL_URL=admin_url)
    t = tools.sql_query(_ctx(), connector="kbsql")
    for sql in ("select 1 as x", "select pg_read_file('/etc/hostname')"):
        assert await t.ainvoke({"sql": sql}) == f"ERROR: {tools.NOT_READ_ONLY}"


async def test_advisory_locks_never_survive_a_call(tmp_path, monkeypatch, admin_url, reader):
    _lib(tmp_path, monkeypatch, KBTEST_SQL_URL=reader)
    t = tools.sql_query(_ctx(), connector="kbsql")
    assert (await t.ainvoke({"sql": "select pg_advisory_lock(424242)"})).startswith("| ")
    other = await asyncpg.connect(admin_url)
    try:  # try_lock, so a leaked lock fails the test instead of hanging it
        assert await other.fetchval("select pg_try_advisory_lock(424242)") is True
        await other.fetchval("select pg_advisory_unlock(424242)")
    finally:
        await other.close()


ESCALATE = (
    "select set_config('role', 'agentkit', true),"
    " query_to_xml('select pg_read_file(''/etc/passwd'')', true, true, '')"
)


@pytest.fixture
async def member_logins(admin_url):
    """Logins that are not superuser/BYPASSRLS themselves but are members of such roles."""
    pw = secrets.token_urlsafe(16)
    conn = await asyncpg.connect(admin_url)
    names = ("kbtest_su_member", "kbtest_bypass_member", "kbtest_bypass")
    try:
        for n in names:
            await conn.execute(f"drop role if exists {n}")
        await conn.execute("create role kbtest_bypass nologin bypassrls")
        su_role = await conn.fetchval("select current_user")  # the stamp's superuser
        for n, parent in (("kbtest_su_member", su_role), ("kbtest_bypass_member", "kbtest_bypass")):
            await conn.execute(f"create role {n} login password {_lit(pw)}")
            await conn.execute(f'grant "{parent}" to {n}')
            await conn.execute(f"grant usage on schema kb to {n}")
        yield {
            n: make_url(admin_url)
            .set(username=n, password=pw)
            .render_as_string(hide_password=False)
            for n in ("kbtest_su_member", "kbtest_bypass_member")
        }
    finally:
        await conn.execute("revoke usage on schema kb from kbtest_su_member, kbtest_bypass_member")
        for n in names:
            await conn.execute(f"drop role if exists {n}")
        await conn.close()


def _lit(v: str) -> str:
    return "'" + v.replace("'", "''") + "'"


async def test_members_of_privileged_roles_are_refused(
    tmp_path, monkeypatch, reader, member_logins
):
    for login, url in member_logins.items():
        _lib(tmp_path, monkeypatch, KBTEST_SQL_URL=url)
        t = tools.sql_query(_ctx(), connector="kbsql")
        for sql in ("select 1 as x", ESCALATE):
            assert await t.ainvoke({"sql": sql}) == f"ERROR: {tools.NOT_READ_ONLY}", login


async def test_kb_reader_cannot_escalate_through_set_config(tmp_path, monkeypatch, reader):
    _lib(tmp_path, monkeypatch, KBTEST_SQL_URL=reader)
    t = tools.sql_query(_ctx(), connector="kbsql")
    out = await t.ainvoke({"sql": ESCALATE})
    assert out.startswith("ERROR: ") and "root:" not in out, out


# `SET ROLE NONE` falls back to session_user: the login, not the startup role.
ESCALATE_TO_LOGIN = (
    "select set_config('role', 'none', true),"
    " query_to_xml('select pg_read_file(''/etc/passwd'')', true, true, '')"
)


async def test_set_role_to_an_existing_superuser_is_denied(tmp_path, monkeypatch, reader, kb_table):
    """Discriminates: the target exists and is a superuser, kb_reader just isn't a member."""
    su = await kb_table.fetchval("select current_user")  # the stamp's superuser
    assert await kb_table.fetchval("select rolsuper from pg_roles where rolname = $1", su)
    assert not await kb_table.fetchval("select pg_has_role('kb_reader', $1, 'member')", su)
    _lib(tmp_path, monkeypatch, KBTEST_SQL_URL=reader)
    t = tools.sql_query(_ctx(), connector="kbsql")
    for sql in (
        f'set role "{su}"',
        f'set session authorization "{su}"',
        f"select set_config('role', {_lit(su)}, true) as r",
    ):
        out = await t.ainvoke({"sql": sql})
        assert out.startswith("ERROR: permission denied to set"), (sql, out)


async def _whoami(pool) -> tuple[str, str]:
    from sqlalchemy import text

    async with pool.connect() as conn:
        row = (await conn.execute(text("select session_user, current_user"))).one()
    return row[0], row[1]


async def test_admin_login_with_a_startup_role_is_refused(admin_url, reader):
    """Review I1: an admin login whose startup `role` is kb_reader passes a current_user-only
    check, then `set_config('role', 'none', ...)` is back to the admin inside one statement."""
    from agentkit_connectors.engines import _async_url
    from langchain_postgres import PGEngine
    from sqlalchemy.ext.asyncio import create_async_engine

    pool = create_async_engine(
        _async_url(admin_url), connect_args={"server_settings": {"role": "kb_reader"}}
    )
    try:
        session, current = await _whoami(pool)
        assert current == "kb_reader" and session != "kb_reader"  # the startup role took
        engine = PGEngine.from_engine(pool)
        runner = tools.PgSql(engine, schemas=["kb"], timeout_ms=1000, fetch=3)
        t = tools.make_sql_query_tool(runner, max_rows=2)
        for sql in ("select 1 as x", ESCALATE_TO_LOGIN):
            assert await t.ainvoke({"sql": sql}) == f"ERROR: {tools.NOT_READ_ONLY}"
    finally:
        await pool.dispose()


@pytest.fixture
async def su_login_defaulting_to_reader(admin_url, reader):
    """A superuser login with `ALTER ROLE ... SET role = kb_reader`: the same shape, via a DSN."""
    pw = secrets.token_urlsafe(16)
    conn = await asyncpg.connect(admin_url)
    try:
        await conn.execute("drop role if exists kbtest_su_login")
        await conn.execute(f"create role kbtest_su_login login superuser password {_lit(pw)}")
        await conn.execute("alter role kbtest_su_login set role = 'kb_reader'")
        yield (
            make_url(admin_url)
            .set(username="kbtest_su_login", password=pw)
            .render_as_string(hide_password=False)
        )
    finally:
        await conn.execute("drop role if exists kbtest_su_login")
        await conn.close()


async def test_superuser_login_with_a_default_role_is_refused(
    tmp_path, monkeypatch, su_login_defaulting_to_reader
):
    url = su_login_defaulting_to_reader
    r = await asyncpg.connect(url)
    try:
        assert tuple(await r.fetchrow("select session_user, current_user")) == (
            "kbtest_su_login",
            "kb_reader",
        )
    finally:
        await r.close()
    _lib(tmp_path, monkeypatch, KBTEST_SQL_URL=url)
    t = tools.sql_query(_ctx(), connector="kbsql")
    for sql in ("select 1 as x", ESCALATE_TO_LOGIN):
        assert await t.ainvoke({"sql": sql}) == f"ERROR: {tools.NOT_READ_ONLY}"
