# agentkit

A self-hosted agent platform built on DeepAgents, LangChain and LangGraph.
The samples run web research or answer questions from this repository's docs.

The app currently runs in the terminal. There is no HTTP backend service or web UI.

```text
Terminal command + agent.yaml
              |
              v
       Python agent runtime
              |
              +--> Model provider + search / knowledge-base tools
              |
              +--> Markdown report
              |
              +--> PostgreSQL (optional: saved conversations and usage)
              |
              +--> OpenTelemetry collector (optional: traces)
```

## Run the research sample

Run all commands from the repository root.

### Step 1: Install prerequisites

- Python 3.12, `uv`, and `make`.
- Docker Desktop, or Docker with Compose, for saved conversations and the knowledge-base sample.

### Step 2: Set up the environment

Copy the template only if you do not already have a `.env` file:

```bash
cp .env.example .env
make sync
```

Edit `.env` and set:

```dotenv
FIREWORKS_API_KEY=your-key
```

The commands below use `--no-selection`, so no OpenAI key is needed.
To enable model and tool selection, set `OPENAI_API_KEY` and omit `--no-selection`.

For more reliable web search, also set one of `PARALLEL_API_KEY`, `BRAVE_API_KEY`, or
`TAVILY_API_KEY`. Otherwise, search falls back to keyless DuckDuckGo, which may be blocked.
Model calls use provider credits.

### Step 3: Run a question

This first run does not need Docker:

```bash
uv run --no-sync research \
  "When should a team choose RAG over fine-tuning?" \
  --model fireworks-glm --no-selection --out report.md
```

Watch progress in the terminal, then open `report.md` for the cited answer.
The command exits when the report is complete.

## Add infrastructure and saved conversations

### Step 4: Start the infrastructure

Start Docker, then run:

```bash
make stamp TENANT=demo
```

This starts PostgreSQL with pgvector and an OpenTelemetry collector, initializes persistence,
and creates `deploy/tenants/demo.env` with credentials, ports and an AES key.
Keep this git-ignored file backed up; its key is needed to read encrypted data.

Leave tenant, database, AES and OTLP settings commented out in the root `.env`.
The tenant helper supplies them; root `.env` values would override them.

Check that the containers are running:

```bash
docker compose -p agentkit-demo --env-file deploy/tenants/demo.env -f deploy/compose.yaml ps
```

### Step 5: Run a saved conversation

```bash
scripts/tenant_env.sh demo uv run --no-sync research \
  "When should a team choose RAG over fine-tuning?" \
  --model fireworks-glm --no-selection --tenant demo \
  --persist --thread demo-chat --out report.md
```

Continue it using the same thread ID:

```bash
scripts/tenant_env.sh demo uv run --no-sync research \
  "Compare the maintenance costs of those approaches." \
  --model fireworks-glm --no-selection --tenant demo \
  --persist --thread demo-chat --out followup.md
```

Reports are saved locally. Conversation state and usage are saved in PostgreSQL.
Traces are written to `deploy/otel-out/demo/spans.jsonl`.

### Step 6: Stop or restart

Stop the containers and keep the database:

```bash
docker compose -p agentkit-demo --env-file deploy/tenants/demo.env -f deploy/compose.yaml stop
```

Restart with `make stamp TENANT=demo`.
To remove the containers and **delete the database**, run `make unstamp TENANT=demo`.

## Run the knowledge-base sample (optional)

Complete steps 1 and 2 first. This sample needs Docker and `FIREWORKS_API_KEY`.

### Step 1: Create a tenant and load the docs

```bash
make stamp TENANT=kb-demo
export KB_READER_PASSWORD="$(python3 -c 'import secrets; print(secrets.token_urlsafe(18))')"

scripts/tenant_env.sh kb-demo sh -c 'KB_DATABASE_URL="$DATABASE_URL" uv run --no-sync agentkit-kb setup \
  --connector kb-docs --reader-password-env KB_READER_PASSWORD'

scripts/tenant_env.sh kb-demo sh -c 'make kb-ingest KB_ADMIN_DATABASE_URL="$DATABASE_URL"'
```

Keep `KB_READER_PASSWORD` securely for later sessions. Re-running setup resets the reader password.

### Step 2: Configure the read-only connection

In the same terminal:

```bash
PG_PORT=$(grep '^AGENTKIT_PG_PORT=' deploy/tenants/kb-demo.env | cut -d= -f2)
export KB_READER_DATABASE_URL="postgresql://kb_reader:$KB_READER_PASSWORD@127.0.0.1:$PG_PORT/agentkit"
export KB_DATABASE_URL="$KB_READER_DATABASE_URL"
```

Both agent connectors use the read-only login. The admin login is only for setup and ingestion.
Leave these connection variables commented out in the root `.env` when using the exports above.

### Step 3: Ask a question

```bash
scripts/tenant_env.sh kb-demo uv run --no-sync research \
  "How do I give a tenant its own deployment?" \
  --agent apps/kb_agent/agent.yaml --model fireworks-glm \
  --tenant kb-demo --out kb_report.md
```

Open `kb_report.md` for the answer and its documentation citations.
Use the stop command from step 6 with `kb-demo` in place of `demo` to keep the database,
or `make unstamp TENANT=kb-demo` to delete it.

## Checks and troubleshooting

Run the offline checks:

```bash
make test
make lint
```

- Missing-key `ConfigError`: set the named key in `.env`.
- macOS import error such as `cannot import name 'Settings'`: run `make sync`, then retry with
  `uv run --no-sync`. This preserves the workspace package imports.
- Agent exits without writing `/report.md`: retry the question or choose another registry model
  with `--model`. The configured Fireworks fallback still requires `FIREWORKS_API_KEY`.

## Showcase

A one-page, interactive view of the platform: **one chassis, many agents**. It shows how a new agent
is a short YAML file of parts from the shared library, and how the platform wraps every agent in
guardrails the YAML cannot remove. Everything on it is generated from this repo, so it never drifts.

### Open it

From the repository root, after Step 2 above (`make sync`):

```bash
make showcase              # serves http://localhost:8766 and opens your browser
make showcase PORT=9000    # use another port if 8766 is taken
```

Stop it with `Ctrl+C`. The page needs no API keys, Docker, database or network: it runs nothing,
it only shows what the repo contains plus one recorded run.

### Present it

Press `p` (or open `http://localhost:8766/?present`) for presenter mode. Use `→` / `←` (or
PageDown / PageUp) to step through the five views; each shows a one-line takeaway banner. Press
`p` again to leave. **Theme** toggles light and dark.

| View | What it shows | Try this |
|---|---|---|
| 1. Recipe | `research_agent` and `kb_agent` side by side; shaded rows come from the platform, the rest from each YAML | Click an agent name to open its assembly |
| 2. Assembly | An `agent.yaml` next to the harness it builds: guards outermost, then middleware in canonical order, model, tools, subagents | Hover a YAML line to light up its part, or a part to find its line |
| 3. Bench | Clone a shipped agent and toggle tools, subagents and middleware; the YAML and rule hints update live | Set the tenant policy to `read` and watch the `web_search` hint appear |
| 4. Replay | A real steered `fireworks-glm` run (235 events): the tenant guard, an email masked as `[REDACTED_EMAIL]`, the `web_search` limit tripping, the report written | Press Play or Space, or use "Jump to" |
| 5. Positioning | agentkit against LangChain's five company-harness components and peer agent builders, including what is not built yet | Open the peer links |

The Bench only writes YAML. To run what you built, save it as `apps/my_agent/agent.yaml` and use the
commands it shows (`uv run agentkit validate …`, then `uv run research --agent …`).

### Share it

```bash
make showcase-snapshot     # writes evidence/showcase/showcase.html
```

That is one self-contained HTML file that works offline (double-click it or email it). It is
gitignored and is checked on every build to contain no local paths, key names or internal
open items. The live `make showcase` page also shows a team-only "This machine" panel listing which
API key names are set (never their values); the snapshot leaves it out.

### Update it

- The page rebuilds from the repo each time, so new agents in `apps/*/agent.yaml`, tools, middleware
  and prompts appear automatically.
- Narrative copy and the peer comparison live in `scripts/showcase/positioning.yaml`.
- The replay reads `evidence/showcase/replay.json`; to record a new run, follow
  `evidence/showcase/README.md`.
- Tests: `uv run pytest scripts -q`.

`make catalog` is a different page: a full inventory of everything installed, for the team.

Spec: `docs/superpowers/specs/2026-11-07-agentkit-showcase-design.md`.

## Reference

- [Architecture and CLI reference](docs/architecture.md)
- [Platform catalog (visual)](scripts/platform_catalog.py) — `make catalog` serves a dashboard of
  everything the platform provides (tools, middleware, models, prompts, skills, subagents,
  connectors, apps, evals, memory tiers, seams), read live from the installed workspace.
- [Deployment, database setup and tracing](deploy/README.md)
- [Research agent configuration](apps/research_agent/agent.yaml)
- [Knowledge-base agent configuration](apps/kb_agent/agent.yaml)
- [Phase 0 results](docs/phase0-results.md), [Phase 1 results](docs/phase1-results.md),
  [Phase 1b results](docs/phase1b-results.md)

Shared Python packages live in `packages/`; prompts, tools' connector definitions and subagents
live in `libraries/`. See the architecture reference for extension recipes and evaluation commands.
