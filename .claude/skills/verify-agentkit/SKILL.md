---
name: verify-agentkit
description: Drive the agentkit research agent CLI (`uv run research`, `research-eval`, `agentkit validate`) the way an operator does, live on fireworks-glm against a throwaway stamped tenant (Docker Postgres + OTel collector), and keep the report, transcript, trace spans, agentkit_usage rows and eval scores as evidence. Use to prove a change to agentkit works end to end in the real CLI, not just in pytest, or when asked to verify, smoke or demo the research agent, tenant stamping, persistence/resume, tracing or the cost ledger.
---

# Verify agentkit

agentkit's user surface is a set of CLIs run from the repo root: `uv run research` (one research
turn, optionally persisted to a tenant's encrypted Postgres and traced to its collector),
`uv run research-eval` (scored eval), `uv run agentkit validate` (offline YAML checks),
`uv run agentkit tools list`, `uv run agentkit-kb setup|ingest` (the knowledge-base pilot
`apps/kb_agent`, run with `research --agent apps/kb_agent/agent.yaml`), the pytest plugin
(`pytest ... --agentkit-live`),
`uv run agentkit-prune`, and the `make stamp/unstamp/contract/phase0-exit` tenant targets. There is
no server: "launch" means stamping one isolated verification tenant; each drive is a short-lived
CLI process whose stdout/stderr is teed into the evidence dir.

Feature recipes: [`features/README.md`](features/README.md). Background: `docs/architecture.md`
(sections 13 and 14 are the CLI reference), `deploy/README.md`.

## Hard rules

- **Model:** live runs use only the `fireworks-glm` registry entry, as agent and as eval judge. The
  helpers hard-code it and refuse `--model`. Never fan out across providers.
- **Cost:** every `research` turn and every eval case is real money (Fireworks tokens, web search
  API traffic, one Decisions call per new thread). Plan the number of turns before you
  start, and give each eval a ONE-case dataset (`drive_eval.sh` writes one). Never run the
  10-case `evals/smoke.jsonl` as a proof.
- **Secrets:** keys live in the repo `.env` (read by `Settings`, which prefers `.env` over the
  shell). Print key NAMES only (`grep -oE '^[A-Z_]+=.' .env | cut -d= -f1`). Never cat, copy or
  commit `.env` or `deploy/tenants/*.env`, which holds the tenant's AES key.
- **Isolation:** one tenant per run, `verify-<RUN_ID>`, as compose project `agentkit-verify-<RUN_ID>`
  with its own volume, ports, password, AES key and collector. Never touch `tenant-a`/`tenant-b`
  stamps you did not create, `agentkit-dev`, `b2blocal-*`, `superagent-*` or any other container.
  Never run `pytest -m pg` against a tenant DB (it creates and drops schemas; dev DB only).
- **Evidence first:** the trace and the ledger live inside the stamp. `make unstamp` is
  `docker compose down -v` and destroys them, so copy them out first (Ruling P12).
  `cleanup.sh` does that for you.

## Launch

```bash
cd "$(git rev-parse --show-toplevel)"
make sync                                      # once per checkout (uv sync, pinned)
RUN_ID=$(date +%Y%m%d-%H%M%S)                  # lowercase, digits, '-'; tenant = verify-$RUN_ID
.claude/skills/verify-agentkit/scripts/stamp.sh "$RUN_ID"
```

`stamp.sh` runs `make stamp TENANT=verify-$RUN_ID` (writes `deploy/tenants/verify-$RUN_ID.env`
with fresh free ports from 55500 up, starts Postgres and the collector with `--wait`, applies
checkpoint/store migrations and creates `agentkit_usage`), then the tenant doctor. Ready means both
`stamp: tenant verify-<RUN_ID> ready: project agentkit-verify-<RUN_ID>, Postgres 127.0.0.1:<p>,
OTLP 127.0.0.1:<q>, traces -> deploy/otel-out/verify-<RUN_ID>/spans.jsonl` and `doctor: OK`.
Takes about 15 s with images cached. An ephemeral run (`--ephemeral`) needs no stamp at all.

## Doctor

```bash
.claude/skills/verify-agentkit/scripts/doctor.sh             # host: before stamping
.claude/skills/verify-agentkit/scripts/doctor.sh "$RUN_ID"   # host + tenant verify-$RUN_ID
```

One PASS/WARN/FAIL line per check; exit 1 on any FAIL. Host: `uv`, `jq`, key names
`FIREWORKS_API_KEY` and `OPENAI_API_KEY` in `.env` (`TAVILY_API_KEY` optional), `.env` does not set
`AGENTKIT_TENANT`, `agentkit validate` passes on the shipped agent, the Decisions API answers a
one-question probe through the product's own `DecisionsClient` (a fraction of a cent), Fireworks
answers a model listing, Docker is up, no stale `verify-*.env` files. Tenant: env file present,
postgres `running/healthy`, collector running, both host ports owned by this compose project,
collector accepts TCP, `agentkit_usage` and the migration tables exist. With a RUN_ID the output
is appended to `evidence/verify/$RUN_ID/doctor.txt`. Run it first whenever anything looks off.

## Drive

```bash
S=.claude/skills/verify-agentkit/scripts
# one persisted, traced turn (REAL; ~1-3 min)
$S/drive_research.sh "$RUN_ID" turn1 "What is the Model Context Protocol and what problem does it solve?"
# resume that thread (REAL): the thread id is the `thread:` line of turn1.stdout
$S/drive_research.sh "$RUN_ID" turn2 "How does it compare to plain function calling?" \
  --thread "$(sed -n 's/^thread: //p' "evidence/verify/$RUN_ID/turn1.stdout")"
# one-case eval, judged by fireworks-glm (REAL)
$S/drive_eval.sh "$RUN_ID" mcp
# no-cost tenant guard probe: refused before any model call, exit 1 (collect checks it wrote no row)
E=evidence/verify/$RUN_ID
scripts/tenant_env.sh "verify-$RUN_ID" uv run --no-sync research "x" --tenant someone-else --persist \
  >"$E/mismatch.stdout" 2>"$E/mismatch.stderr.log"; echo $? >"$E/mismatch.exit"
```

`drive_research.sh <RUN_ID> <LABEL> "<question>" [args]` runs
`scripts/tenant_env.sh verify-<RUN_ID> uv run research "<question>" --model fireworks-glm --tenant verify-<RUN_ID> --persist --out evidence/verify/<RUN_ID>/<LABEL>.report.md [args]`
and tees stdout/stderr. `--ephemeral` as the first extra arg drops the tenant, `--persist` and
tracing. Stable handles on stdout: `thread: <uuid>`, `resumed thread <uuid> at step <n>` (resumes
only), `trace: <32 hex>` (traced runs), `usage: ...`, `wrote <path>`. Progress on stderr:
`agent ... -> fireworks accounts/fireworks/models/glm-5p3-flash (tier=default, selection=decisions)`,
`selection for thread <id>: tier=<t> tools=<names>` (Decisions), `orchestrator -> ...` tool calls, `agent finished in <s>s`. Exit codes:
0 ok; 2 argparse/`SpecErrors`/`ConfigError` (one line on stderr); 1 `TenantMismatch` or
`agent finished without writing /report.md`. Per-feature recipes and expected end states:
`features/`.

## Evidence

Location: `evidence/verify/<RUN_ID>/` (git-ignored by `.gitignore` rule `evidence/verify/`; never
commit it). After the drives and before cleanup:

```bash
.claude/skills/verify-agentkit/scripts/collect_evidence.sh "$RUN_ID"
```

| File | What it proves |
|---|---|
| `<label>.cmd.txt`, `.stdout`, `.stderr.log`, `.exit` | The exact command, its transcript and exit code |
| `<label>.report.md`, `<label>.summary.txt` | The report the user gets; thread/trace/usage lines |
| `spans.jsonl`, `spans-summary.txt` | Copy of the tenant collector's file; spans per `agentkit.tenant`, trace ids, masked count |
| `agentkit_usage.csv` | Every ledger row (tenant, thread_id, model, token counts) |
| `checkpoints.csv` | Threads and max step per checkpoint-metadata tenant |
| `eval-dataset.jsonl`, `eval_results.md`, `eval_results.json` | The one-case dataset and its scores |
| `doctor.txt`, `stamp.log`, `compose-ps.txt`, `cleanup.log`, `checks.txt`, `MANIFEST.txt` | Launch, health, assertions, teardown |

`checks.txt` must be all PASS: spans exist and carry only `agentkit.tenant=verify-<RUN_ID>`, every
printed trace id is in the spans, `agentkit_usage` has rows and all of them belong to the tenant,
every persisted thread that printed `usage:` has a row, and checkpoints belong to the tenant only.
Proof standards: drive the real CLI path (no scripted model, no test-only setters; `scripts/smoke.py`
is offline scaffolding, not proof of the live agent). Capture the action and the resulting state:
read the report (inline `[n]` citations and a `Sources` list of fetched URLs), and check the side
effects (ledger rows, checkpoints, spans), not just exit 0. The only mock-free boundary that is
not exercised is Langfuse forwarding (off unless the tenant env file has Langfuse keys).

## Cleanup

```bash
.claude/skills/verify-agentkit/scripts/cleanup.sh "$RUN_ID"
```

Collects evidence first if it is missing (best effort), then `make unstamp TENANT=verify-$RUN_ID`
(removes only that compose project's containers, network and volume), deletes
`deploy/tenants/verify-$RUN_ID.env` and `deploy/otel-out/verify-$RUN_ID/`, asserts nothing of the
project remains, lists other `agentkit-*` containers without touching them, and lists the
evidence dir to show it survived. Run it after every failed attempt too; it is idempotent. The
CLIs are foreground processes that exit on their own: there is nothing else to kill. If a drive
hangs, stop that one process (Ctrl-C or its own PID), never `pkill python`.

## Helpers

All in `.claude/skills/verify-agentkit/scripts/` (bash 3.2-safe, `set -euo pipefail`, run from
anywhere; they `cd` to the repo root and set `UV_CONSTRAINT=constraints.txt`):

| Script | Invocation | Cost |
|---|---|---|
| `doctor.sh` | `doctor.sh [RUN_ID]` | one tiny Decisions probe |
| `stamp.sh` | `stamp.sh RUN_ID` | free (Docker) |
| `drive_research.sh` | `drive_research.sh RUN_ID LABEL "question" [--ephemeral] [--thread ID] [--user U] [-v]` | one real turn |
| `drive_eval.sh` | `drive_eval.sh RUN_ID [CASE_ID]` (case ids from `apps/research_agent/evals/smoke.jsonl`) | one turn + judge calls |
| `collect_evidence.sh` | `collect_evidence.sh RUN_ID` | free |
| `cleanup.sh` | `cleanup.sh RUN_ID` | free |
| `common.sh` | sourced by the others (RUN_ID -> tenant, paths, `compose`, `psql_tenant`) | - |

## Gotchas

- Web search (`backend: auto`) uses each set key in order Parallel, Brave, Tavily, then DuckDuckGo.
  `web_search backend X failed ... ` warnings mean a fallback happened; that is fine in small numbers.
  With no search key it is DuckDuckGo only, which rate-limits bursts (`DDGSException`, `<- web_search
  error`); many of them, thin reports, or `agent finished without writing /report.md` are not normal.
  Wait and rerun as a new LABEL; do not weaken the question. Pinning a backend is an `agent.yaml` change.
- A Decisions failure does not fail the run: stderr shows `selection unavailable for thread ...`
  and the agent falls back to all tools. Treat that line as a doctor finding, not a pass.
- `research-eval` checks the tenant even without `--persist`: through `tenant_env.sh` you must pass
  `--tenant verify-<RUN_ID>` or it exits 2 with `ConfigError: TenantMismatch: ...`.
- `--thread` without `--persist` is an argparse error (exit 2). A resume prints
  `resumed thread <id> at step <n>` before the agent starts; no line means a new thread.
- Spans reach `spans.jsonl` about 1 s after the CLI exits (collector batching); collect waits for
  every printed trace id. Payloads are masked (`agentkit.payload.masked`) unless
  `AGENTKIT_TRACE_PAYLOADS=1`.
- `agentkit validate` with a path outside the repo cannot see `libraries/` (prompts show
  `known: (none)`); put scratch YAML under the evidence dir. A glob that matches nothing is skipped
  and exits 0 with `checked 0 file(s)`.
- `make phase0-exit` stamps the fixed tenants `tenant-a` and `tenant-b` and leaves them running.
  Only run it when no one uses those names, and `make unstamp` both afterwards.
- `make unstamp` keeps the env file on purpose (it holds the AES key); `cleanup.sh` deletes it
  because a verify tenant's data is throwaway. Never do that for a real tenant.
- `ImportError: cannot import name ... from 'agentkit_core' (unknown location)` means macOS re-hid the
  editable-install `.pth` files (it can recur mid-session). Run `make sync` (or
  `chflags nohidden .venv/lib/python*/site-packages/*.pth`) and rerun the drive as a new LABEL.
- The shipped agent needs `FIREWORKS_API_KEY` even off Fireworks (its fallback model is built at load),
  and its eval gate (`research-eval --gate`) is a 25-case release check, not a verification drive.
- Default CLI outputs (`report.md`, `eval_results.*` at the repo root) are git-ignored but are not
  evidence: always pass `--out` into the evidence dir (the helpers do).

## Proof record and maintenance

First proven 2026-11-02 (RUN_ID `20261102-proof1`, local Docker Desktop on macOS): doctor, stamp,
one persisted `research-question` turn (exit 0, 5 sources, 41 s), the mismatch probe (exit 1, no
row), a one-case `mcp` eval (all scores 1.00), collect (all PASS: 88 masked spans of the tenant
only, 2 usage rows), cleanup (project gone, evidence kept). Re-proven 2026-11-02 for Phase 1 (RUN_ID `20261102-phase1`): the middleware stack rode along on a
persisted turn (exit 0, 35 s, `## Sources` report), a one-case `mcp` eval scored all seven metrics 1.00,
the `--gate` mismatch probe exited 2 with `gate: baseline mismatch: ...`, `--write-baseline` without
`--gate` exited 2, checks all PASS (223 spans, 2 usage rows), cleanup clean. Re-proven 2026-11-02 for the rest of Phase 1
(RUN_ID `20261102-phase1b`): doctor OK; a persisted research turn after the tool-description change
(exit 0, 34 s, `## Sources`); `agentkit tools list` (four tools at 1.0.0); `agentkit-kb setup` and
`make kb-ingest` (161 chunks) on the verify tenant; one persisted `apps/kb_agent` turn as `kb_reader`
(exit 0, 8 `kb_search` lines, `## Sources` of GitHub blob URLs); the plugin skip (12 skipped) and one
live plugin case (`first-factual` PASSED); checks all PASS (163 masked spans, 2 usage rows); cleanup
clean. Not yet driven live by this skill: the
resume turn, `make contract`, `make phase0-exit`, `agentkit validate` recipes (validate output was
checked by hand when writing the map). Keep the map honest as the CLIs change with
`/pstack:maintain-verification-skill`.
