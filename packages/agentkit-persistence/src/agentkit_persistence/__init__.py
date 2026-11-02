"""agentkit-persistence: encrypted Postgres checkpoints and store, thread locks, pruning.

Encryption at rest (Ruling P3): checkpoint blobs and writes are AES-encrypted, but
`checkpoints.metadata` and primitive (str/int/float/bool) top-level state channels stay
plaintext JSONB in `checkpoints.checkpoint`. Containers (`messages`, `files`) are encrypted.
Keep user content and secrets out of metadata and out of primitive top-level channels.
Store item values are encrypted by `EncryptedStore` (Ruling P7); namespaces and keys are not.
"""

from .encrypted_store import EncryptedStore, StoreEncryptionError
from .lock import thread_lock
from .open import AES_KEY_ERROR, Persistence, PersistenceSettings, open_persistence
from .prune import prune

__all__ = [
    "AES_KEY_ERROR",
    "EncryptedStore",
    "Persistence",
    "PersistenceSettings",
    "StoreEncryptionError",
    "open_persistence",
    "prune",
    "thread_lock",
]
