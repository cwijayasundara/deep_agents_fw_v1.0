# agentkit-persistence

Encrypted Postgres persistence for agent threads and memory.

- `PersistenceSettings` reads `DATABASE_URL` and `LANGGRAPH_AES_KEY` (raw 16, 24 or 32 characters,
  not base64) from the environment, then the nearest `.env`. `PersistenceSettings.from_env()` turns
  a missing value into `ConfigError`.
- `open_persistence(settings)` opens two pools (`autocommit`, `prepare_threshold=0`, `dict_row`),
  sets up an `AsyncPostgresSaver` with `EncryptedSerializer` and an `AsyncPostgresStore` with a
  `TTLConfig`, starts the TTL sweeper, and closes everything on exit. It refuses to start with
  `ConfigError: LANGGRAPH_AES_KEY must be 16, 24, or 32 characters`.
- `thread_lock(persistence, thread_id)` holds `pg_advisory_lock(hashtext(thread_id))` on a
  connection from the separate lock pool, so concurrent runs on one thread form one linear
  checkpoint chain instead of losing an update.
- `prune(persistence, older_than)` / `agentkit-prune --older-than 30d` deletes threads whose newest
  checkpoint `ts` is older than the cutoff and prints `pruned N threads`.

## What is encrypted at rest (Ruling P3)

| Where | Encrypted |
|---|---|
| `checkpoint_blobs`, `checkpoint_writes` (`msgpack+aes`) | yes |
| container state channels (`messages`, `files`, lists, dicts) | yes (stored as blobs) |
| primitive top-level state channels (str, int, float, bool) | **no**: inline JSONB in `checkpoints.checkpoint` |
| `checkpoints.metadata` | **no**: plaintext JSONB |
| store items (`store` table) | **no**: plaintext JSONB |

Keep user content and secrets out of checkpoint metadata and out of primitive top-level state
channels. The research agent's state uses containers, so it is unaffected. Store values are not
encrypted by this package; protect them with database-level controls.
