"""A store wrapper that encrypts item values at rest (Ruling P7).

Each put value becomes `{"__enc": <type>, "ct": <base64>}`, made by the same
`EncryptedSerializer` (and key) as the checkpoint saver. Namespace, key and TTL stay plaintext,
so per-label prefix search, `list_namespaces` and the TTL sweeper keep working. Reading a value
that is not such an envelope with an `+aes` type (a plaintext value) raises
`StoreEncryptionError`: there is no legacy plaintext data. Value filters and vector indexes would
need plaintext values, so both are rejected. Rotating the key means re-encrypting
every item.
"""

from __future__ import annotations

import base64
from collections.abc import Iterable
from typing import Any

from langgraph.checkpoint.serde.base import SerializerProtocol
from langgraph.store.base import (
    BaseStore,
    GetOp,
    Item,
    Op,
    PutOp,
    Result,
    SearchItem,
    SearchOp,
)

_ENC, _CT = "__enc", "ct"


class StoreEncryptionError(ValueError):
    """An operation that cannot work on encrypted store values, or a stored value that is not
    encrypted."""


class EncryptedStore(BaseStore):
    """Delegates to `inner`, encrypting values on put and decrypting them on get/search."""

    def __init__(self, inner: BaseStore, serde: SerializerProtocol) -> None:
        if getattr(inner, "index_config", None):
            raise StoreEncryptionError(
                "an encrypted store cannot have a vector index: embeddings need plaintext values"
            )
        self._inner = inner
        self._serde = serde
        self.supports_ttl = inner.supports_ttl
        self.ttl_config = inner.ttl_config

    def batch(self, ops: Iterable[Op]) -> list[Result]:
        ops = list(ops)
        return self._decrypt_results(ops, self._inner.batch(self._encrypt_ops(ops)))

    async def abatch(self, ops: Iterable[Op]) -> list[Result]:
        ops = list(ops)
        return self._decrypt_results(ops, await self._inner.abatch(self._encrypt_ops(ops)))

    def _encrypt_ops(self, ops: list[Op]) -> list[Op]:
        return [self._encrypt_op(op) for op in ops]

    def _encrypt_op(self, op: Op) -> Op:
        if isinstance(op, SearchOp) and op.filter:
            raise StoreEncryptionError("value filter is not supported: store values are encrypted")
        if isinstance(op, PutOp) and op.value is not None:
            type_, data = self._serde.dumps_typed(dict(op.value))
            envelope = {_ENC: type_, _CT: base64.b64encode(data).decode()}
            return op._replace(value=envelope)
        return op

    def _decrypt_results(self, ops: list[Op], results: list[Result]) -> list[Result]:
        out: list[Result] = []
        for op, result in zip(ops, results, strict=True):
            if isinstance(op, GetOp) and isinstance(result, Item):
                out.append(self._decrypt_item(result))
            elif isinstance(op, SearchOp) and isinstance(result, list):
                out.append([self._decrypt_item(item) for item in result])
            else:
                out.append(result)
        return out

    def _decrypt_item(self, item: Any) -> Any:
        value = item.value
        if not (
            isinstance(value, dict)
            and set(value) == {_ENC, _CT}
            and isinstance(value[_ENC], str)
            and value[_ENC].endswith("+aes")
        ):
            raise StoreEncryptionError(
                f"store item {item.namespace!r}/{item.key!r} is not encrypted"
                " (expected an {'__enc': '<type>+aes', 'ct': ...} envelope)"
            )
        data = base64.b64decode(value[_CT])
        plain = self._serde.loads_typed((value[_ENC], data))
        if isinstance(item, SearchItem):
            return SearchItem(
                item.namespace, item.key, plain, item.created_at, item.updated_at, item.score
            )
        return Item(
            value=plain,
            key=item.key,
            namespace=item.namespace,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )
