# agentkit Phase 1 (rest): tool governance, prompt registry, connectors, single-step evals, pytest plugin

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the roadmap's Phase 1 ("Factory v0 + eval core"). This means governed tools via `@platform_tool`, a versioned git prompt registry, Postgres/pgvector connectors behind curated tools, single-step and trajectory evals, and a pytest plugin. It is proven by a second, knowledge-base pilot agent gated by a 20-case golden set.

**Architecture:**
- Everything plugs into the existing seams: entry-point pools (`agentkit.tools`), the library roots (`libraries/prompts`, `libraries/connectors`), `load_agent` → `resolve` → `build_deep_agent`, and `agentkit-evals`.
- One new package, `agentkit-connectors`, owns connector specs, secrets, embeddings and pooled engines. Agents reach it only through two curated tools, `kb_search` and `sql_query`.
- Single-step evals stream the agent and stop at the first top-level tool call, so no tool runs and no checkpointer is needed.

**Tech Stack:** Python 3.12, uv workspace, DeepAgents 0.7.32, langchain 1.4.7, LangGraph, openevals 0.2.2, langchain-postgres (new, pinned in Task 4), langchain-fireworks 1.7.1 embeddings, Postgres 16 + pgvector (`pgvector/pgvector:pg16`, already the stamp's image).

**Spec:** There is no separate design doc. The plan argues from `reports/Reusable agent platform components.md`:
- "Tools library" (lines 264-311)
- "Prompt library" (378-389)
- "Connectors" (413-415)
- "Evals gate every component change" (417-441)
- the Phase 1 roadmap row (616)

and from `docs/architecture.md` section 16 (open items). Where the report is silent, the decisions below are this plan's calls and are marked provisional.

## Global Constraints

- **Live runs:** live tests of sample agents use **fireworks-glm only**. The judge stays `--judge anthropic` (strong tier, `claude-opus-5-5`). Embeddings in live tests use the Fireworks entry.
- **Public repo:** no tenant client names; use "tenant" wording. Never commit `.env`. Keep keys out of cassettes, fixtures and evidence.
- **Pins:** every new dependency is pinned in `constraints.txt`. Python 3.12, uv workspace.
- **Running tests on macOS:** run `make sync` first, because macOS hides `.pth` files. Then use `uv run --no-sync pytest` / `ruff` / `mypy`, since `uv run` without `--no-sync` re-hides them.
- **Errors:**
  - Load-time spec problems are `SpecError`s (exit 2).
  - Missing keys and connector secrets are `ConfigError` (exit 2), and the message names the variable, never its value.
  - Tools return `ERROR: ...` text instead of raising, which is the house pattern.
- **Commits:** every commit ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Don't push or merge without asking.
- **Unchanged contracts:**
  - Existing agent YAML keeps working unchanged.
  - A bare prompt name such as `prompt: research/orchestrator` stays valid.
  - The shipped research agent's golden gate must still pass at the end (Task 9).

## Decisions (provisional; this plan's calls)

1. **`@platform_tool` decorates pool *factories*, not built tools.** The pool registers factories (`(ctx, **params) -> BaseTool`), so putting metadata on the factory lets `agentkit validate` check tenant policy without building tools or needing keys. `resolve` copies the metadata onto `tool.metadata["agentkit"]` at build.
2. **Tenant policy is enforced at build and validate time against `settings.deployment_tenant`.** It is not enforced per call: one deployment serves one tenant, and `TenantGuardMiddleware` already rejects any run whose `context.tenant` differs. `tenants=None` means every tenant.
3. **`side_effects` and `classification` are recorded and listed, not enforced yet.** No shipped tool writes. Turning on HITL for `side_effects="write"` is a Phase 2 item.
4. **Tool schema snapshot.** `packages/agentkit-tools/tool_schemas.json` holds `{name: {version, schema}}`. A test fails when a schema changes and the major version doesn't.
5. **Prompts.**
   - Layout: `prompts/<name>/v<x.y.z>.md` (front matter: `owner`, `description`, optional `eval_suite`), next to the existing flat `prompts/<name>.md`. A flat file is an unversioned prompt with version `0.0.0`; the name can't have both forms.
   - References: `name` (highest version), `name@1` (highest 1.x.y), `name@1.2.0` (exact), `name@<label>` (from `prompts/labels.yaml`).
   - Fragments: `{{> other/name}}` includes another prompt (highest version), at most 5 levels deep. A cycle or a missing fragment is a SpecError.
   - Templating: no Jinja. Today's `{{agent_name}}`/`{{date}}` substitution is unchanged.
6. **Connectors.**
   - Spec files: `libraries/connectors/<name>.yaml`.
   - Secrets: `dsn` is a secret ref. Only `env://VAR` is implemented, behind a `SecretsProvider` protocol, so Vault or a cloud secret manager can be added later.
   - Pooling: one cached `PGEngine`/pool per DSN per process.
   - Embeddings: a new `embeddings:` section in `models.yaml`, resolved by `get_embeddings(entry, settings)`.
7. **`sql_query` safety.** These are layered, and the role is the real wall:
   - a dedicated read-only role (`kb_reader`, created by `agentkit-kb setup`, SELECT on schema `kb` only)
   - `SET TRANSACTION READ ONLY`
   - `search_path` limited to the connector's `schemas`
   - a single statement only (anything after a `;` is refused)
   - `statement_timeout`
   - `max_rows`

   Raw SQL toolkits are never exposed.
8. **Single-step evals stream and stop.** Stream with `stream_mode="updates"` and stop at the first top-level model update that carries tool calls. No tool executes, no checkpointer is needed, and no `interrupt_before` is used. A case may give a message prefix to set up a later decision point.
9. **The pytest plugin ships in `agentkit-evals` via a `pytest11` entry point.** Live eval tests are skipped unless `--agentkit-live` is given. Not in scope: VCR (cassettes of LLM calls are a key-leak risk in a public repo), judge caching, and judge calibration (a Phase 2 roadmap item).
10. **The pilot is a knowledge-base agent over this repo's own docs (`apps/kb_agent`).**
    - Chunks carry the doc's public GitHub URL as their source, so the existing citation metrics work unchanged.
    - It runs through `research-eval --agent apps/kb_agent/agent.yaml`, with no new eval CLI.
    - HITL and production rollout are deployment work, outside this plan.

## Review Focus

1. **A tool not allowed for the deployment tenant.** An agent YAML references a tool whose `tenants` excludes `AGENTKIT_TENANT`. `agentkit validate` and `load_agent` fail with a SpecError naming the tool and the tenant, before any key check. *Pinned in Task 2.*
2. **Hostile SQL.** `sql_query` receives a write (`insert`, `with d as (delete ...) select`), a second statement after `;`, `set role`, or a query longer than the timeout. Each returns `ERROR: ...` and no write happens. *Pinned in Task 5 (pg-marked tests).*
3. **A broken prompt reference.**
   - A fragment cycle (`a` includes `b` includes `a`) or a missing fragment is a SpecError at validate, never a `RecursionError` at run time.
   - An unknown `@version` or `@label` also fails, and the error lists the versions that exist.
   *Pinned in Task 3.*
4. **A single-step case where the model doesn't call a tool.**
   - The model answers in text with no tool call: the case scores `step_pass = 0` with reason "no tool call", not an exception.
   - The model's first move is to delegate (`task`): that is the top-level call that gets scored.
   - Calls inside subagents are never scored.
   *Pinned in Task 7.*
5. **A missing secret or a changed embedding size.**
   - `env://KB_DATABASE_URL` is unset: ConfigError names `KB_DATABASE_URL`, and no DSN appears in any log line.
   - The KB was ingested with a different embedding dimension than the connector's entry: `kb_search` returns `ERROR: embedding dimension ...`, not a driver traceback.
   *Pinned in Tasks 4 and 5.*

---

### Task 1: `@platform_tool` and the tool contract

**Files:**
- Create: `packages/agentkit-tools/src/agentkit_tools/platform.py`
- Modify: `packages/agentkit-tools/src/agentkit_tools/factories.py`, `langchain_tools.py`, `__init__.py`
- Test: `packages/agentkit-tools/tests/test_platform_tool.py`

**Interfaces:**
- Produces:
  - `ToolMeta` (frozen pydantic), with fields: `owner: str`, `version: str` (semver), `tenants: frozenset[str] | None = None`, `side_effects: Literal["read","write","external"]`, `identity: Literal["service","user"] = "service"`, `classification: Literal["public","internal","confidential"] = "internal"`, `examples: tuple[dict, ...] = ()`
  - `platform_tool(**meta) -> Callable[[F], F]`, which sets `factory.__agentkit_tool__ = ToolMeta(...)`
  - `tool_meta(factory) -> ToolMeta | None`
  - `check_tool_contract(tool: BaseTool) -> list[str]`, which returns the problems (empty list if none)

- [ ] **Step 1: Write the failing tests.** Each of these must hold:
  - `ToolMeta(version="1.x")` raises a pydantic error.
  - `@platform_tool(owner="platform", version="1.0.0", side_effects="read")` on a factory → `tool_meta(f).owner == "platform"`, and the factory still builds.
  - `check_tool_contract` reports:
    - `"empty description"` for a tool without a docstring;
    - `"argument 'q' has no description"` for an `args_schema` field without one;
    - `"argument 'tenant' must come from runtime context"` for any of the args `tenant`, `tenant_id`, `user`, `user_id`, `thread_id`.
  - The built `web_search` and `fetch_url` pass `check_tool_contract` with `[]`.
  - `tool_meta(web_search).version == "1.0.0"` and `side_effects == "external"`; the same holds for `fetch_url`.
- [ ] **Step 2: Run, expect FAIL.** `uv run --no-sync pytest packages/agentkit-tools/tests/test_platform_tool.py -v`
- [ ] **Step 3: Implement.**
  - Give `web_search` and `fetch_url` pydantic `args_schema`s with a `Field(description=...)` for each argument: `query`, `k` (1-10, default 5), and `url`.
  - Write their docstrings in the report's "when to use / when not to" style.
  - Decorate both factories: `owner="platform"`, `version="1.0.0"`, `side_effects="external"`, `classification="public"`.
- [ ] **Step 4: Run the package tests, expect PASS.** Then run the full suite, because tool descriptions changed and snapshots may need regenerating.
- [ ] **Step 5: Commit** `feat(tools): @platform_tool metadata and the tool contract`

### Task 2: Tenant policy, `agentkit tools`, schema snapshot

**Files:**
- Modify: `packages/agentkit-config/src/agentkit_config/resolve.py` (`_tools`), `validate.py`, `cli.py`
- Create: `packages/agentkit-tools/tool_schemas.json`, `packages/agentkit-tools/tests/test_tool_schemas.py`
- Test: `packages/agentkit-config/tests/test_tool_policy.py`

**Interfaces:**
- Consumes: `tool_meta`, `check_tool_contract` from Task 1.
- Produces:
  - `resolve` sets `tool.metadata["agentkit"] = meta.model_dump(mode="json")` on every tool built from a decorated factory.
  - CLI `agentkit tools list [--tenant T]` prints one line per pool tool: `name version side_effects classification owner tenants`.
  - CLI `agentkit tools snapshot [--check]` writes, or with `--check` compares against, `tool_schemas.json`.

- [ ] **Step 1: Write the failing tests.**
  - A pool tool with `tenants={"tenant-a"}`, used by an agent YAML under `deployment_tenant="tenant-b"`:
    - `validate` returns a SpecError at `tools[0]` reading `tool 'x' is not available to tenant 'tenant-b'`;
    - `load_agent` raises `SpecErrors` before `get_model` is called (assert with a `get_model` spy).
  - The same tool under `tenant-a` loads, and the built tool's `metadata["agentkit"]["owner"]` is set.
  - An undecorated pool tool gives a validate **warning** `tool 'x' has no @platform_tool metadata`.
  - `tools list --tenant tenant-b` omits the restricted tool.
- [ ] **Step 2: Write the failing snapshot test.** `test_tool_schemas.py` builds every pool tool with a fake `Settings` and compares `tool.tool_call_schema.model_json_schema()` to `tool_schemas.json`.
  - If the schema differs and the major version is unchanged, it fails with `schema of 'x' changed; bump its major version (1.0.0 -> 2.0.0) and run agentkit tools snapshot`.
  - If the version changed and the schema matches, it fails with `run agentkit tools snapshot`.
  - It also asserts `check_tool_contract(tool) == []` for every pool tool.
- [ ] **Step 3: Implement.** Then generate `tool_schemas.json` with `uv run --no-sync agentkit tools snapshot` and add `make tool-schemas` to the Makefile.
- [ ] **Step 4: Run, expect PASS.** Run the full suite and `make lint` (`agentkit validate` must stay at 0 errors).
- [ ] **Step 5: Commit** `feat(config): tenant tool policy, agentkit tools list/snapshot`

### Task 3: Versioned prompt registry with labels and fragments

**Files:**
- Modify: `packages/agentkit-config/src/agentkit_config/pools/prompts.py`, `resolve.py`, `validate.py`; `packages/agentkit-deep/src/agentkit_deep/factory.py`
- Move: `libraries/prompts/research/orchestrator.md` → `libraries/prompts/research/orchestrator/v1.0.0.md`, and the same for `researcher.md`. Use `git mv`, add front matter `owner: platform`, and leave the body byte-identical.
- Create: `libraries/prompts/labels.yaml` with `research/orchestrator: {production: 1.0.0}` and `research/researcher: {production: 1.0.0}`
- Test: `packages/agentkit-config/tests/test_prompt_registry.py`

**Interfaces:**
- Produces:
  - `Prompt` gains `version: str` (`"0.0.0"` for flat files), `owner: str | None` and `eval_suite: str | None`.
  - `PromptRegistry.get_ref(ref: str, *, file: str, path: str) -> Prompt` parses `name[@selector]`.
  - `compose(prompt, lib) -> str` expands `{{> name}}`.
  - `build_deep_agent` adds `PROMPT_ID_KEY = "prompt_id"` (value `name@version`) to the agent config metadata, next to `prompt_hash`.
  - The telemetry `run_config` copies `prompt_id` into run metadata the same way it does `prompt_hash`.

- [ ] **Step 1: Write the failing tests.** Use a tmp library with `p/v1.0.0.md`, `p/v1.2.0.md`, `p/v2.0.0.md`, `labels.yaml {p: {production: 1.2.0}}`, and fragments:
  - `get_ref("p")` returns version `2.0.0`.
  - `"p@1"` returns `1.2.0`, `"p@1.0.0"` returns `1.0.0`, and `"p@production"` returns `1.2.0`.
  - `"p@3"` raises a SpecError whose message contains `available: 1.0.0, 1.2.0, 2.0.0`.
  - `"p@staging"` raises a SpecError naming the label.
  - A flat file `q.md` resolves for `"q"` at version `0.0.0`.
  - Both `q.md` and `q/v1.0.0.md` present gives a SpecError `prompt 'q' is both flat and versioned`.
  - `{{> frag/a}}` expands. `a`→`b`→`a` gives a SpecError naming the cycle `a -> b -> a`. A missing fragment gives a SpecError. Nesting deeper than 5 gives a SpecError.
  - A label pointing to a missing version gives a SpecError from `validate`.
  - `prompt_hash` of the shipped research agent equals the hash before the move (byte-identical body).
  - A traced run's metadata includes `prompt_id == "research/orchestrator@1.0.0"`.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement.** Agent YAML `prompt:` and subagent `prompt:` accept any ref. `validate` resolves every ref, label and fragment.
- [ ] **Step 4: Run the full suite, expect PASS.** Snapshot tests that pin the shipped prompt text must not change.
- [ ] **Step 5: Commit** `feat(prompts): versioned prompt registry with labels and fragments`

### Task 4: `agentkit-connectors`: specs, secrets, embeddings, pooled engines

**Files:**
- Create package: `packages/agentkit-connectors/`, with `pyproject.toml` and `src/agentkit_connectors/{__init__,spec,secrets,embeddings,engines}.py`; add it to the workspace.
- Modify: `packages/agentkit-core/src/agentkit_core/models.yaml` and its registry loader (new `embeddings:` section), `constraints.txt`
- Test: `packages/agentkit-connectors/tests/test_connectors.py`

**Interfaces:**
- Produces:
  - `ConnectorSpec`: a discriminated union on `kind`.
    - `PgVectorSpec`: `kind: "pgvector"`, `dsn: str`, `collection: str`, `embeddings: str`
    - `PostgresSpec`: `kind: "postgres"`, `dsn: str`, `schemas: list[str]` (min 1), `statement_timeout_ms: int = 5000`, `max_rows: int = 200`
  - `load_connector(name, roots) -> ConnectorSpec`
  - `SecretsProvider` protocol: `resolve(ref: str) -> str`
  - `EnvSecrets`: `env://VAR` only; a missing variable raises `ConfigError("connector secret env://VAR is not set")`; any other scheme raises `ConfigError("unsupported secret ref scheme ...")`.
  - `get_embeddings(entry: str, settings) -> Embeddings` and `embedding_dimensions(entry) -> int`
  - `get_engine(dsn: str) -> PGEngine`, cached per DSN with `functools.cache` keyed on the DSN string.
  - `get_vectorstore(spec: PgVectorSpec, settings) -> PGVectorStore`

- [ ] **Step 1: Pin the dependency.** `uv add --package agentkit-connectors langchain-postgres`, then pin the resolved version in `constraints.txt`. Confirm `uv lock` keeps `langchain-core` and `langgraph` at their current pins. If it can't, stop and report the conflict; don't relax the pins.
- [ ] **Step 2: Add the embeddings entries.** In `models.yaml`:
  - `fireworks-nomic` (`provider: fireworks`, `model: nomic-ai/nomic-embed-text-v1.5`, `dimensions: 768`)
  - `openai-small` (`provider: openai`, `model: text-embedding-3-small`, `dimensions: 1536`)

  The Fireworks model id is unverified. Verify it with one live `embed_query` call in this task and record the result in the report. If it's wrong, use the id Fireworks lists, and log the change.
- [ ] **Step 3: Write the failing tests.**
  - The spec parses both kinds. An unknown `kind` fails. `schemas: []` fails.
  - `EnvSecrets` resolves a set variable. When it's unset, the error message names the variable and the test asserts the value never appears in `caplog`.
  - `get_engine` returns the same object for the same DSN and a different one for a different DSN, with no connection opened (engine creation is lazy; assert with a monkeypatched factory).
  - `get_embeddings("fireworks-nomic", settings_without_key)` raises ConfigError naming `FIREWORKS_API_KEY`.
  - An unknown embeddings entry gives a ConfigError listing the known entries.
  - Live, marked `live`: one `embed_query` returns 768 floats.
- [ ] **Step 4: Implement, then run, expect PASS.**
- [ ] **Step 5: Commit** `feat(connectors): connector specs, env secrets, embeddings registry, pooled engines`

### Task 5: Curated tools `kb_search` and `sql_query`, plus the `agentkit-kb` CLI

**Files:**
- Create: `packages/agentkit-connectors/src/agentkit_connectors/{tools,kb_cli}.py`
- Modify: the connectors `pyproject.toml` (entry points `agentkit.tools`: `kb_search`, `sql_query`; script `agentkit-kb`), `deploy/README.md`
- Test: `packages/agentkit-connectors/tests/test_tools.py` (offline) and `test_pg_tools.py` (`pg` marker, using the existing pg test fixtures and DB URL convention)

**Interfaces:**
- Consumes: Task 1 `platform_tool`; Task 4 specs, engines and embeddings.
- Produces:
  - `kb_search(ctx, *, connector: str, k: int = 5) -> BaseTool`
    - Tool name `kb_search`. Args: `query` (described), `k` (1-10).
    - Each hit renders as `[n] <title>\n<source_url>\n<chunk text>`.
    - Decorated with `version="1.0.0"`, `side_effects="read"`, `classification="internal"`.
  - `sql_query(ctx, *, connector: str) -> BaseTool`
    - Tool name `sql_query`. Arg: `sql` (described).
    - Returns a Markdown table of at most `max_rows` rows, plus `[truncated at N rows]` when it cuts rows off.
    - `side_effects="read"`, `classification="confidential"`.
  - CLI:
    - `agentkit-kb setup --connector <pg> --reader-password-env KB_READER_PASSWORD` creates schema `kb` and role `kb_reader` (LOGIN, SELECT on `kb` only, default privileges), idempotently.
    - `agentkit-kb ingest --connector <pgvector> <path>... --source-base <url>` splits Markdown on headings, then into ~1,500-character chunks, and upserts them with metadata `{title, source_url}`. `source_url = <source-base>/<path relative to repo root>`.

- [ ] **Step 1: Write the failing offline tests.**
  - The connector name resolves through the library roots. An unknown connector is a SpecError at validate (validate checks `params.connector` for these two tools).
  - The `kb_search` output format uses a fake vector store.
  - `sql_query` refuses `select 1; select 2` with `ERROR: one statement only` before touching the DB.
  - Both tools pass `check_tool_contract` and the Task 2 schema snapshot (regenerate it).
- [ ] **Step 2: Write the failing pg tests.** They need the stamped DB and are skipped without one, like the existing pg tests.
  - `setup` is idempotent (run it twice).
  - Ingest 3 small docs, then `kb_search` returns the expected doc first.
  - As `kb_reader`, each of these returns `ERROR:` and leaves the table count unchanged: `insert into kb.t ...`, `with d as (delete from kb.t returning *) select * from d`, `set role postgres`, `select pg_sleep(10)` (with a 1,000 ms timeout).
  - `select * from public.agentkit_usage` returns `ERROR:` (not in search_path, and no grant).
  - A dimension mismatch (ingest with a fake 768-dim embedder, query with a 1536-dim one) returns `ERROR: embedding dimension ...`.
- [ ] **Step 3: Implement.** Each `sql_query` call runs `BEGIN READ ONLY; SET LOCAL statement_timeout = ...; SET LOCAL search_path = <schemas>`, then the statement, then `ROLLBACK`.
- [ ] **Step 4: Run the offline tests, plus the pg tests against a stamped throwaway tenant (`make stamp TENANT=kbtest`, cleaned up afterwards). Expect PASS.**
- [ ] **Step 5: Commit** `feat(connectors): kb_search and sql_query curated tools, agentkit-kb setup/ingest`

### Task 6: Pilot `kb_agent` and its 20-case golden set

**Files:**
- Create:
  - `apps/kb_agent/agent.yaml`
  - `libraries/prompts/kb/answerer/v1.0.0.md`
  - `libraries/connectors/kb-docs.yaml` (pgvector, `dsn: env://KB_DATABASE_URL`, `collection: kb_docs`, `embeddings: fireworks-nomic`)
  - `libraries/connectors/kb-sql.yaml` (postgres, `dsn: env://KB_READER_DATABASE_URL`, `schemas: [kb]`)
  - `apps/kb_agent/evals/golden.jsonl`, `gates.yaml`
  - `apps/kb_agent/tests/test_kb_agent.py`
- Modify: `.env.example` (`KB_DATABASE_URL`, `KB_READER_DATABASE_URL`, `KB_READER_PASSWORD`), `Makefile` (`kb-ingest` target)

**Interfaces:**
- Consumes: Tasks 3-5.
- The agent:
  - `model: fireworks-glm`, `selection` off, `tools: [{kb_search: {connector: kb-docs}}, {sql_query: {connector: kb-sql}}]`.
  - The Phase 1 standard middleware stack (copy the research agent's list, with `call_limit 30` and tool budgets `kb_search 15`, `sql_query 5`).
  - `output: /report.md` and `require_output`.
  - The prompt says to answer only from `kb_search` results, cite their URLs, and end with a `## Sources` heading.
- The corpus is `README.md`, `docs/architecture.md` and `docs/phase*-results.md`, ingested with `--source-base https://github.com/cwijayasundara/deep_agents_fw_v1.0/blob/main`.

- [ ] **Step 1: Write the failing offline test.** `load_agent("apps/kb_agent/agent.yaml")` with fake keys and env DSNs:
  - it builds;
  - the tool names are `{kb_search, sql_query}` plus the deepagents built-ins;
  - the stack order matches the research agent;
  - `agentkit validate` reports 0 errors.
- [ ] **Step 2: Write the 20 golden cases** about agentkit itself, each answerable from the corpus:
  - `must_cover` with 2-3 facts each;
  - `expect_tools: ["kb_search"]`;
  - tags `definition` / `how-to` / `config` / `history`.

  Run `load_dataset` to check them.
- [ ] **Step 3: Write `gates.yaml`** with the research agent's metric set. Floors are provisional (citation validity 0.85, completeness 0.80, groundedness 0.60, completed 0.95, tool_recall 0.95) and get re-set from the live baseline in Task 9.
- [ ] **Step 4: Run, expect PASS. Commit** `feat(kb_agent): pilot knowledge-base agent and golden set`

### Task 7: Single-step and trajectory evals

**Files:**
- Modify: `packages/agentkit-evals/src/agentkit_evals/{dataset,metrics,runner}.py`, `apps/research_agent/src/research_agent/eval_cli.py`
- Create: `packages/agentkit-evals/src/agentkit_evals/single_step.py`, `apps/research_agent/evals/steps.jsonl`, `apps/research_agent/evals/gates_steps.yaml`
- Test: `packages/agentkit-evals/tests/test_single_step.py`, `test_evals.py`

**Interfaces:**
- Produces:
  - `EvalCase` gains:
    - `kind: Literal["full","single_step"] = "full"`
    - `messages: list[dict] = []` (a prefix of `{role, content}` turns, used before `question`)
    - `expect_call: ExpectCall | None`, where `ExpectCall = {name: str, args: dict[str, str] = {}}` and each arg value is a regex matched with `re.search` against `str(arg)`
    - `ideal_tool_calls: int | None`
  - `single_step(graph, case, *, config, context) -> StepResult(name: str | None, args: dict, text: str)`
  - Metrics:
    - `step_pass(case, step) -> float`: 1.0 only when the name matches and every arg regex matches.
    - `tool_call_ratio(case, calls) -> float | None`: `len(calls) / ideal_tool_calls`.
  - `CaseResult` gains `reason: str | None` and `report: str` (the full report, saved in the summary JSON; this closes the Phase 1 "can't inspect a bad case" gap).
  - `research-eval` handles a dataset that mixes both kinds. Single-step cases skip the judge and the citation metrics.

- [ ] **Step 1: Write the failing tests,** with a scripted fake model graph built through `create_agent`:
  - The first top-level model update with `tool_calls` stops the stream, and the test asserts the fake tool was **not** executed.
  - Name and arg regex match → `step_pass` 1.0. A wrong name → 0.0 with `reason="called fetch_url, expected web_search"`.
  - A text-only reply → 0.0 with `reason="no tool call"`.
  - The `messages` prefix reaches the model (assert on the fake model's received messages).
  - A tool call inside a subagent namespace is ignored.
  - `tool_call_ratio` gives 1.5 for 6 calls with ideal 4, and `None` without an ideal.
  - Existing full-run cases score exactly as before (regression test against a fixed fake run).
- [ ] **Step 2: Implement, then run, expect PASS.**
- [ ] **Step 3: Write `steps.jsonl`,** 12 research-agent decision points, for example:
  - a first turn on a factual question expects `web_search` or `task`;
  - after a search result in `messages`, expect `fetch_url` with a URL from it;
  - after enough sources, expect `write_file` with `file_path` `^/report\.md$`.

  Also write `gates_steps.yaml` (`step_pass` min 0.80, `completed` min 1.0, baseline `apps/research_agent/evals/baseline_steps.json`).
- [ ] **Step 4: Run the full suite. Commit** `feat(evals): single-step evals, tool_call_ratio, per-case reports in the summary`

### Task 8: pytest plugin

**Files:**
- Create: `packages/agentkit-evals/src/agentkit_evals/pytest_plugin.py`; `apps/research_agent/tests/test_eval_steps.py`
- Modify: `packages/agentkit-evals/pyproject.toml` (`[project.entry-points.pytest11] agentkit = "agentkit_evals.pytest_plugin"`, plus a dependency on `agentkit-config`), root `pyproject.toml` (register markers)
- Test: `packages/agentkit-evals/tests/test_pytest_plugin.py`, using `pytester`

**Interfaces:**
- Produces:
  - Options:
    - `--agentkit-live` (otherwise every `agentkit_eval` test is skipped with `live eval; pass --agentkit-live`)
    - `--agentkit-model ENTRY` (default `fireworks-glm`)
  - Marker `@pytest.mark.agentkit_eval(dataset="path.jsonl", agent="path/agent.yaml", kind="single_step"|"full")`. The test is parametrized with one `case` per dataset line, with ids equal to the case ids.
  - Fixture `agentkit_run(case) -> CaseResult`. It loads the agent with the `--agentkit-model` override and a fresh thread, runs `single_step` or a full run plus judge, and returns the scored result.
  - Helper `assert_case(result, **floors)`, which fails with the case id, the scores and the `reason`.

- [ ] **Step 1: Write the failing `pytester` tests.**
  - Without `--agentkit-live`, a marked test is skipped and reports the reason.
  - With it, a fake agent entry point gives one test per case, and the ids match the case ids.
  - A failing `assert_case` message contains the case id and the reason.
  - Unmarked tests are unaffected.
- [ ] **Step 2: Implement, then run, expect PASS.**
- [ ] **Step 3: Write `apps/research_agent/tests/test_eval_steps.py`,** one test over `steps.jsonl`, `kind="single_step"`, `assert_case(result, step_pass=1.0)`. Offline it is skipped.
- [ ] **Step 4: Run the full suite and confirm the deselected and skipped counts change only by the new live tests. Commit** `feat(evals): pytest plugin for dataset-driven agent evals`

### Task 9: Live baselines, gates and docs

**Files:**
- Create: `apps/research_agent/evals/baseline_steps.json`, `apps/kb_agent/evals/baseline.json`, `docs/phase1b-results.md`, `evidence/phase1b/`
- Modify: `apps/research_agent/evals/baseline.json` (only if the gate below reports a mismatch or a regression traced to Task 1's tool descriptions), `docs/architecture.md`, `README.md`, `CLAUDE.md`, `.claude/skills/verify-agentkit/features/`

- [ ] **Step 1: Research golden gate.** `uv run research-eval --model fireworks-glm --dataset apps/research_agent/evals/golden.jsonl --judge anthropic --gate apps/research_agent/evals/gates.yaml`, expecting exit 0.
  - If it exits 1, check whether the regression comes from the Task 1 description changes. Fix the descriptions, or re-record and justify it in the results doc.
  - Run at most one re-record.
- [ ] **Step 2: Single-step baseline.** `--dataset apps/research_agent/evals/steps.jsonl --gate .../gates_steps.yaml --write-baseline`.
  - Then run the plugin live: `uv run --no-sync pytest apps/research_agent/tests/test_eval_steps.py --agentkit-live`.
  - Record per-case pass/fail.
  - A case that fails consistently is evidence of a real agent behaviour gap. Write it down; don't loosen the case.
- [ ] **Step 3: KB pilot.**
  - Stamp a throwaway tenant, then run `agentkit-kb setup` and `make kb-ingest`.
  - Run `research-eval --agent apps/kb_agent/agent.yaml --model fireworks-glm --dataset apps/kb_agent/evals/golden.jsonl --judge anthropic --gate apps/kb_agent/evals/gates.yaml --write-baseline`.
  - Set the floors from the result: the floor sits below the baseline by the same margins as the research gates.
  - Run the gate once more to check it passes, then tear the tenant down.
- [ ] **Step 4: Docs.**
  - architecture: new sections for tool governance, the prompt registry, connectors, single-step evals and the plugin; update the section 16 open items.
  - README: kb agent quickstart and the `agentkit tools` / `agentkit-kb` commands.
  - `docs/phase1b-results.md` with evidence paths.
  - CLAUDE.md: Phase 1 status; mark the roadmap's Phase 1 complete only if the KB gate passes.
  - Run the verify-agentkit skill and update its feature map with the kb agent and `--agentkit-live`.
- [ ] **Step 5: Final checks.** Run the full offline suite, `make lint`, and `agentkit validate` on every agent, flow and subagent. Then commit `chore(phase1): kb pilot baseline, single-step baseline, docs`.

## Out of scope (named so they aren't mistaken for gaps)

These belong to Phase 2 or later:
- HITL for write tools
- Vault and cloud secret providers
- Qdrant, Weaviate and Pinecone adapters
- Langfuse prompt sync
- judge calibration (TPR/TNR cards)
- judge-result caching
- VCR replay
- pass^k / k-trial runs
- MCP

Still open from earlier phases and not touched here: the strong-tier models for openai, google_genai and fireworks-deepseek.
