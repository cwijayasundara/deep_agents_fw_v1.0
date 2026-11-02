# Tenant isolation

Each tenant gets its own stamped deployment (compose project `agentkit-<tenant>`: Postgres volume,
collector, host ports, database password, AES key). Runs are bound to the deployment's tenant: a
CLI run for another tenant is refused before it can touch a checkpoint, and traces and ledger rows
of one tenant never appear in another's collector or database.

## Sub-features

- `ti-stamp` `make stamp TENANT=<t>` writes `deploy/tenants/<t>.env` (mode 600) once, starts the project, applies migrations; a second stamp changes nothing.
- `ti-ports-keys` two tenants never share a port or an AES key.
- `ti-precheck` `research --persist --tenant <other>` exits 1 with `TenantMismatch` before any model or DB call.
- `ti-trace-ledger` the tenant's spans carry only `agentkit.tenant=<t>`; its `agentkit_usage` and checkpoint metadata hold only `<t>`.
- `ti-contract` `make contract TENANT=<t>` runs the contract suite against the tenant DB.
- `ti-phase0-exit` `make phase0-exit` stamps `tenant-a` and `tenant-b` and proves separation offline.

## How to get to it (user POV)

- `make stamp TENANT=<t>`, `make unstamp TENANT=<t>`, `make contract TENANT=<t>`, `make phase0-exit`.
- `scripts/tenant_env.sh <t> <command>` to run anything as the tenant.

## Driving it with verify-agentkit scripts

Preconditions:

- `$S/doctor.sh` OK; Docker up.
- For `ti-phase0-exit`: `docker ps -a --format '{{.Names}}' | grep -E '^agentkit-tenant-(a|b)-'` prints nothing and nobody relies on those tenant names.

- **Stamp.** Run `$S/stamp.sh "$RUN_ID"`. `stamp.log` has `stamp: wrote deploy/tenants/verify-<RUN_ID>.env (new AES key, Postgres 127.0.0.1:<p>, OTLP 127.0.0.1:<q>)`, `setup: <n> applied; ...; agentkit_usage ready` and `stamp: tenant verify-<RUN_ID> ready: ...`; doctor shows both ports owned by `agentkit-verify-<RUN_ID>`.
- **Idempotent restamp.** Run `make stamp TENANT="verify-$RUN_ID" 2>&1 | tee -a "evidence/verify/$RUN_ID/restamp.log"`. It prints `stamp: using deploy/tenants/verify-<RUN_ID>.env (AES key unchanged)` and `setup: no new migrations`.
- **Pre-check refusal (free).** Run `scripts/tenant_env.sh "verify-$RUN_ID" uv run --no-sync research "x" --tenant someone-else --persist > "evidence/verify/$RUN_ID/mismatch.stdout" 2> "evidence/verify/$RUN_ID/mismatch.stderr.log"; echo $? > "evidence/verify/$RUN_ID/mismatch.exit"`. Exit `1`; stderr `TenantMismatch: run tenant 'someone-else' != deployment tenant 'verify-<RUN_ID>'`; no `usage:` line; `agentkit_usage.csv` (after collect) gains no row for its thread.
- **Trace and ledger separation.** After a persisted drive, run `$S/collect_evidence.sh "$RUN_ID"`. `spans-summary.txt` reads `spans by agentkit.tenant: {'verify-<RUN_ID>': <n>}`; `checks.txt` has PASS for tenant-only spans, usage rows and checkpoints.
- **Contract suite.** Run `make contract TENANT="verify-$RUN_ID" 2>&1 | tee "evidence/verify/$RUN_ID/contract.log"`. Last line `N passed` with no `skipped` (the pg contracts must run). Free, but writes the suite's test threads into the verify DB, so collect evidence first if the ledger proof matters.
- **Two-tenant exit check.** Run `make phase0-exit 2>&1 | tee "evidence/verify/$RUN_ID/phase0-exit.log"`. Last line `phase0 exit: tenant-a OK, tenant-b OK, traces separated`. Then `make unstamp TENANT=tenant-a` and `make unstamp TENANT=tenant-b`, keeping their env files only if they existed before.

## Gotchas

- `make phase0-exit` uses fixed tenant names and leaves both stamps running; it is a scripted (no live model) run. Never run it while someone else's `tenant-a`/`tenant-b` holds real data.
- Tenant names must match `^[a-z0-9][a-z0-9_-]{0,62}$`; `example` is refused. Never set `AGENTKIT_TENANT` in `.env` (it would override every stamp; `tenant_env.sh` refuses).
- Ports 15432 and 16379 are reserved for other local stacks and are never handed out; leftover `deploy/tenants/*.env` files keep their ports reserved even when stopped.
- Never run `pytest -m pg` with `AGENTKIT_TEST_DATABASE_URL` pointing at a tenant DB; only `make contract` targets a tenant DB, on purpose.
- The guard inside the graph runs after LangGraph checkpoints the input; the CLI pre-check is what keeps a mismatched run out of the history. Code that calls a persistent graph directly must repeat it.
