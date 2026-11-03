import logging

import pytest
from agentkit_connectors import (
    PgVectorSpec,
    PostgresSpec,
    embedding_dimensions,
    engines,
    get_embeddings,
    get_engine,
    get_vectorstore,
    load_connector,
)
from agentkit_core import ConfigError, Settings, resolve_secret


def _write(root, name, text):
    d = root / "connectors"
    d.mkdir(exist_ok=True)
    (d / f"{name}.yaml").write_text(text)


def test_specs_parse_both_kinds(tmp_path):
    _write(
        tmp_path,
        "kb",
        "kind: pgvector\ndsn: env://KB\ncollection: docs\nembeddings: fireworks-nomic\n",
    )
    _write(tmp_path, "sql", "kind: postgres\ndsn: env://SQL\nschemas: [public]\n")
    kb, sql = load_connector("kb", [tmp_path]), load_connector("sql", [tmp_path])
    assert isinstance(kb, PgVectorSpec) and kb.collection == "docs"
    assert (
        isinstance(sql, PostgresSpec) and sql.statement_timeout_ms == 5000 and sql.max_rows == 200
    )


def test_bad_specs_fail(tmp_path):
    _write(tmp_path, "a", "kind: mongo\ndsn: env://X\n")
    _write(tmp_path, "b", "kind: postgres\ndsn: env://X\nschemas: []\n")
    for name in ("a", "b"):
        with pytest.raises(ConfigError):
            load_connector(name, [tmp_path])


def test_unknown_name_lists_known_and_first_root_wins(tmp_path):
    r1, r2 = tmp_path / "r1", tmp_path / "r2"
    r1.mkdir(), r2.mkdir()
    _write(r1, "kb", "kind: postgres\ndsn: env://A\nschemas: [one]\n")
    _write(r2, "kb", "kind: postgres\ndsn: env://B\nschemas: [two]\n")
    _write(r2, "other", "kind: postgres\ndsn: env://B\nschemas: [two]\n")
    assert load_connector("kb", [r1, r2]).dsn == "env://A"
    with pytest.raises(ConfigError, match="known: kb, other"):
        load_connector("nope", [r1, r2])


def test_resolve_secret_env(monkeypatch, caplog):
    monkeypatch.setenv("KB_X", "postgresql://u:hunter2@h/db")
    assert resolve_secret("env://KB_X", Settings()) == "postgresql://u:hunter2@h/db"
    monkeypatch.delenv("KB_DATABASE_URL", raising=False)
    with (
        caplog.at_level(logging.DEBUG),
        pytest.raises(ConfigError, match=r"env://KB_DATABASE_URL is not set"),
    ):
        resolve_secret("env://KB_DATABASE_URL", Settings())
    assert "hunter2" not in caplog.text
    with pytest.raises(ConfigError, match="unsupported secret ref scheme"):
        resolve_secret("vault://x", Settings())


def test_get_engine_cached_per_dsn(monkeypatch):
    calls = []
    monkeypatch.setattr(
        engines.PGEngine, "from_connection_string", lambda url: calls.append(url) or object()
    )
    get_engine.cache_clear()
    a = get_engine("postgresql://u@h/one")
    assert get_engine("postgresql://u@h/one") is a
    assert get_engine("postgresql://u@h/two") is not a
    assert calls == ["postgresql+asyncpg://u@h/one", "postgresql+asyncpg://u@h/two"]
    get_engine.cache_clear()


def test_embeddings_errors():
    with pytest.raises(ConfigError, match="FIREWORKS_API_KEY"):
        get_embeddings("fireworks-nomic", Settings(_env_file=None, fireworks_api_key=None))
    with pytest.raises(ConfigError, match="known: fireworks-nomic, openai-small"):
        get_embeddings("nope", Settings(_env_file=None))
    assert embedding_dimensions("fireworks-nomic") == 768
    assert embedding_dimensions("openai-small") == 1536


def test_get_vectorstore_wires_engine_and_embeddings(monkeypatch):
    seen = {}
    monkeypatch.setenv("KB_URL", "postgresql://u@h/db")
    monkeypatch.setattr(engines, "get_engine", lambda dsn: ("engine", dsn))
    monkeypatch.setattr(
        engines.PGVectorStore,
        "create_sync",
        lambda eng, emb, table_name, schema_name: (
            seen.update(eng=eng, emb=emb, table=table_name, schema=schema_name) or "store"
        ),
    )
    spec = PgVectorSpec(
        kind="pgvector", dsn="env://KB_URL", collection="docs", embeddings="openai-small"
    )
    s = Settings(_env_file=None, openai_api_key="k")
    assert get_vectorstore(spec, s) == "store"
    assert seen["eng"] == ("engine", "postgresql://u@h/db") and seen["table"] == "docs"
    assert seen["schema"] == "kb"


@pytest.mark.live
def test_live_fireworks_embed_query():
    s = Settings()
    if s.fireworks_api_key is None:
        pytest.skip("FIREWORKS_API_KEY unset")
    vec = get_embeddings("fireworks-nomic", s).embed_query("hello world")
    assert len(vec) == 768 and all(isinstance(x, float) for x in vec)
