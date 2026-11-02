"""Offline tests for the curated connector tools (no database, no model calls)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from agentkit_config import CodePools, Library
from agentkit_config.registry import Registry
from agentkit_config.spec import parse_agent
from agentkit_config.validate import validate_agent
from agentkit_connectors import tools
from agentkit_connectors.kb_cli import chunk_markdown, scram_verifier
from agentkit_connectors.tools import (
    KbError,
    QueryResult,
    kb_search,
    make_kb_search_tool,
    make_sql_query_tool,
    sql_query,
)
from agentkit_core import BuildContext, ConfigError, ModelRegistry, Settings
from agentkit_tools import check_tool_contract, tool_meta
from langchain_core.documents import Document


def _library(root: Path) -> Path:
    d = root / "connectors"
    d.mkdir(parents=True, exist_ok=True)
    (d / "docs.yaml").write_text(
        "kind: pgvector\ndsn: env://T_KB_URL\ncollection: kb_docs\nembeddings: fireworks-nomic\n"
    )
    (d / "sql.yaml").write_text(
        "kind: postgres\ndsn: env://T_SQL_URL\nschemas: [kb]\nmax_rows: 2\n"
    )
    return root


def _ctx() -> BuildContext:
    s = Settings(_env_file=None, fireworks_api_key="fake")  # type: ignore[arg-type]
    return BuildContext(s, ModelRegistry.default().resolve(), "t")


def _agent(root: Path, tools_yaml: str) -> Path:
    (root / "prompts").mkdir(exist_ok=True)
    (root / "prompts" / "main.md").write_text("I am {{agent_name}}.")
    p = root / "agent.yaml"
    p.write_text(
        "apiVersion: agentkit/v1\nkind: Agent\nname: demo\nmodel: anthropic\nprompt: main\n"
        f"tools: {tools_yaml}\noutput: null\n"
    )
    return p


def _validate(root: Path, tools_yaml: str) -> list[Any]:
    pools = CodePools(
        Registry("tool", {"kb_search": kb_search, "sql_query": sql_query}),
        Registry("middleware", {}),
        Registry("node", {}),
        Registry("schema", {}),
    )
    path = _agent(root, tools_yaml)
    errs = validate_agent(
        parse_agent(path), Library.for_file(path, pools), ModelRegistry.default(), file=str(path)
    )
    return [e for e in errs if e.severity == "error"]


def test_validate_checks_connector_names_and_kinds(tmp_path, monkeypatch):
    monkeypatch.delenv("AGENTKIT_LIBRARY_PATH", raising=False)
    root = _library(tmp_path)
    ok = "[{kb_search: {connector: docs}}, {sql_query: {connector: sql}}]"
    assert _validate(root, ok) == []
    bad = "[{kb_search: {connector: nope}}, {sql_query: {connector: docs}}]"
    errs = _validate(root, bad)
    assert [e.path for e in errs] == ["tools[0]", "tools[1]"]
    assert "unknown connector 'nope'; known: docs, sql" in errs[0].message
    assert "connector 'docs' is a pgvector connector; sql_query needs postgres" in errs[1].message


def test_factories_resolve_connector_through_library_roots(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTKIT_LIBRARY_PATH", str(_library(tmp_path / "lib")))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("T_KB_URL", "postgresql://u:pw@127.0.0.1:1/db")
    monkeypatch.setenv("T_SQL_URL", "postgresql://u:pw@127.0.0.1:1/db")
    # Building connects to nothing: engines are lazy, the vector store is created on first use.
    assert kb_search(_ctx(), connector="docs").name == "kb_search"
    assert sql_query(_ctx(), connector="sql").name == "sql_query"
    with pytest.raises(ConfigError, match="unknown connector 'nope'"):
        kb_search(_ctx(), connector="nope")
    with pytest.raises(ConfigError, match="needs postgres"):
        sql_query(_ctx(), connector="docs")
    monkeypatch.delenv("T_SQL_URL")
    with pytest.raises(ConfigError, match=r"env://T_SQL_URL is not set"):
        sql_query(_ctx(), connector="sql")


class _FakeKb:
    def __init__(self, docs: list[Document] | None = None, error: str | None = None) -> None:
        self.docs, self.error, self.calls = docs or [], error, []

    async def search(self, query: str, k: int) -> list[Document]:
        self.calls.append((query, k))
        if self.error:
            raise KbError(self.error)
        return self.docs[:k]


async def test_kb_search_renders_hits_and_errors():
    docs = [
        Document("chunk one", metadata={"title": "Intro", "source_url": "https://x/a.md"}),
        Document("chunk two", metadata={"title": "Setup", "source_url": "https://x/b.md"}),
    ]
    kb = _FakeKb(docs)
    t = make_kb_search_tool(kb, default_k=3)
    out = await t.ainvoke({"query": "what is it"})
    assert out == "[1] Intro\nhttps://x/a.md\nchunk one\n\n[2] Setup\nhttps://x/b.md\nchunk two"
    assert kb.calls == [("what is it", 3)]
    await t.ainvoke({"query": "q", "k": 1})
    assert kb.calls[-1] == ("q", 1)
    assert await make_kb_search_tool(_FakeKb(), default_k=5).ainvoke({"query": "q"}) == (
        "No results."
    )
    bad = make_kb_search_tool(_FakeKb(error="embedding dimension mismatch: x"), default_k=5)
    assert await bad.ainvoke({"query": "q"}) == "ERROR: embedding dimension mismatch: x"


class _FakeSql:
    def __init__(self, result: QueryResult | None = None) -> None:
        self.result, self.seen = result, []

    async def run(self, sql: str) -> QueryResult:
        self.seen.append(sql)
        assert self.result is not None, "the database must not be touched"
        return self.result


@pytest.mark.parametrize(
    ("sql", "error"),
    [
        ("select 1; select 2", "ERROR: one statement only"),
        ("select 1;select 2;", "ERROR: one statement only"),
        ("select 1;;", "ERROR: one statement only"),
        ("select ';' as x", "ERROR: one statement only"),  # conservative: any inner ';'
        ("   ", "ERROR: empty statement"),
        (";", "ERROR: empty statement"),
    ],
)
async def test_sql_query_refuses_more_than_one_statement_before_the_db(sql, error):
    runner = _FakeSql()
    out = await make_sql_query_tool(runner, max_rows=2).ainvoke({"sql": sql})
    assert out.startswith(error)
    assert runner.seen == []


async def test_sql_query_one_statement_and_markdown_table():
    rows = [(1, "a|b"), (2, "line\nbreak"), (3, None)]
    runner = _FakeSql(QueryResult(columns=["id", "name"], rows=rows))
    t = make_sql_query_tool(runner, max_rows=2)
    out = await t.ainvoke({"sql": "  select id, name from t;  "})
    assert runner.seen == ["select id, name from t"]
    assert out == (
        "| id | name |\n| --- | --- |\n| 1 | a\\|b |\n| 2 | line break |\n[truncated at 2 rows]"
    )
    runner.result = QueryResult(columns=["n"], rows=[(None,)])
    assert await t.ainvoke({"sql": "select null as n"}) == "| n |\n| --- |\n|  |"
    runner.result = QueryResult(columns=["n"], rows=[])
    assert await t.ainvoke({"sql": "select 1 where false"}) == "| n |\n| --- |\n(0 rows)"
    runner.result = QueryResult(columns=None, rows=[])
    assert await t.ainvoke({"sql": "set x = 1"}) == "OK (no rows)"


def test_tools_meet_the_contract_and_metadata():
    for factory, cls in ((kb_search, "internal"), (sql_query, "confidential")):
        meta = tool_meta(factory)
        assert meta is not None
        assert (meta.version, meta.side_effects, meta.classification) == ("1.0.0", "read", cls)
        built = factory.__agentkit_snapshot__(_ctx())  # type: ignore[attr-defined]
        assert check_tool_contract(built) == []
    kb_props = make_kb_search_tool(_FakeKb(), default_k=5).tool_call_schema.model_json_schema()
    assert set(kb_props["properties"]) == {"query", "k"}
    sql_props = make_sql_query_tool(_FakeSql(), max_rows=1).tool_call_schema.model_json_schema()
    assert set(sql_props["properties"]) == {"sql"}


def test_chunk_markdown_splits_on_headings_and_size():
    text = (
        "Preamble line.\n\n# Title\n\nIntro para.\n\n```bash\n# not a heading\n```\n\n"
        "## Part two\n\n" + ("word " * 400 + "\n\n") * 2
    )
    chunks = chunk_markdown(text, default_title="doc.md", size=1500)
    assert chunks[0] == ("doc.md", "Preamble line.")
    assert chunks[1][0] == "Title" and "# not a heading" in chunks[1][1]
    rest = chunks[2:]
    assert {t for t, _ in rest} == {"Part two"} and len(rest) >= 2
    assert all(len(c) <= 1500 for _, c in chunks)


def test_scram_verifier_shape_and_no_plaintext():
    v = scram_verifier("s3cret-pw", salt=b"0123456789abcdef", iterations=4096)
    assert v.startswith("SCRAM-SHA-256$4096:") and "s3cret-pw" not in v
    with pytest.raises(ConfigError):
        scram_verifier("pässword")


def test_kb_cli_setup_needs_the_password_env(monkeypatch, capsys, tmp_path):
    from agentkit_connectors.kb_cli import main

    monkeypatch.setenv("AGENTKIT_LIBRARY_PATH", str(_library(tmp_path)))
    monkeypatch.setenv("T_KB_URL", "postgresql://u:topsecret@127.0.0.1:1/db")
    monkeypatch.delenv("KB_READER_PW_UNSET", raising=False)
    rc = main(["setup", "--connector", "docs", "--reader-password-env", "KB_READER_PW_UNSET"])
    err = capsys.readouterr().err
    assert rc == 2 and "KB_READER_PW_UNSET" in err and "topsecret" not in err
    assert tools.KB_SCHEMA == "kb"
