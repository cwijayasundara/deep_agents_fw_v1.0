# deploy

- `compose.dev.yaml`: local dev/test Postgres (pgvector, PG16). Run it as compose project
  `agentkit-dev`:

  ```bash
  AGENTKIT_PG_PORT=55432 docker compose -p agentkit-dev -f deploy/compose.dev.yaml up -d --wait
  export AGENTKIT_TEST_DATABASE_URL=postgresql://agentkit:agentkit@127.0.0.1:55432/agentkit
  uv run pytest -m pg            # pg tests skip when AGENTKIT_TEST_DATABASE_URL is unset
  docker compose -p agentkit-dev -f deploy/compose.dev.yaml down -v
  ```

  **Never point `AGENTKIT_TEST_DATABASE_URL` at a real tenant database for `pytest -m pg`.** The
  package pg tests write rows and create and drop throwaway schemas; run them against the dev
  database only. `make contract` / `scripts/phase0_exit.sh` aim it at a tenant database on purpose
  and run only `contracts/`, which writes test threads under fresh ids and drops nothing.

## One deployment per tenant

`compose.yaml` is the per-tenant stamp: Postgres (own named volume) plus a trace collector
(`otel-collector.yaml`, own JSONL file). Each tenant runs it as compose project `agentkit-<tenant>`,
so containers, network, volume, host ports, database password, AES key and collector are all its
own; nothing is shared. Always start it through the stamp script:

```bash
make stamp TENANT=tenant-a      # = scripts/stamp_tenant.sh tenant-a
```

The first stamp writes `deploy/tenants/tenant-a.env` (shape: `tenants/example.env`; git-ignored,
mode 600): a fresh 32-character `LANGGRAPH_AES_KEY`, a fresh database password, and two free host
ports from 55500 up (never 15432/16379, never a port another tenant file holds; set `STAMP_PG_PORT`
/ `STAMP_OTLP_PORT` to choose). Later stamps reuse the file unchanged, start the project if needed,
and re-run the setup (`setup: no new migrations`). Back the env file up: it is the only copy of
the tenant's key.

Run anything as a tenant with `scripts/tenant_env.sh <tenant> <command>`, which exports the
tenant's `AGENTKIT_TENANT`, `DATABASE_URL`, `LANGGRAPH_AES_KEY` and `OTEL_EXPORTER_OTLP_ENDPOINT`
over the shell's. `AGENTKIT_TENANT` must not be set in the repo `.env` (it would win over every
stamp; the helper refuses).

```bash
scripts/tenant_env.sh tenant-a uv run research "question" --tenant tenant-a --persist
scripts/tenant_env.sh tenant-a uv run python scripts/smoke.py --persist --trace --tenant tenant-a
make contract TENANT=tenant-a   # contract suite (incl. pg contracts) against the tenant's DB
make phase0-exit                # stamps tenant-a + tenant-b and proves the separation
make unstamp TENANT=tenant-a    # docker compose down -v: deletes the DB; keeps the env file
```

`make contract` writes the contract suite's own test threads and store items into the tenant's
database (under the suite's fixed test key); run it on test tenants, not on one holding real data.

Spans land in `deploy/otel-out/<tenant>/spans.jsonl` (git-ignored). To forward a tenant's spans to
its own Langfuse project as well, set `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` and
`LANGFUSE_HOST` in its env file and stamp again: the script then adds the `otlp_http/langfuse`
exporter to the collector pipeline (`AGENTKIT_OTEL_EXPORTERS`), with the endpoint
`$LANGFUSE_HOST/api/public/otel` and Basic auth from the two keys.

`scripts/phase0_exit.sh` (`make phase0-exit`) stamps `tenant-a` and `tenant-b`, checks that they
share no port or key, runs the contract suite and one scripted, persisted, traced smoke run
against each, then asserts that each collector file holds spans of its own tenant only (and never
names the other), and that each database's checkpoints and `agentkit_usage` rows belong to its own
tenant only. It ends with `phase0 exit: tenant-a OK, tenant-b OK, traces separated` and leaves both
stamps running.

## Knowledge base: schema `kb` and the read-only role

Agents reach Postgres only through the curated tools `kb_search` (a `pgvector` connector) and
`sql_query` (a `postgres` connector); connector specs live in `libraries/connectors/<name>.yaml`
and their `dsn` is an `env://VAR` ref, resolved when the agent is built. KB tables live in schema
`kb`. Requires Postgres >= 15 (no CREATE on `public` for PUBLIC); the stamp runs PG16. Do not
install `dblink` or `postgres_fdw` in a KB database. Set it up once per tenant database, with a
connector whose DSN is the admin login (`kb-docs`, `KB_DATABASE_URL`). Run `setup` and `ingest`
as the **same** admin login: kb_reader's SELECT on new tables comes from default privileges, which
apply only to tables created by the role that ran `setup`.

```bash
export KB_READER_PASSWORD=...        # read from this env var; never printed or logged
# admin login: setup and ingest (kb_search's connector kb-docs uses it too)
scripts/tenant_env.sh tenant-a sh -c 'KB_DATABASE_URL="$DATABASE_URL" uv run agentkit-kb setup \
  --connector kb-docs --reader-password-env KB_READER_PASSWORD'
scripts/tenant_env.sh tenant-a sh -c 'KB_DATABASE_URL="$DATABASE_URL" uv run agentkit-kb ingest \
  --connector kb-docs README.md docs/*.md --source-base https://github.com/<owner>/<repo>/blob/main'
# sql_query's connector kb-sql must log in as kb_reader, never as the admin:
export KB_READER_DATABASE_URL="postgresql://kb_reader:$KB_READER_PASSWORD@127.0.0.1:<pg port>/agentkit"
```

`setup` is idempotent (a re-run resets the password and re-applies the grants). It creates schema
`kb` and role `kb_reader`: LOGIN, no superuser/createdb/createrole/replication/bypassrls,
`default_transaction_read_only=on`, USAGE + SELECT on `kb` (including future tables, through
default privileges), nothing else. The password goes to the server as a SCRAM-SHA-256 verifier,
so it never appears in server logs. `ingest` splits Markdown on headings and then into ~1,500
character chunks, and upserts them with `{title, source_url}`; re-ingesting a file replaces its
chunks.

Point the `sql_query` connector at `kb_reader` (`KB_READER_DATABASE_URL`). Its safety is layered
and the role is the real wall. On first use `sql_query` checks the login and refuses to run
(`ERROR: sql_query connector must log in as a read-only role (e.g. kb_reader)`) if it is a
superuser or bypasses RLS, is a member of `pg_execute_server_program` / `pg_read_server_files` /
`pg_write_server_files` / `pg_read_all_data`, or can CREATE in a configured schema. Every call
then runs one statement (anything after `;` is refused) in a rolled-back `READ ONLY` transaction
with `SET LOCAL statement_timeout` and `search_path` = the connector's `schemas`, releases any
advisory locks, and reads at most `max_rows` rows (cells capped at 2,000 characters, output at
50,000).

The connector pg tests (`packages/agentkit-connectors/tests/test_pg_tools.py`) create schema `kb`
and reset `kb_reader`'s password; run them on a throwaway stamp only:

```bash
make stamp TENANT=kbtest
scripts/tenant_env.sh kbtest sh -c 'AGENTKIT_TEST_DATABASE_URL="$DATABASE_URL" \
  uv run --no-sync pytest -m pg packages/agentkit-connectors'
make unstamp TENANT=kbtest && rm deploy/tenants/kbtest.env
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
unless `AGENTKIT_TRACE_PAYLOADS=1`. Error text is masked too: exception messages, stack traces and
status descriptions (including an error tool message's content) are replaced, and only the
exception type name (e.g. `ValueError`) is kept. `LANGSMITH_TRACING` is never set. A dead collector costs one
warning line; spans are dropped, the run is not affected.

```bash
docker compose -p agentkit-dev -f deploy/compose.dev.yaml --profile tracing up -d   # + collector
OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318 uv run python scripts/smoke.py --trace
tail -n 1 deploy/otel-out/spans.jsonl          # one JSON line per exported batch
```

Forwarding to Langfuse is configured but off in `otel-collector.dev.yaml` (no keys yet): uncomment
the `otlp_http/langfuse` exporter and add it to the pipeline.

Every CLI run is metered by a `CostLedger`: one row per run (tenant, thread, model, input / output /
cached tokens, Decisions tokens). Without `--persist` the CLIs print a one-line `usage:` total; with
`--persist` rows also go to the `agentkit_usage` table, created on first use (`ledger.setup`). Run
metadata (tenant, product, team, user, thread, agent, prompt hash) is also copied by LangGraph into
the plaintext `checkpoints.metadata` column: identifiers only, never user content.
