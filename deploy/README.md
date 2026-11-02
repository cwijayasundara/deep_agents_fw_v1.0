# deploy

- `compose.dev.yaml`: local dev/test Postgres (pgvector, PG16). Run it as compose project
  `agentkit-dev`:

  ```bash
  AGENTKIT_PG_PORT=55432 docker compose -p agentkit-dev -f deploy/compose.dev.yaml up -d --wait
  export AGENTKIT_TEST_DATABASE_URL=postgresql://agentkit:agentkit@127.0.0.1:55432/agentkit
  uv run pytest -m pg            # pg tests skip when AGENTKIT_TEST_DATABASE_URL is unset
  docker compose -p agentkit-dev -f deploy/compose.dev.yaml down -v
  ```

## Encryption at rest

`agentkit-persistence` encrypts checkpoint blobs and writes, and store item values (Ruling P7), with
AES (`LANGGRAPH_AES_KEY`). It does **not** encrypt `checkpoints.metadata`, primitive
(str/int/float/bool) top-level state channels (stored inline in `checkpoints.checkpoint`, Ruling
P3), or store namespaces, keys and TTLs. Anyone with database access can read those, including
tenant and user ids. Keep user content and secrets out of them, and treat database access as
tenant-data access. Losing or changing `LANGGRAPH_AES_KEY` makes existing threads and store values
unreadable (`ValueError: MAC check failed`); nothing is overwritten. Key rotation means
re-encrypting every checkpoint blob and store value with the new key.

Prune idle threads with `uv run agentkit-prune --older-than 30d` (needs `DATABASE_URL` and
`LANGGRAPH_AES_KEY`).
