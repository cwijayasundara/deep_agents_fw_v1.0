from __future__ import annotations

import uuid
from typing import Any

import pytest
from agentkit_persistence import Persistence
from agentkit_persistence.encrypted_store import EncryptedStore, StoreEncryptionError
from langgraph.checkpoint.serde.encrypted import EncryptedSerializer
from langgraph.store.memory import InMemoryStore

KEY = b"0123456789abcdef0123456789abcdef"
NS = ("acme", "agentkit", "platform", "u1", "memories")
VALUE = {"text": "PINEAPPLE secret", "n": 3, "tags": ["a", "b"]}


def _store(inner: Any = None) -> tuple[EncryptedStore, InMemoryStore]:
    raw = inner or InMemoryStore()
    serde = EncryptedSerializer.from_pycryptodome_aes(key=KEY)
    return EncryptedStore(raw, serde), raw


async def test_roundtrip_put_get_search() -> None:
    store, raw = _store()
    await store.aput(NS, "k", VALUE)
    assert (await store.aget(NS, "k")).value == VALUE  # type: ignore[union-attr]
    found = await store.asearch(("acme",), limit=100)
    assert [(i.namespace, i.key, i.value) for i in found] == [(NS, "k", VALUE)]
    stored = (await raw.aget(NS, "k")).value  # type: ignore[union-attr]
    assert set(stored) == {"__enc", "ct"} and stored["__enc"].endswith("+aes")
    assert "PINEAPPLE" not in repr(stored)


def test_sync_roundtrip() -> None:
    store, _ = _store()
    store.put(NS, "k", VALUE)
    assert store.get(NS, "k").value == VALUE  # type: ignore[union-attr]


async def test_legacy_plaintext_values_pass_through() -> None:
    store, raw = _store()
    await raw.aput(NS, "old", {"text": "legacy"})
    assert (await store.aget(NS, "old")).value == {"text": "legacy"}  # type: ignore[union-attr]


async def test_delete_and_missing() -> None:
    store, _ = _store()
    await store.aput(NS, "k", VALUE)
    await store.adelete(NS, "k")
    assert await store.aget(NS, "k") is None


async def test_namespaces_stay_listable() -> None:
    store, _ = _store()
    await store.aput(NS, "k", VALUE)
    assert await store.alist_namespaces(prefix=("acme",)) == [NS]


async def test_value_filter_is_rejected() -> None:
    store, _ = _store()
    with pytest.raises(StoreEncryptionError, match="filter"):
        await store.asearch(("acme",), filter={"text": "x"})


def test_index_config_is_rejected() -> None:
    inner = InMemoryStore(index={"dims": 2, "embed": lambda texts: [[0.0, 0.0] for _ in texts]})
    with pytest.raises(StoreEncryptionError, match="index"):
        _store(inner)


async def test_wrong_key_cannot_read() -> None:
    store, raw = _store()
    await store.aput(NS, "k", VALUE)
    other = EncryptedStore(raw, EncryptedSerializer.from_pycryptodome_aes(key=b"f" * 32))
    with pytest.raises(ValueError, match="MAC check failed"):
        await other.aget(NS, "k")


@pytest.mark.pg
async def test_store_table_holds_no_plaintext(persistence: Persistence) -> None:
    assert isinstance(persistence.store, EncryptedStore)
    tenant = f"t{uuid.uuid4().hex[:8]}"
    ns = (tenant, "agentkit", "platform", "u1", "memories")
    await persistence.store.aput(ns, "k", VALUE)
    assert (await persistence.store.aget(ns, "k")).value == VALUE  # type: ignore[union-attr]
    async with persistence.pool.connection() as conn:
        cur = await conn.execute(
            "select value::text like '%%PINEAPPLE%%' as leak, value ? '__enc' as enc "
            "from store where prefix = %s",
            (".".join(ns),),
        )
        rows: list[dict[str, Any]] = await cur.fetchall()
    assert rows == [{"leak": False, "enc": True}]


@pytest.mark.pg
async def test_prefix_isolation_through_wrapper(persistence: Persistence) -> None:
    acme, other = f"a{uuid.uuid4().hex[:8]}", f"o{uuid.uuid4().hex[:8]}"
    for tenant in (acme, other, f"{acme}b"):
        await persistence.store.aput((tenant, "memories"), "k", {"tenant": tenant})
    found = await persistence.store.asearch((acme,), limit=100)
    assert [(i.namespace, i.value) for i in found] == [((acme, "memories"), {"tenant": acme})]
