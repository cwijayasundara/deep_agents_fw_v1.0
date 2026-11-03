"""`agentkit-kb`: set up the knowledge-base schema and read-only role, and ingest Markdown.

    agentkit-kb setup --connector kb-docs --reader-password-env KB_READER_PASSWORD
    agentkit-kb ingest --connector kb-docs README.md docs/*.md --source-base <url> [--root DIR]

`setup` connects with the connector's (admin) DSN. The kb_reader password is read from the named
env var, hashed client-side to a SCRAM-SHA-256 verifier, and never printed or logged; only the
verifier reaches the server.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import hmac
import os
import re
import sys
import uuid
from collections.abc import Sequence
from functools import partial
from pathlib import Path

import asyncpg  # type: ignore[import-untyped]  # ships no type information
from agentkit_core import ConfigError, Settings, resolve_secret
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_postgres import PGVectorStore
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from .embeddings import embedding_dimensions, get_embeddings
from .engines import KB_SCHEMA, get_engine, run_on
from .spec import PgVectorSpec, library_roots, load_connector
from .tools import qualified_table, table_dims

ROLE = "kb_reader"
CHUNK_CHARS = 1500

_HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*#*\s*$")


# --- setup ----------------------------------------------------------------------------------


def scram_verifier(password: str, *, salt: bytes | None = None, iterations: int = 4096) -> str:
    """The SCRAM-SHA-256 verifier Postgres stores for `password` (as psql's \\password sends)."""
    if not password or not password.isascii():
        raise ConfigError("the kb_reader password must be non-empty ASCII")
    salt = salt or os.urandom(16)
    salted = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    stored = hashlib.sha256(hmac.new(salted, b"Client Key", "sha256").digest()).digest()
    server = hmac.new(salted, b"Server Key", "sha256").digest()

    def b64(b: bytes) -> str:
        return base64.b64encode(b).decode()

    return f"SCRAM-SHA-256${iterations}:{b64(salt)}${b64(stored)}:{b64(server)}"


def _plain_dsn(dsn: str) -> str:
    return dsn.replace("postgresql+asyncpg://", "postgresql://", 1)


def _literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


async def setup(dsn: str, password: str) -> None:
    """Create schema `kb` and role `kb_reader` (LOGIN, read-only, SELECT on `kb` only).

    Idempotent: a second run resets the password and re-applies the grants."""
    verifier = scram_verifier(password)
    conn = await asyncpg.connect(_plain_dsn(dsn))
    try:
        async with conn.transaction():
            await conn.execute(f"CREATE SCHEMA IF NOT EXISTS {KB_SCHEMA}")
            exists = await conn.fetchval("select 1 from pg_roles where rolname = $1", ROLE)
            verb = "ALTER" if exists else "CREATE"
            await conn.execute(
                f"{verb} ROLE {ROLE} WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE"
                f" NOREPLICATION NOBYPASSRLS PASSWORD {_literal(verifier)}"
            )
            await conn.execute(f"ALTER ROLE {ROLE} SET default_transaction_read_only = on")
            await conn.execute(f"REVOKE CREATE ON SCHEMA {KB_SCHEMA} FROM PUBLIC")
            await conn.execute(f"GRANT USAGE ON SCHEMA {KB_SCHEMA} TO {ROLE}")
            await conn.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA {KB_SCHEMA} TO {ROLE}")
            await conn.execute(
                f"ALTER DEFAULT PRIVILEGES IN SCHEMA {KB_SCHEMA} GRANT SELECT ON TABLES TO {ROLE}"
            )
    finally:
        await conn.close()


# --- ingest ---------------------------------------------------------------------------------


def _split(body: str, size: int) -> list[str]:
    """Pack paragraphs into chunks of at most `size` characters (long ones cut at a space)."""
    pieces: list[str] = []
    for para in re.split(r"\n\s*\n", body):
        para = para.strip()
        while len(para) > size:
            cut = para.rfind(" ", 0, size + 1)
            cut = cut if cut > 0 else size
            pieces.append(para[:cut].rstrip())
            para = para[cut:].lstrip()
        if para:
            pieces.append(para)
    chunks: list[str] = []
    cur = ""
    for p in pieces:
        if cur and len(cur) + 2 + len(p) > size:
            chunks.append(cur)
            cur = p
        else:
            cur = f"{cur}\n\n{p}" if cur else p
    if cur:
        chunks.append(cur)
    return chunks


def chunk_markdown(
    text: str, *, default_title: str, size: int = CHUNK_CHARS
) -> list[tuple[str, str]]:
    """`(title, chunk)` pairs: split on headings (not inside code fences), then by size."""
    sections: list[tuple[str, list[str]]] = []
    title, fence = default_title, None
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            marker = stripped[:3]
            fence = None if fence == marker else (fence or marker)
        elif fence is None and (m := _HEADING.match(line)):
            sections.append((title, lines))
            title, lines = m.group(1) or default_title, []
        lines.append(line)
    sections.append((title, lines))
    out: list[tuple[str, str]] = []
    for t, ls in sections:
        body = "\n".join(ls).strip()
        if body:
            out.extend((t, c) for c in _split(body, size))
    return out


async def _prepare(pool: AsyncEngine, table: str) -> tuple[bool, int | None]:
    async with pool.begin() as conn:
        await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {KB_SCHEMA}"))
    return await table_dims(pool, table)


async def _delete_source(pool: AsyncEngine, *, table: str, url: str) -> None:
    sql = text(f"delete from {qualified_table(table)} where langchain_metadata->>'source_url' = :u")
    async with pool.begin() as conn:
        await conn.execute(sql, {"u": url})


def _read_sources(
    paths: Sequence[Path], *, source_base: str, root: Path
) -> list[tuple[str, str, str]]:
    """`(source_url, default title, text)` per file; a path outside `root` is a ConfigError."""
    root = root.resolve()
    out: list[tuple[str, str, str]] = []
    for path in paths:
        try:
            rel = path.resolve().relative_to(root).as_posix()
        except ValueError:
            raise ConfigError(f"{path} is outside the repo root {root}") from None
        url = f"{source_base.rstrip('/')}/{rel}"
        out.append((url, path.name, path.read_text(encoding="utf-8")))
    return out


async def ingest(
    spec: PgVectorSpec,
    paths: Sequence[Path],
    *,
    source_base: str,
    root: Path,
    embeddings: Embeddings,
    dims: int,
) -> int:
    """Upsert each file's chunks with `{title, source_url}`; returns the chunk count.

    A file's previous chunks are replaced, so re-ingesting a shrunk file leaves no stale rows."""
    sources = _read_sources(paths, source_base=source_base, root=root)
    engine = get_engine(resolve_secret(spec.dsn, Settings()))
    table = spec.collection
    present, have = await run_on(engine, lambda pool: _prepare(pool, table))
    if not present:
        await engine.ainit_vectorstore_table(table, dims, schema_name=KB_SCHEMA)
    elif have is not None and have != dims:
        raise ConfigError(
            f"embedding dimension mismatch: {KB_SCHEMA}.{table} holds {have}-dim vectors,"
            f" the embeddings give {dims}; drop the table or use the matching entry"
        )
    store = await PGVectorStore.create(engine, embeddings, table_name=table, schema_name=KB_SCHEMA)
    total = 0
    for url, title, body in sources:
        chunks = chunk_markdown(body, default_title=title)
        docs = [Document(c, metadata={"title": t, "source_url": url}) for t, c in chunks]
        ids = [str(uuid.uuid5(uuid.NAMESPACE_URL, f"{url}#{i}")) for i in range(len(docs))]
        await run_on(engine, partial(_delete_source, table=table, url=url))
        if docs:
            await store.aadd_documents(docs, ids=ids)
        total += len(docs)
    return total


# --- CLI ------------------------------------------------------------------------------------


def _repo_root(start: Path) -> Path:
    here = start.resolve()
    for ancestor in (here, *here.parents):
        if (ancestor / ".git").exists():
            return ancestor
    return here


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="agentkit-kb", description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("setup", help="create schema kb and the read-only role kb_reader")
    s.add_argument("--connector", required=True, help="connector whose DSN is an admin login")
    s.add_argument(
        "--reader-password-env", required=True, help="env var holding kb_reader's password"
    )
    i = sub.add_parser("ingest", help="chunk Markdown files and upsert them into the KB")
    i.add_argument("--connector", required=True, help="a pgvector connector")
    i.add_argument("paths", nargs="+", type=Path)
    i.add_argument("--source-base", required=True, help="URL prefix for each chunk's source_url")
    i.add_argument("--root", type=Path, help="repo root paths are made relative to (default: git)")
    return p


def _run(args: argparse.Namespace) -> str:
    spec = load_connector(args.connector, library_roots())
    if args.cmd == "setup":
        password = os.environ.get(args.reader_password_env)
        if not password:
            raise ConfigError(f"{args.reader_password_env} is not set (the kb_reader password)")
        asyncio.run(setup(resolve_secret(spec.dsn, Settings()), password))
        return f"setup: schema {KB_SCHEMA} and role {ROLE} ready (read-only, SELECT on {KB_SCHEMA})"
    if not isinstance(spec, PgVectorSpec):
        raise ConfigError(f"connector {args.connector!r} is a {spec.kind} connector; need pgvector")
    emb = get_embeddings(spec.embeddings, Settings())
    root = args.root or _repo_root(Path.cwd())
    n = asyncio.run(
        ingest(
            spec,
            args.paths,
            source_base=args.source_base,
            root=root,
            embeddings=emb,
            dims=embedding_dimensions(spec.embeddings),
        )
    )
    return f"ingest: {n} chunk(s) from {len(args.paths)} file(s) into {KB_SCHEMA}.{spec.collection}"


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        print(_run(args))
    except ConfigError as e:
        print(f"agentkit-kb: {e}", file=sys.stderr)
        return 2
    except asyncpg.PostgresError as e:  # the server's message; never the DSN or the password
        print(f"agentkit-kb: {args.cmd} failed: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(
            f"agentkit-kb: {args.cmd} failed: cannot reach the database ({type(e).__name__})",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
