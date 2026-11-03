# agentkit

Shared, self-hosted, multi-tenant agent platform on DeepAgents / LangChain v1 / LangGraph.
Phase 0 is complete: a deep-research agent, defined in YAML and built through the `build_deep_agent`
factory, runs end to end on any registry model, with persisted threads, tenant-tagged traces and a usage
ledger. The full technical reference is [`docs/architecture.md`](docs/architecture.md).

## Architecture

agentkit is a thin policy layer over DeepAgents, not a fork. Teams describe an agent in `agent.yaml`,
picking a model, prompt, tools, skills, subagents and middleware by name from shared pools.
`agentkit-config` validates every name at load time and resolves the file into kwargs for
`build_deep_agent`, the one place that calls `create_deep_agent`. The factory always adds the
`PlatformContext` schema, puts `TenantGuardMiddleware` first, and wires encrypted Postgres persistence and
memory tiers when asked. Optional OpenAI Decisions selection picks the visible tools and the model tier
once per thread. Each tenant gets its own stamped deployment (database, AES key, collector, ports).

```mermaid
flowchart LR
  yaml["agent.yaml + libraries/ (prompts, subagents, skills)"] --> config["agentkit-config: load, validate, resolve"]
  pools["entry-point pools: agentkit-tools, agentkit-middleware, app nodes and schemas"] --> config
  models["agentkit-core: models.yaml, Settings, PlatformContext"] --> config
  config --> deep["agentkit-deep: build_deep_agent (TenantGuard first, memory tiers, prompt hash)"]
  deep --> da["DeepAgents create_deep_agent"]
  da --> run["run with context=PlatformContext"]
  run --> persist[("agentkit-persistence: encrypted Postgres per tenant")]
  run --> tele["agentkit-telemetry: OTLP traces + agentkit_usage ledger"]
  run --> evals["agentkit-evals: citation checks + LLM judge"]
```

## Quickstart

```bash
cp .env.example .env        # fill in keys; .env is git-ignored, never commit it
make test                   # uv sync (pinned via constraints.txt) + offline tests
make lint                   # ruff, mypy, agentkit validate
```

## Run the sample apps

There are two sample agents. Run every command from the repo root (the CLIs read `.env` from there).

On macOS, if a `uv run` command fails with `cannot import name 'Settings'`, run `make sync` and retry:
macOS hides the `.pth` files that make the workspace packages importable, and a plain `uv run` re-syncs
and hides them again. After `make sync`, `uv run --no-sync ...` keeps them visible.

### Research agent (web research, no Docker)

Needs `FIREWORKS_API_KEY` (the agent and its fallback model) and `OPENAI_API_KEY` (model and tool
selection), or pass `--no-selection` to skip the OpenAI key. Web search uses the first of `PARALLEL_API_KEY`, `BRAVE_API_KEY`,
`TAVILY_API_KEY` that is set, falling back down that list and finally to keyless DuckDuckGo (unreliable).

```bash
cp .env.example .env              # fill in the keys
make sync
uv run --no-sync research "When should a team choose RAG over fine-tuning?" \
	--model fireworks-glm --out report.md
```

Progress (searches, fetches, delegations, run time) streams to stderr; the cited report lands in
`report.md`. To score it, add an Anthropic key (the judge) and run one golden case or the full gate:

```bash
uv run --no-sync research-eval --model fireworks-glm --case mcp --judge anthropic   # one case, about 2 min
uv run --no-sync research-eval --model fireworks-glm --judge anthropic \
	--dataset apps/research_agent/evals/golden.jsonl --gate apps/research_agent/evals/gates.yaml   # 25 cases, about 10 min
```

### Knowledge-base agent (answers from this repo's docs, needs Docker)

See [Knowledge-base agent](#knowledge-base-agent) below: stamp a tenant, load the docs once, then ask.

The agent is `apps/research_agent/agent.yaml`. `--model <registry entry>` switches provider (default
`fireworks-glm`, `accounts/fireworks/models/glm-5p3-flash`); `--tier` and `--no-selection` override the
other two keys; `--agent <file>` runs a different agent file. Keys come from the nearest `.env` (searched
upward from the current directory), and `.env` values win over shell exports. Both CLIs log progress to
stderr (resolved model, key names set, the Decisions selection, every delegation, search, fetch and file
write, run time); `-v` adds tool output and token counts, `-q` keeps warnings only. CLI and environment
reference: `docs/architecture.md` section 13.

The agent runs a standard middleware stack, placed in a fixed order whatever the YAML order: model fallback
to `fireworks-glm:strong`, two retries per model, a 60 model-call budget and 20 searches and 25 fetches for the orchestrator (each researcher delegation gets its own 30 calls and 25 tools; the report write is never budgeted), and PII
redaction (e-mail) and masking (card numbers), and `require_output`, which sends a run that stops before
saving `/report.md` back to the model (at most twice per run; the report must be written in that run). Details: `docs/architecture.md` sections 3.1 and 4.

## Test it manually

Run every command from the repo root: the CLIs read `.env` from the current directory, and `--dataset`
paths are relative to it. Every step except 1 costs real tokens.

### 1. Check the offline build

```bash
make test        # expect: 571 passed, 61 skipped (pg without a database, live evals), 8 deselected (live)
make lint        # expect: no ruff or mypy errors; agentkit validate: 0 error(s)
```

### 2. Check which keys you have

```bash
cp .env.example .env    # then fill in the keys you have
grep -oE '^[A-Z_]+=.' .env | cut -d= -f1    # lists the keys that are set, never their values
```

| What you run | Keys it needs |
|---|---|
| The shipped `apps/research_agent/agent.yaml` | `OPENAI_API_KEY` (it sets `selection: decisions`), the provider's own key, and `FIREWORKS_API_KEY` for any `--model` (its fallback model, `fireworks-glm:strong`, is built at load) |
| Any run with `--no-selection` | The provider's own key and `FIREWORKS_API_KEY` (the fallback model) |
| `research-eval` | The above, plus the key of the `--judge` entry (default `anthropic`) |

To try a provider without an OpenAI key, pass `--no-selection` (a Fireworks key is still needed): the agent sees every tool and stays on the
configured tier. To pin a search backend, set `tools: [{web_search: {backend: brave}}, fetch_url]` (or a list such as
`[parallel, brave]`, tried in order); a subagent's `tools` replace the parent's, so set it on each subagent too.

### 3. Check that each model answers

```bash
uv run pytest -m live packages/agentkit-core/tests/test_live_providers.py -v
```

One short call per registry entry; an entry whose key is missing is skipped, not failed.

### 4. Run one research question

```bash
uv run research "When should a team choose RAG over fine-tuning?" \
	--model fireworks-glm --out report.md
```

A good run gives a structured report with inline citations, each a URL the agent fetched. Common failures:

- `ConfigError` naming a key means that key is missing from `.env`.
- A Decisions API error does not stop the run. The middleware logs `selection unavailable for thread ...`
  and falls back to all tools and the default tier.
- `agent finished without writing /report.md` means the model never wrote the report. Try another
  `--model`, and note the model in `docs/phase0-results.md`.

### 5. Score an agent with the eval

```bash
uv run research-eval --model fireworks-glm --judge anthropic \
	--out eval_results.md
```

Runs the 10 questions in `apps/research_agent/evals/smoke.jsonl` and scores citations, groundedness and
completeness into `eval_results.md` and `eval_results.json`. Use `--dataset` with a smaller JSONL file for
a cheaper run, and `--judge` with an entry you have a key for (e.g. `openai`).

### 6. Run the full live suite

```bash
RESEARCH_LIVE_MODELS=fireworks-glm \
	uv run pytest -m live -v
```

A model whose keys are missing is skipped. Record each result in `docs/phase0-results.md`.

## Layout

| Path | Purpose |
|---|---|
| `packages/agentkit-core` | `Settings`, model registry (`models.yaml`), `get_model`, `PlatformContext`, `BuildContext` |
| `packages/agentkit-config` | declarative layer: `load_agent`, pools, `Library`, validation, flows (`load_flow`), `agentkit validate` |
| `packages/agentkit-deep` | `build_deep_agent` factory, skills mount, memory tiers, scripted test models |
| `packages/agentkit-middleware` | `TenantGuardMiddleware`, per-thread `SelectionMiddleware` + Decisions client, retry and circuit breaker |
| `packages/agentkit-tools` | `web_search` (Parallel, Brave, Tavily, DuckDuckGo; `auto` fallback chain by default) and `fetch_url` tool factories, `@platform_tool`, `tool_schemas.json` |
| `packages/agentkit-connectors` | connector specs (`env://` secrets), embeddings, pooled engines, `kb_search` / `sql_query`, `agentkit-kb` |
| `packages/agentkit-persistence` | encrypted Postgres checkpoints and store (`open_persistence`), `thread_lock`, `agentkit-prune` |
| `packages/agentkit-telemetry` | tenant-tagged OTel tracing with masking, `run_config`, `CostLedger` (`agentkit_usage`) |
| `packages/agentkit-evals` | dataset, citation metrics, openevals LLM judge, runner, gates, single-step evals, pytest plugin |
| `apps/research_agent` | `agent.yaml`, `research` and `research-eval` CLIs, the `research_with_review` flow |
| `apps/kb_agent` | pilot knowledge-base agent (`agent.yaml`) and its 20-case golden set |
| `libraries/` | versioned prompts (`prompts/<name>/v<x.y.z>.md`, `labels.yaml`), connectors, subagents (skills go in `libraries/skills/`) |
| `contracts/` | upstream contract suite (`-m contract`, `-m pg`) |
| `deploy/` | dev Postgres + collector (`compose.dev.yaml`), per-tenant stamp (`compose.yaml`, `tenants/`) |
| `scripts/` | tenant stamp and env helpers, Phase 0 exit check, offline `smoke.py` |

## Per-tenant deployments

Each tenant gets its own deployment: compose project `agentkit-<tenant>` with its own Postgres volume,
collector, ports, database password and AES key. Nothing is shared. Needs Docker.

```bash
make stamp TENANT=tenant-a        # writes deploy/tenants/tenant-a.env once (git-ignored), starts it, sets up the DB
scripts/tenant_env.sh tenant-a uv run research "your question" --tenant tenant-a --persist
make contract TENANT=tenant-a     # contract suite against the tenant's database
make phase0-exit                  # stamps tenant-a and tenant-b and proves they are separated
make unstamp TENANT=tenant-a      # stop it and delete its database (keeps the env file and key)
```

Langfuse forwarding and what stays plaintext at rest: `deploy/README.md` and `docs/architecture.md`
sections 9 to 11.

## Knowledge-base agent

`apps/kb_agent` answers questions from this repo's docs, stored in a tenant's Postgres (pgvector), with
cited answers. It reaches the data only through `kb_search` and the read-only `sql_query`. Needs
`FIREWORKS_API_KEY` (agent and `fireworks-nomic` embeddings) and Docker; details in `deploy/README.md`.

**1. Stamp a tenant and load the docs (once).** Setup and ingest use the tenant's admin login; nothing
else does.

```bash
make sync
make stamp TENANT=kb-demo         # prints the tenant's Postgres port, e.g. 127.0.0.1:55500
export KB_READER_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(18))')"
# schema kb and the read-only role kb_reader (the password is read from the variable, never printed)
scripts/tenant_env.sh kb-demo sh -c 'KB_DATABASE_URL="$DATABASE_URL" uv run --no-sync agentkit-kb setup \
	--connector kb-docs --reader-password-env KB_READER_PASSWORD'
# README + docs into kb.kb_docs (expect: ingest: <n> chunk(s) from 5 file(s) into kb.kb_docs)
scripts/tenant_env.sh kb-demo sh -c 'make kb-ingest KB_ADMIN_DATABASE_URL="$DATABASE_URL"'
```

Keep `KB_READER_PASSWORD` for later sessions; re-running `setup` resets it.

**2. Point the agent at the read-only login.** Both connectors log in as `kb_reader` at run time;
`sql_query` refuses an admin login.

```bash
PG_PORT=$(grep -o '127.0.0.1:[0-9]*' deploy/tenants/kb-demo.env | head -1 | cut -d: -f2)   # no password printed
export KB_READER_DATABASE_URL="postgresql://kb_reader:$KB_READER_PASSWORD@127.0.0.1:$PG_PORT/agentkit"
export KB_DATABASE_URL="$KB_READER_DATABASE_URL"
```

**3. Ask a question.**

```bash
scripts/tenant_env.sh kb-demo uv run --no-sync research "How do I give a tenant its own deployment?" \
	--agent apps/kb_agent/agent.yaml --model fireworks-glm --tenant kb-demo --out kb_report.md
```

A good run makes a few `kb_search` calls, writes `/report.md` and finishes in about 10-20 seconds;
`kb_report.md` holds the answer, cited to the docs' GitHub URLs under `## Sources`.

**4. Score it (optional, about 2 minutes, needs an Anthropic key for the judge).**

```bash
scripts/tenant_env.sh kb-demo uv run --no-sync research-eval --agent apps/kb_agent/agent.yaml \
	--model fireworks-glm --tenant kb-demo --dataset apps/kb_agent/evals/golden.jsonl --judge anthropic \
	--gate apps/kb_agent/evals/gates.yaml --out kb_eval.md
```

**5. Tear it down.**

```bash
make unstamp TENANT=kb-demo       # deletes the tenant's database (keeps deploy/tenants/kb-demo.env)
```

## Tools, prompts and agent evals

```bash
uv run agentkit tools list [--tenant T]          # name version side_effects classification owner tenants
uv run agentkit tools snapshot --check           # tool argument schemas vs tool_schemas.json (make tool-schemas writes it)
uv run agentkit-kb setup|ingest --help           # knowledge-base schema, read-only role, Markdown ingest
uv run pytest apps/research_agent/tests/test_eval_steps.py --agentkit-live   # dataset-driven evals in pytest
```

- Every pool tool carries `@platform_tool` metadata (owner, version, tenants, side effects,
  classification). An agent that names a tool not allowed for the deployment tenant fails
  `agentkit validate` and load.
- Prompts are versioned files (`libraries/prompts/<name>/v1.0.0.md`) referenced as `name`, `name@1`,
  `name@1.0.0` or `name@production` (`labels.yaml`), with `{{> other/prompt}}` fragments.
- Single-step evals score the agent's next tool call (`kind: single_step` cases,
  `apps/research_agent/evals/steps.jsonl`). The pytest plugin's `agentkit_eval` tests are skipped
  unless `--agentkit-live` is given.

Reference: `docs/architecture.md` sections 3.7, 6.1, 6.2 and 14.7 to 14.9.

## Extending

Add tools and middleware as entry-point factories `(ctx: BuildContext, **params)`, prompts and subagents
as files under `libraries/`, models as entries in `models.yaml`, and agents and flows as YAML. Check YAML
with `uv run agentkit validate <files>`. Step-by-step recipes: `docs/architecture.md` section 15.

## Status

Phase 0 (T1-T9) and Phase 0b are delivered and live-verified (`docs/phase0-results.md`). All six model ids
answer a live call; live agent runs use only `fireworks-glm`, whose eval baseline is completed 1.00,
citation validity 0.96, completeness 0.97 and groundedness 0.64. A two-turn persisted `fireworks-glm` run
against a stamped tenant resumed its thread, traced it and metered both turns, and `make phase0-exit`
passes offline.

Open items: P10 thread-to-user binding, P3 primitive state stored in plaintext, AES key rotation and
backup, never-pruned store items of `eval-<hex>` users, and a prune tenant filter if tenants ever share a
database (`docs/architecture.md` section 16). Verify changes end to end with the `verify-agentkit` skill
(`.claude/skills/verify-agentkit/`).

Phase 1 is complete (`docs/phase1-results.md`, `docs/phase1b-results.md`): the standard middleware
stack (fallback, retry, call and tool budgets, PII, `require_output`), eval gates, `@platform_tool` and
tenant tool policy, the versioned prompt registry, connectors with `kb_search` / `sql_query`, single-step
evals, the pytest plugin, and the knowledge-base pilot, whose 20-case gate passes. The research golden
baseline was re-recorded from an outlier run (297k mean tokens per case, median 185k), which loosened the
token ceiling to about 386k and the groundedness reference by 0.06 (`docs/phase1b-results.md`); Phase 2
gates a median or trimmed token metric instead. Gate a change against the committed golden baseline:

```bash
uv run research-eval --model fireworks-glm --dataset apps/research_agent/evals/golden.jsonl \
	--judge anthropic --gate apps/research_agent/evals/gates.yaml --out eval_results.md
```

Exit 0 is `gate: PASS`, 1 a regression (`gate: FAIL <metric>: ...` on stderr), 2 a missing, unreadable or mismatched baseline. It
runs 25 cases, 6 at a time by default (`--concurrency N`). While debugging, run a subset with
`--case <id>` or `--tag <tag>` (both repeatable; not allowed with `--gate`, which needs the full set).
The single-step set has its own gate (`--dataset apps/research_agent/evals/steps.jsonl --gate
apps/research_agent/evals/gates_steps.yaml`), and the kb agent's is in "Knowledge-base agent" above.

Design and plans: `docs/superpowers/specs/` and `docs/superpowers/plans/`; research and roadmap:
`reports/Reusable agent platform components.md`.
