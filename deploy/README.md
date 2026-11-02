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

## Tracing and the cost ledger

Tracing is off unless `OTEL_EXPORTER_OTLP_ENDPOINT` is set. `agentkit-telemetry` then emits
Langfuse-shaped OTel spans (resource `agentkit.tenant`, span `user.id`, `session.id`,
`langfuse.trace.metadata.*`) to that collector only. Prompt and completion text is dropped at export
unless `AGENTKIT_TRACE_PAYLOADS=1`. `LANGSMITH_TRACING` is never set. A dead collector costs one
warning line; spans are dropped, the run is not affected.

```bash
docker compose -p agentkit-dev -f deploy/compose.dev.yaml --profile tracing up -d   # + collector
OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318 uv run python scripts/smoke.py --trace
tail -n 1 deploy/otel-out/spans.jsonl          # one JSON line per exported batch
```

Forwarding to Langfuse is configured but off in `otel-collector.dev.yaml` (no keys yet): uncomment
the `otlphttp/langfuse` exporter and add it to the pipeline.

Every CLI run is metered by a `CostLedger`: one row per run (tenant, thread, model, input / output /
cached tokens, Decisions tokens). Without `--persist` the CLIs print a one-line `usage:` total; with
`--persist` rows also go to the `agentkit_usage` table, created on first use (`ledger.setup`). Run
metadata (tenant, product, team, user, thread, agent, prompt hash) is also copied by LangGraph into
the plaintext `checkpoints.metadata` column: identifiers only, never user content.
