# agentkit Phase 0b foundations plan

Phase 0 built the research agent through `build_deep_agent`, but a run keeps nothing after it exits, emits no trace, and carries no tenant. Phase 0b adds the foundations from the research report's Phase 0 row so every later agent inherits them. The users are the platform team and every product team that calls the factory.
The rule this program enforces is that every run carries a validated `PlatformContext`, persists only to its own tenant's encrypted Postgres, and traces only to its own tenant's collector.
The PRs, in order, are P1 `contracts`, P2 `context`, P3 `persistence`, P4 `memory-wiring`, P5 `telemetry`, and P6 `tenant-stamps`.
Phase 0 is complete when this plan is closed and T9 of `docs/superpowers/plans/2026-11-01-agentkit-phase0-plan.md` has passed.

## How to read this

One box is one unit of work. Every box names the evidence that checks it. A nested box is a sub-step of the box above it. Check a box only when its evidence exists, a file, a log line, a screenshot, a test run, or a SHA. The body is a how-to. The appendices explain and record.

The program runs `pstack/skills/poteto-mode/playbooks/autopilot-stack.md`. The operator lands every PR. All six PRs stop at verified and are handed to the operator. P2 and P4 change the `research` CLI, so they also wait for the operator's review.

In this repo, pstack paths resolve to the installed plugin at `~/.claude/plugins/cache/cursor-plugins/pstack/0.15.36/`. Read pstack files from there, and read repo files with `git show origin/main:<path>`.

Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

## Program checklist

### Arm the program

- [ ] State the protocol and this plan to the operator, then stop. Start execution only on the operator's explicit go.
- [ ] Read these at program start. Re-read them at every tick.
  - [ ] `skills/poteto-mode/playbooks/autopilot-stack.md` and `skills/poteto-mode/playbooks/autopilot-full.md` from the pstack plugin.
  - [ ] `skills/swarm/SKILL.md` from the pstack plugin.
  - [ ] `skills/poteto-mode/playbooks/opening-a-pr.md` from the pstack plugin.
  - [ ] `skills/architect/SKILL.md`, `skills/interrogate/SKILL.md`, and `skills/tdd/SKILL.md` from the pstack plugin.
  - [ ] `git show origin/main:docs/superpowers/plans/2026-11-01-agentkit-phase0b-plan.md`
  - [ ] `git show origin/main:CLAUDE.md`
- [ ] On the operator's go, arm the audit tick as `/loop 1h` with the tick prompt below. Never leave the cadence to memory.
- [ ] Use this tick prompt, verbatim. "Re-read the execution playbook from trunk. Audit the operation against it and fix drift in this tick. Probe every active lane and judge progress by side effects only. Stand down a stuck lane and dispatch its replacement now. Then post a short status message to the operator in chat only when the audit found a tracked change that no earlier status message reported, such as a PR opened, a code-ready head, a round launched or closed, a verdict, a merge, a stuck agent and the action taken, a blocker added or cleared, or a decision only the operator can make. Name every such change and nothing else. Do not repeat a table, the merged list, or an unchanged blocker. If the audit found none, end the turn with no reply text. Either way, log this tick's row in your decision trail. The row names the items reported, or none."
- [ ] On the operator's hold or stand-down, send every owner a zero-writes order at once.

### Spawn owners

- [ ] Spawn one owner per PR with the full lifecycle the execution playbook names. Owners use `subagent_type: "pstack:poteto-agent"` and the `feature, refactoring` model line.
- [ ] Follow this dependency graph. Each child PR stacks on its parent's branch.
  - [ ] P1 is first and branches from `main`.
  - [ ] P2 after P1.
  - [ ] P3 after P2.
  - [ ] P4 after P3.
  - [ ] P5 after P3. P5 does not need P4, so P4 and P5 run in parallel and both stack on P3.
  - [ ] P6 after P4 and P5. P6 stacks on P5 and rebases onto P4 once P4 lands.
- [ ] Hold the file boundaries.
  - [ ] P1 touches only `constraints.txt`, `pyproject.toml`, `contracts/**`, and `.github/workflows/canary.yml`.
  - [ ] P2 touches only `packages/agentkit-core/**`, `packages/agentkit-middleware/**`, `packages/agentkit-deep/**`, `apps/research_agent/**`, `scripts/smoke.py`, and `contracts/**`.
  - [ ] P3 touches only `packages/agentkit-persistence/**`, `pyproject.toml`, `contracts/**`, and `deploy/compose.dev.yaml`.
  - [ ] P4 touches only `packages/agentkit-deep/**`, `apps/research_agent/**`, and `scripts/smoke.py`.
  - [ ] P5 touches only `packages/agentkit-telemetry/**`, `packages/agentkit-middleware/src/agentkit_middleware/decisions.py`, `packages/agentkit-evals/**`, `apps/research_agent/**`, `pyproject.toml`, and `scripts/smoke.py`.
  - [ ] P6 touches only `deploy/**`, `Makefile`, `.github/workflows/ci.yml`, `.env.example`, `README.md`, `CLAUDE.md`, and `scripts/**`.
- [ ] Hold the review gate. P2 and P4 change the `research` CLI. They wait for the operator's review in chat with screenshots and a video before merge.

### PR mechanics, for every PR

- [ ] Resolve the forge once. Default to `gh`; if `command -v origin` succeeds and Origin can resolve the repository, use `origin pr` for every PR operation. Record any fallback to `gh`. Never require `gt`.
- [ ] Open the PR ready, never draft, per **Opening a PR**. Use `gh pr create --base <base-branch>`. A stack child targets its parent branch.
- [ ] Run `make lint` once before the PR-facing push. Push with hooks on.
- [ ] Run `/deslop` before each commit and `/no-comments` before review. `cursor-team-kit` is not installed here, so run the `pstack:comment-sicko` agent over the diff in place of `/deslop`, and record that substitution in the PR body.
- [ ] Triage every Bugbot and security-reviewer comment per `../references/bugbot-triage.md`.
- [ ] Rebase onto current trunk before the code-ready report and babysit. Keep that merge base in fix rounds. Rebase again only at merge prep, on a `git merge-tree` conflict with trunk, on a CI failure that comes from a change on trunk, or when a known concurrent change to the same files lands.

### Verdict and merge, for every PR

- [ ] A full swarm runs once, at the code-ready head. Another full swarm runs only for new behavior, a redesign, or a large new diff. A rebase, a merge-conflict resolution, or a minor fix gets a single verifier at the new head, and a wording-only change gets none. Run each full swarm per `skills/swarm/SKILL.md` from the pstack plugin. One gates lane. The ten live lanes from the PR's **Verify, live** block. The perf lane from its **Verify, perf** block. Two or more audit lanes, each with its own focus, that read the diff and the receipts and distrust the PR body. The root audits the receipts in the merge-ready report before the verdict.
- [ ] Judge every finding by the execution playbook's blocking rule. The verdict is clean when none blocks. A failure on trunk behavior in a lane marked `Regression lane against trunk.` is recorded against trunk and does not block the PR. A new head gets a fresh verdict, except for results that stay valid under the patch-id rule in `playbooks/shipping.md`.
- [ ] Stop each PR at verified and hand it to the operator, per `playbooks/autopilot-stack.md`. Nobody pushes after the handoff without the operator's go. A restack that leaves a PR's `git patch-id` unchanged keeps its verdict.

### Boot recipe, for every live lane

Each live lane runs in its own git worktree at the PR head on the operator's machine. Claude Code has no cloud VM. The `research` CLI and `scripts/smoke.py` are the surfaces. `control-cli` is not installed, so each lane drives the CLI with `Bash` and saves the terminal transcript as its screenshot.

- [ ] `git fetch origin <head-branch> && git checkout <head SHA>`.
- [ ] Run `UV_CONSTRAINT=constraints.txt uv sync --python 3.12`. From P3 on, run `docker compose -p agentkit-lane<n> -f deploy/compose.dev.yaml up -d --wait` with `AGENTKIT_PG_PORT=554<n>` so lanes never share a database. Never touch containers that this program did not start.
- [ ] Deliver input only through `uv run research ...`, `uv run research-eval ...`, `uv run python scripts/smoke.py ...`, and `uv run agentkit-prune ...`. Read-only diagnostics are `psql`, `docker compose logs`, and the collector's JSONL output files.
- [ ] Save every transcript to `/tmp/swarm-<pr-id>/worker-<n>/<slug>.log` with `script -q <file> <command>`, and return the paths with the report. Tear down the lane's compose project with `down -v`.

## Pin the upstream APIs with a contract suite (P1)

**Depends on.** None.

**Files.**

- [ ] Edit `constraints.txt` to add `langgraph-checkpoint==4.3.1`, `langgraph-checkpoint-postgres==3.2.0`, `psycopg==3.3.6`, `psycopg-binary==3.3.6`, `psycopg-pool==3.3.3`, `pycryptodome==4.2.0`, `langfuse==5.1.0`, `opentelemetry-sdk==1.45.2`, and `opentelemetry-exporter-otlp==1.45.2`.
- [ ] Edit `pyproject.toml` to add `contracts` to `testpaths` and register the `contract` and `pg` markers.
- [ ] Create `contracts/test_langchain_contract.py`, `contracts/test_deepagents_contract.py`, `contracts/test_langgraph_contract.py`, and `contracts/test_postgres_contract.py`.
- [ ] Create `.github/workflows/canary.yml`.

**Build.**

- [ ] Turn each prototype script in Appendix A into one contract test that asserts the observed behavior, not the signature text.
  - [ ] `test_langchain_contract.py` asserts that `request.runtime.context` and `before_agent`'s `runtime.context` carry the object passed as `context=`. It also asserts the constructors of `ModelFallbackMiddleware`, `ModelCallLimitMiddleware`, `ToolCallLimitMiddleware`, `PIIMiddleware`, `ToolErrorMiddleware`, and `HumanInTheLoopMiddleware(interrupt_mode="per_call")` by building each one.
  - [ ] `test_deepagents_contract.py` asserts that a `StoreBackend` namespace factory reads `rt.context`, that a `write_file` to a `CompositeBackend` route lands at that namespace, that `MemoryMiddleware` loads two `AGENTS.md` sources into `<agent_memory>`, that `runtime.server_info` is `None`, and that `HarnessProfile(excluded_tools=...)` removes tools from the bound set.
  - [ ] `test_langgraph_contract.py` asserts that `get_config()` raises `RuntimeError` outside a run, that `TracePolicy` and `omit_payload` import from `langgraph.types`, and that `AIMessage.usage_metadata` reaches `on_llm_end` while `metadata` reaches only `on_chat_model_start`.
  - [ ] `test_postgres_contract.py` is marked `pg` and skips without `AGENTKIT_TEST_DATABASE_URL`. It asserts the encrypted roundtrip with no plaintext in `checkpoint_blobs`, the lost update on two concurrent `ainvoke` calls on one `thread_id`, the serialized result under `pg_advisory_lock`, the default `asearch` limit of 10, the per-label prefix match, and `InvalidNamespaceError` on a label with a dot.
- [ ] Add `canary.yml`, a weekly scheduled job that runs `uv lock --upgrade-package deepagents --upgrade-package langchain --upgrade-package langchain-core --upgrade-package langgraph` in a scratch copy and then runs `uv run pytest contracts -m "contract or pg"` with a Postgres service.

**You see.**

- [ ] `uv run pytest contracts -m contract` prints a pass line with no skips, and `uv run pytest contracts -m pg` prints the same once `AGENTKIT_TEST_DATABASE_URL` is set.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `contracts/test_*_contract.py` gain every case named in **Build**. Run `uv run pytest contracts -m "contract or pg"` and `make test`.
- [ ] Prove each contract can fail. For three contracts, invert one assertion locally, show the red run, and revert. Paste the red output into the PR body.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on `inherit-parent` at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Run `make test` at trunk and head. Trunk has no contract suite, so record that and gate the head result plus the unchanged count of the existing 53 tests. Save `regression.log`. Pass when head passes the 53 existing tests and every new contract test.
- [ ] Lane 2. Run `uv run pytest contracts -m contract -v`. Save `contract-offline.log`. Pass when every contract test passes with no network access, checked by running under `HTTPS_PROXY=http://127.0.0.1:9`.
- [ ] Lane 3. Start the lane's Postgres and run `uv run pytest contracts -m pg -v`. Save `contract-pg.log`. Pass when every `pg` test passes.
- [ ] Lane 4. Unset `AGENTKIT_TEST_DATABASE_URL` and run `uv run pytest contracts -m pg`. Save `pg-skip.log`. Pass when every `pg` test is skipped with a reason that names the variable.
- [ ] Lane 5. Pin `deepagents==0.7.31` in a scratch copy of `constraints.txt` and run the contract suite. Save `older-deepagents.log`. Pass when the run either passes or fails with an assertion that names the changed behavior, never with an import traceback that hides it.
- [ ] Lane 6. Run the concurrency contract ten times in a loop. Save `concurrency-repeat.log`. Pass when all ten runs observe the lost update without the lock and the linear chain with it.
- [ ] Lane 7. Run the canary job locally with `act -j canary`, or run its steps by hand if `act` is absent. Save `canary.log`. Pass when the job reaches the contract step and reports its result.
- [ ] Lane 8. Run `UV_CONSTRAINT=constraints.txt uv sync --python 3.12` from a clean clone. Save `clean-sync.log`. Pass when the sync resolves every new pin with no conflict.
- [ ] Lane 9. Grep the contract suite for `inspect.signature`. Save `no-signature-tests.log`. Pass when the grep finds nothing, because the suite asserts behavior.
- [ ] Lane 10. Run `make lint`. Save `lint.log`. Pass when ruff and mypy report no errors.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. The wall time of `make test`, and separately the wall time of `uv run pytest contracts -m "contract or pg"`.
- [ ] Probe. Run `hyperfine --warmup 1 --runs 5 'uv run pytest -q'` at trunk and head, interleaved, then time the contract suite alone at head.
- [ ] Baseline. Record the trunk `make test` time first.
- [ ] Rule. Head `make test` time must stay within 1.5 times trunk. The contract suite alone must finish in under 60 seconds. Either breach fails.

**Review gate.** None. P1 is not review-gated.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Rebased onto current trunk after the verdict, patch-id unchanged.
- [ ] The root appends P1 to the stack and the operator lands it bottom-up.

## Carry a validated tenant context through every run (P2)

**Depends on.** P1.

**Files.**

- [ ] Create `packages/agentkit-core/src/agentkit_core/context.py`.
- [ ] Edit `packages/agentkit-core/src/agentkit_core/settings.py` and `packages/agentkit-core/src/agentkit_core/__init__.py`.
- [ ] Create `packages/agentkit-middleware/src/agentkit_middleware/tenant_guard.py`.
- [ ] Edit `packages/agentkit-middleware/src/agentkit_middleware/selection.py` and `packages/agentkit-middleware/src/agentkit_middleware/decisions.py`.
- [ ] Edit `packages/agentkit-deep/src/agentkit_deep/factory.py`.
- [ ] Edit `apps/research_agent/src/research_agent/agent.py`, `apps/research_agent/src/research_agent/cli.py`, and `apps/research_agent/src/research_agent/eval_cli.py`.
- [ ] Create `scripts/smoke.py`.

**Build.**

- [ ] Add `PlatformContext` and `store_namespace` in `agentkit_core/context.py`, shaped as in Appendix E. `Label` rejects dots, because the Postgres store rejects them.
- [ ] Add `deployment_tenant` to `Settings`, read from `AGENTKIT_TENANT`.
- [ ] Add `TenantGuardMiddleware` in `tenant_guard.py`. Its `before_agent` raises `TenantMismatch` when `runtime.context.tenant` differs from the deployment tenant.
- [ ] Make `build_deep_agent` always pass `context_schema=PlatformContext`, insert `TenantGuardMiddleware` first, and accept `store`. Callers cannot opt out.
- [ ] Move the selection cache in `SelectionMiddleware` from the instance `OrderedDict` into agent state through the middleware's `state_schema`, and delete `_thread_id` and its `"_default"` fallback. `DecisionsClient` takes `prompt_cache_key` from `runtime.context.thread_id`.
- [ ] Give `research` the flags `--tenant`, `--user`, and `--thread`. A missing `--thread` mints a new `uuid4`, and the CLI prints it. `research-eval` mints one thread per case.
- [ ] Add `scripts/smoke.py`, which builds a factory agent on `ScriptedChatModel` with a given context and prints the context the tool saw. Later PRs extend it.

**You see.**

- [ ] `uv run research "q" --tenant acme --model <registry-name>` prints `thread: <uuid>` before the report path.
- [ ] `AGENTKIT_TENANT=acme uv run python scripts/smoke.py --tenant other` exits 1 with `TenantMismatch: run tenant 'other' != deployment tenant 'acme'`.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `packages/agentkit-core/tests/test_context.py` gains cases for `Label` rejecting `a.b` and empty strings, for `store_namespace` producing `(tenant, product, team, user_id, kind)` and `(tenant, product, team, "global", kind)`, and for `PlatformContext` being frozen. Run `uv run pytest packages/agentkit-core`.
- [ ] `packages/agentkit-middleware/tests/test_tenant_guard.py` gains a match case and a mismatch case. Run `uv run pytest packages/agentkit-middleware`.
- [ ] `packages/agentkit-deep/tests/test_selection_integration.py` gains a case where two threads in one process get independent selections, and a case where a run with no context fails at the factory boundary. Update `test_factory_integration.py` for the guard's position. Run `make test`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on `inherit-parent` at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Run `uv run research "What is LangGraph?" --model anthropic` at trunk and head when keys exist. Without keys, run the end-to-end fake test `apps/research_agent/tests/test_agent.py` at both. Save `regression.log`. Pass when both produce a cited report and head also prints a thread id.
- [ ] Lane 2. Run `scripts/smoke.py --tenant acme --user u1` with `AGENTKIT_TENANT=acme`. Save `context-flows.log`. Pass when the tool prints `acme/u1/<thread>`.
- [ ] Lane 3. Run `scripts/smoke.py --tenant other` with `AGENTKIT_TENANT=acme`. Save `guard-rejects.log`. Pass when the process exits 1 with `TenantMismatch` and the scripted model recorded zero calls.
- [ ] Lane 4. Run `scripts/smoke.py --tenant acme.corp`. Save `label-dot.log`. Pass when the run fails before the agent starts with a validation error that names `tenant`.
- [ ] Lane 5. Run `scripts/smoke.py` twice in one process on two threads with different scripted selections. Save `selection-per-thread.log`. Pass when each thread's bound tools match its own selection.
- [ ] Lane 6. Run `uv run research --help`. Save `help.log`. Pass when `--tenant`, `--user`, and `--thread` appear with their defaults.
- [ ] Lane 7. Run `uv run research-eval` on the fake dataset path used by `test_agent.py`. Save `eval-threads.log`. Pass when each case logs a distinct thread id.
- [ ] Lane 8. Grep the repo for `"_default"` and `OrderedDict` in `agentkit_middleware`. Save `no-default-thread.log`. Pass when both greps find nothing.
- [ ] Lane 9. Run `uv run pytest contracts -m contract`. Save `contracts.log`. Pass when every contract still passes.
- [ ] Lane 10. Run `make lint`. Save `lint.log`. Pass when ruff and mypy report no errors.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Wall time of 200 scripted three-step runs through `build_deep_agent` in one process.
- [ ] Probe. Add `--repeat 200` to `scripts/smoke.py` at head. At trunk, run the same loop from a throwaway copy of the script with the context lines removed. Interleave three trunk and three head runs.
- [ ] Baseline. Record the trunk median first.
- [ ] Rule. Head median must stay within 1.05 times trunk. More fails, because the guard and context must cost almost nothing.

**Review gate.** The operator reviews before merge.

- [ ] Copy lane 2, 3, and 6 transcripts into `docs/media/p2-review-*.log` and render each to `docs/media/p2-review-*.png` with a terminal screenshot.
- [ ] Record a 30 to 60 second video of lanes 2 and 3 with the macOS screen recorder. Save it as `docs/media/p2-review.mp4`.
- [ ] Post the screenshots and the video in chat. Stop at merge-ready. Wait for the operator's click.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Rebased onto P1's branch after the verdict, patch-id unchanged.
- [ ] The root appends P2 to the stack and the operator lands it bottom-up.

## Persist threads and memory in encrypted Postgres (P3)

**Depends on.** P2.

**Files.**

- [ ] Create `packages/agentkit-persistence/pyproject.toml`, `packages/agentkit-persistence/src/agentkit_persistence/__init__.py`, `packages/agentkit-persistence/src/agentkit_persistence/py.typed`, `packages/agentkit-persistence/src/agentkit_persistence/open.py`, `packages/agentkit-persistence/src/agentkit_persistence/lock.py`, and `packages/agentkit-persistence/src/agentkit_persistence/prune.py`.
- [ ] Create `packages/agentkit-persistence/tests/test_agentkit_persistence_import.py`, `packages/agentkit-persistence/tests/test_open.py`, `packages/agentkit-persistence/tests/test_lock.py`, and `packages/agentkit-persistence/tests/test_prune.py`.
- [ ] Edit `pyproject.toml` to add the package to dependencies and `[tool.uv.sources]`, and the `agentkit-prune` script.
- [ ] Create `deploy/compose.dev.yaml` with one `pgvector/pgvector:pg16` service on `${AGENTKIT_PG_PORT:-55432}`.
- [ ] Edit `contracts/test_postgres_contract.py` to also run against `open_persistence`.

**Build.**

- [ ] Add `PersistenceSettings` and `open_persistence(settings) -> AsyncIterator[Persistence]` in `open.py`, shaped as in Appendix E. It opens one `AsyncConnectionPool` with `autocommit=True`, `prepare_threshold=0`, and `row_factory=dict_row`, builds `AsyncPostgresSaver` with `EncryptedSerializer.from_pycryptodome_aes()`, builds `AsyncPostgresStore` with `TTLConfig`, runs both `setup()` calls, and starts the TTL sweeper. It refuses to start when `LANGGRAPH_AES_KEY` is missing or not 16, 24, or 32 characters.
- [ ] Add `thread_lock(persistence, thread_id)` in `lock.py`, an async context manager that holds `pg_advisory_lock(hashtext(thread_id))` on a connection from a separate lock pool, so a waiting run never starves the saver's pool.
- [ ] Add `prune(persistence, older_than)` in `prune.py`. It selects thread ids whose newest checkpoint `ts` is older than the cutoff and calls `adelete_thread` for each. Running it twice deletes nothing the second time. Expose it as `agentkit-prune --older-than 30d`.

**You see.**

- [ ] `uv run agentkit-prune --older-than 30d` prints `pruned 0 threads` on a fresh database and exits 0.
- [ ] Starting with `LANGGRAPH_AES_KEY` unset exits with `ConfigError: LANGGRAPH_AES_KEY must be 16, 24, or 32 characters`.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `test_open.py` gains a key validation case that runs offline, and `pg` cases for setup idempotence, an encrypted roundtrip, and a store write under a namespace from `store_namespace`. Run `uv run pytest packages/agentkit-persistence -m "not live"` with `AGENTKIT_TEST_DATABASE_URL` set.
- [ ] `test_lock.py` gains a `pg` case where two concurrent runs on one thread produce one linear checkpoint chain with both turns visible. Run the same command.
- [ ] `test_prune.py` gains `pg` cases for an old thread deleted, a fresh thread kept, and a second prune deleting nothing. Run the same command.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on `inherit-parent` at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Run `make test` at trunk and head. Trunk has no persistence package, so record that and gate the head suite plus a two-turn scripted thread that survives a process restart. Save `regression.log`. Pass when both suites pass and the second process sees turn one.
- [ ] Lane 2. Run two scripted turns in two processes on one thread through `open_persistence`. Save `resume.log`. Pass when turn two's state holds both turns.
- [ ] Lane 3. After lane 2, run `psql -c "select count(*) from checkpoint_blobs where convert_from(blob,'LATIN1') like '%PINEAPPLE%'"`. Save `ciphertext.log`. Pass when the count is 0.
- [ ] Lane 4. Restart with a different `LANGGRAPH_AES_KEY` and read lane 2's thread. Save `wrong-key.log`. Pass when the read fails with a decryption error and nothing is overwritten.
- [ ] Lane 5. Run two concurrent turns on one thread with `thread_lock`. Save `locked.log`. Pass when the final state holds both turns in one linear chain.
- [ ] Lane 6. Run lane 5 without `thread_lock`. Save `unlocked.log`. Pass when the lost update reproduces, which shows the lock is what fixes it.
- [ ] Lane 7. Write store items for `acme` and `other` and search with prefix `("acme",)` and `limit=100`. Save `store-isolation.log`. Pass when no `other` item returns.
- [ ] Lane 8. Backdate one thread's checkpoint `ts` by 40 days with `psql` and run `agentkit-prune --older-than 30d` twice. Save `prune.log`. Pass when the first run prunes 1 and the second prunes 0.
- [ ] Lane 9. Run 20 concurrent locked runs on 20 threads with a saver pool of `max_size=10`. Save `pool-pressure.log`. Pass when all 20 finish and none times out.
- [ ] Lane 10. Run `make lint`. Save `lint.log`. Pass when ruff and mypy report no errors.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. The p50 and p95 latency of one scripted agent super-step. Trunk has no checkpointer, so the diff-added work is the encrypted checkpoint write, and the end state the user waits for is a ten-step run finishing.
- [ ] Probe. Run 200 ten-step scripted runs at trunk with no checkpointer and at head with `open_persistence` against the lane's local Postgres. Interleave the runs.
- [ ] Baseline. Record the trunk p50 and p95 first.
- [ ] Rule. Head p50 per super-step may exceed trunk by at most 15 ms, and a ten-step run may exceed trunk by at most 200 ms at p95. Either breach fails. These budgets are a guess for local Postgres and are recorded as such.

**Review gate.** None. P3 is not review-gated.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Rebased onto P2's branch after the verdict, patch-id unchanged.
- [ ] The root appends P3 to the stack and the operator lands it bottom-up.

## Wire persistence and memory tiers into the factory and the research agent (P4)

**Depends on.** P3.

**Files.**

- [ ] Edit `packages/agentkit-deep/src/agentkit_deep/factory.py` and add `packages/agentkit-deep/src/agentkit_deep/memory.py`.
- [ ] Edit `packages/agentkit-deep/tests/test_factory_integration.py` and add `packages/agentkit-deep/tests/test_memory_tiers.py`.
- [ ] Edit `apps/research_agent/src/research_agent/agent.py`, `apps/research_agent/src/research_agent/cli.py`, and `apps/research_agent/src/research_agent/eval_cli.py`.
- [ ] Edit `scripts/smoke.py`.

**Build.**

- [ ] Add `memory_backend()` in `memory.py`. It returns a `CompositeBackend` whose default is `StateBackend()` for ephemeral files, with `/memories/` routed to `StoreBackend` on the user namespace and `/org/` routed to `StoreBackend` on the global namespace. Both namespaces come from `store_namespace(rt.context, ...)`. The declarative loader (`agentkit_deep.skills_mount`) already mounts agent skills at `/skills/<owner>/`; that mount becomes one more route inside `memory_backend()` (not a second `CompositeBackend`), so a persistent agent keeps its skills.
- [ ] Make `build_deep_agent` take `persistence: Persistence | None`. When it is set, pass `checkpointer`, `store`, `backend=memory_backend()`, `memory=["/org/AGENTS.md", "/memories/AGENTS.md"]`, and `permissions=[FilesystemPermission(operations=["write"], paths=["/org/**"], mode="deny")]`.
- [ ] Run every `research` turn inside `thread_lock`. `--thread <id>` resumes a thread. `research-eval` uses persistence only with `--persist`.
- [ ] Keep `/report.md` on the default `StateBackend` route so `read_output` keeps working.

**You see.**

- [ ] `uv run research "follow up" --thread <id>` prints `resumed thread <id> at step <n>`.
- [ ] A scripted agent that writes `/org/AGENTS.md` gets a tool error that names the denied path, and the store holds no `/org/` item.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `test_memory_tiers.py` gains cases for a `/memories/` write landing at the user namespace, an `/org/` write denied, two users not seeing each other's `/memories/`, and both `AGENTS.md` sources reaching `<agent_memory>`. These run on `InMemoryStore` with no Postgres. Run `uv run pytest packages/agentkit-deep`.
- [ ] `apps/research_agent/tests/test_agent.py` gains a resume case on `InMemorySaver`. Run `make test`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on `inherit-parent` at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Run the end-to-end research flow at trunk and head, with real keys if present and the fake end-to-end test otherwise. Save `regression.log`. Pass when both produce a cited `/report.md`.
- [ ] Lane 2. Run `scripts/smoke.py --persist` for turn one, kill the process, and run turn two with `--thread`. Save `resume.log`. Pass when turn two prints `resumed thread` and sees turn one.
- [ ] Lane 3. Run a scripted turn that writes `/memories/AGENTS.md` for user `u1`, then a new thread for `u1`. Save `memory-recall.log`. Pass when the second thread's system prompt contains the note.
- [ ] Lane 4. Repeat lane 3's second step as user `u2`. Save `memory-isolation.log`. Pass when `u2`'s prompt lacks the note.
- [ ] Lane 5. Run a scripted turn that writes `/org/AGENTS.md`. Save `org-denied.log`. Pass when the tool error names the denied path and `psql` finds no `/org/` row.
- [ ] Lane 6. Seed `/org/AGENTS.md` with `psql` through the store and start a thread. Save `org-read.log`. Pass when the prompt contains the org note.
- [ ] Lane 7. Run two `research` processes on one `--thread` at once with scripted models. Save `cli-lock.log`. Pass when both turns appear in order in the final state.
- [ ] Lane 8. Run `uv run research --help`. Save `help.log`. Pass when `--thread` describes resume.
- [ ] Lane 9. Run `research-eval --persist` on the fake dataset. Save `eval-persist.log`. Pass when each case has its own thread in `checkpoints` and the scores match the run without `--persist`.
- [ ] Lane 10. Run `make lint`. Save `lint.log`. Pass when ruff and mypy report no errors.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Wall time of a scripted ten-step research run that ends with `/report.md` written.
- [ ] Probe. Run 50 interleaved runs each of trunk without persistence, and of head with `--persist` against local Postgres.
- [ ] Baseline. Record the trunk median first.
- [ ] Rule. Head median may exceed trunk by at most 300 ms per run, which covers ten checkpoint writes, two memory reads, and the lock. More fails.

**Review gate.** The operator reviews before merge.

- [ ] Copy lane 2, 3, and 5 transcripts into `docs/media/p4-review-*.log` and render each to `docs/media/p4-review-*.png` with a terminal screenshot.
- [ ] Record a 30 to 60 second video of a run, a kill, and a resume. Save it as `docs/media/p4-review.mp4`.
- [ ] Post the screenshots and the video in chat. Stop at merge-ready. Wait for the operator's click.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Rebased onto P3's branch after the verdict, patch-id unchanged.
- [ ] The root appends P4 to the stack and the operator lands it bottom-up.

## Trace every run to its tenant and record its cost (P5)

**Depends on.** P3.

**Files.**

- [ ] Create `packages/agentkit-telemetry/pyproject.toml`, `packages/agentkit-telemetry/src/agentkit_telemetry/__init__.py`, `packages/agentkit-telemetry/src/agentkit_telemetry/py.typed`, `packages/agentkit-telemetry/src/agentkit_telemetry/tracing.py`, `packages/agentkit-telemetry/src/agentkit_telemetry/run_config.py`, and `packages/agentkit-telemetry/src/agentkit_telemetry/ledger.py`.
- [ ] Create `packages/agentkit-telemetry/tests/test_agentkit_telemetry_import.py`, `packages/agentkit-telemetry/tests/test_run_config.py`, and `packages/agentkit-telemetry/tests/test_ledger.py`.
- [ ] Edit `packages/agentkit-middleware/src/agentkit_middleware/decisions.py` to return `usage` with the selection.
- [ ] Edit `packages/agentkit-evals/src/agentkit_evals/runner.py` to add `run_id`, `trace_id`, and `usage` to `CaseResult`.
- [ ] Edit `apps/research_agent/src/research_agent/cli.py`, `apps/research_agent/src/research_agent/eval_cli.py`, `pyproject.toml`, and `scripts/smoke.py`.

**Build.**

- [ ] Add `configure_tracing(settings)` in `tracing.py`. It builds one `Langfuse` client with an OTLP `span_exporter` pointed at `OTEL_EXPORTER_OTLP_ENDPOINT`, a resource attribute `agentkit.tenant`, and a `mask` function that drops `gen_ai.prompt` and `gen_ai.completion` unless `AGENTKIT_TRACE_PAYLOADS=1`. It does not set `LANGSMITH_TRACING`.
- [ ] Add `run_config(ctx, prompt_hash, ledger) -> RunnableConfig` in `run_config.py`. It sets `configurable.thread_id`, the metadata keys `tenant`, `product`, `team`, `user_id`, `thread_id`, `agent_name`, `agent_version`, `prompt_hash`, `langfuse_user_id`, `langfuse_session_id`, and `langfuse_tags`, plus the Langfuse handler and the ledger as callbacks. Every caller builds its config here.
- [ ] Add `CostLedger` in `ledger.py`. It reads the tenant on `on_chat_model_start`, joins `usage_metadata` on `on_llm_end` by `run_id`, adds Decisions usage, and writes one row per run to an `agentkit_usage` table through `Persistence`. The table is created idempotently in `setup()`.
- [ ] Compute `prompt_hash` as the SHA-256 of the resolved system prompt in `build_deep_agent`, and expose it on the returned agent's config.

**You see.**

- [ ] After a scripted run, the collector's JSONL holds spans whose resource carries `agentkit.tenant=acme` and whose attributes carry `user.id`, `session.id`, and `langfuse.trace.metadata.prompt_hash`.
- [ ] `psql -c "select tenant, thread_id, input_tokens, output_tokens from agentkit_usage"` returns one row per run.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `test_run_config.py` gains cases for every metadata key, the thread id, and stable `prompt_hash` values. It uses an `InMemorySpanExporter` to assert span attributes and to assert that the prompt text is absent by default. Run `uv run pytest packages/agentkit-telemetry`.
- [ ] `test_ledger.py` gains a case with a `ScriptedChatModel` subclass that emits `usage_metadata`, asserting one aggregated row per run with the right tenant. A `pg` case asserts the row in Postgres. Run the same command with `AGENTKIT_TEST_DATABASE_URL` set.
- [ ] `packages/agentkit-middleware/tests/test_decisions.py` gains a case that returns usage from the fixture. Run `make test`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on `inherit-parent` at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Run the end-to-end research flow at trunk and head. Trunk emits no spans, so record that and gate the head report plus at least one span per model call in the collector file. Save `regression.log`. Pass when both produce the report and head's collector file has the spans.
- [ ] Lane 2. Start an `otel/opentelemetry-collector-contrib` container with a file exporter and run `scripts/smoke.py --trace`. Save `spans.log`. Pass when the file holds spans with `agentkit.tenant`, `user.id`, and `session.id`.
- [ ] Lane 3. Grep lane 2's file for the scripted prompt text. Save `no-payload.log`. Pass when the grep finds nothing.
- [ ] Lane 4. Repeat lane 2 with `AGENTKIT_TRACE_PAYLOADS=1`. Save `payload-opt-in.log`. Pass when the prompt text appears.
- [ ] Lane 5. Stop the collector and run `scripts/smoke.py --trace`. Save `collector-down.log`. Pass when the run finishes and its report is written, with at most one warning line about export.
- [ ] Lane 6. Run three scripted runs and query `agentkit_usage`. Save `ledger.log`. Pass when it returns three rows whose token sums match the scripted `usage_metadata`.
- [ ] Lane 7. Run with a selection fixture that reports Decisions usage. Save `decisions-usage.log`. Pass when the ledger row carries the Decisions tokens in their own columns.
- [ ] Lane 8. Run `research-eval` on the fake dataset. Save `eval-trace.log`. Pass when `eval_results.json` holds `run_id`, `trace_id`, and `usage` per case.
- [ ] Lane 9. Grep the spans for `LANGSMITH_` and `_API_KEY`. Save `no-env-leak.log`. Pass when the grep finds nothing.
- [ ] Lane 10. Run `make lint`. Save `lint.log`. Pass when ruff and mypy report no errors.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Wall time of a scripted ten-step run. Trunk has no tracing, so the diff-added work is span export plus one ledger write, and the end state the user waits for is the run's return.
- [ ] Probe. Run 100 interleaved runs at trunk, and at head with tracing to a local collector.
- [ ] Baseline. Record the trunk median first.
- [ ] Rule. Head median may exceed trunk by at most 5 percent plus 20 ms for the ledger write. More fails. Span export must stay off the run's path, checked by lane 5.

**Review gate.** None. P5 is not review-gated.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Rebased onto P3's branch after the verdict, patch-id unchanged.
- [ ] The root appends P5 to the stack and the operator lands it bottom-up.

## Stamp one isolated deployment per tenant and prove the exit criterion (P6)

**Depends on.** P4 and P5.

**Files.**

- [ ] Create `deploy/compose.yaml`, `deploy/otel-collector.yaml`, `deploy/tenants/example.env`, and `deploy/README.md`.
- [ ] Create `scripts/stamp_tenant.sh` and `scripts/phase0_exit.sh`.
- [ ] Edit `Makefile`, `.github/workflows/ci.yml`, `.env.example`, `README.md`, and `CLAUDE.md`.

**Build.**

- [ ] Add `deploy/compose.yaml` with a Postgres service and an OTel collector service. Each tenant runs it as its own compose project, `agentkit-<tenant>`, so each tenant gets its own database volume, its own collector, and its own ports. Nothing is shared.
- [ ] Add `deploy/tenants/example.env` with `AGENTKIT_TENANT`, `AGENTKIT_PG_PORT`, `DATABASE_URL`, `LANGGRAPH_AES_KEY`, `OTEL_EXPORTER_OTLP_ENDPOINT`, `AGENTKIT_OTLP_PORT`, and optional `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_HOST`. The collector forwards to the tenant's Langfuse project when the keys are set, and always writes a JSONL file.
- [ ] Add `scripts/stamp_tenant.sh <tenant>`. It writes `deploy/tenants/<tenant>.env` with a fresh 32-character AES key when the file is missing, then starts the compose project and runs `open_persistence` setup. Running it twice changes nothing.
- [ ] Add `make stamp TENANT=<t>`, `make contract TENANT=<t>`, and `make phase0-exit`. `scripts/phase0_exit.sh` stamps `tenant-a` and `tenant-b`, runs the contract suite and a scripted research run against each, and asserts that each collector file holds only its own tenant's spans.
- [ ] Add a `services: postgres` job to `ci.yml` that runs the `pg` contracts. Add the new variables to `.env.example`. Update the README status and the `CLAUDE.md` current-work line.

**You see.**

- [ ] `make phase0-exit` ends with `phase0 exit: tenant-a OK, tenant-b OK, traces separated` and exits 0.

**Verify, unit.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] `scripts/phase0_exit.sh` is the check for this PR, because P6 adds no library code. Add `shellcheck scripts/*.sh` to `make lint`. Run `make lint` and `make test`.

**Verify, live.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked. Ten lanes on `inherit-parent` at the PR head, per the boot recipe.

- [ ] Lane 1. Regression lane against trunk. Run `make test` and the fake end-to-end research test at trunk and head. Trunk has no stamps, so record that and gate `make phase0-exit` at head. Save `regression.log`. Pass when both pass and `phase0-exit` exits 0.
- [ ] Lane 2. Run `make phase0-exit`. Save `exit.log`. Pass when the final line reads `traces separated` and the exit code is 0.
- [ ] Lane 3. Grep `tenant-a`'s collector file for `tenant-b`, and the reverse. Save `trace-separation.log`. Pass when both greps find nothing.
- [ ] Lane 4. Connect to `tenant-a`'s database and list the threads. Save `db-separation.log`. Pass when no `tenant-b` thread exists.
- [ ] Lane 5. Run `make stamp TENANT=tenant-a` a second time. Save `stamp-idempotent.log`. Pass when the AES key in the env file is unchanged and setup reports no new migrations.
- [ ] Lane 6. Run `scripts/smoke.py` with `tenant-a`'s env and `--tenant tenant-b`. Save `cross-tenant.log`. Pass when it exits 1 with `TenantMismatch`.
- [ ] Lane 7. Read `tenant-a`'s checkpoints with `tenant-b`'s AES key. Save `cross-key.log`. Pass when decryption fails.
- [ ] Lane 8. Run `make contract TENANT=tenant-b`. Save `contract-b.log`. Pass when every contract passes.
- [ ] Lane 9. Run the `research` CLI with real keys against `tenant-a`, if T9 keys exist. Otherwise, record the skip. Save `real-run.log`. Pass when the report is written and the collector holds its spans, or when the skip is recorded with its reason.
- [ ] Lane 10. Run `git check-ignore deploy/tenants/tenant-a.env .env`. Save `env-ignored.log`. Pass when both paths are ignored.

**Verify, perf.** Tests alone are not sufficient verification. A PR is verified only when its unit, live, and perf boxes are all checked.

- [ ] Metric. Wall time of `make stamp TENANT=<t>` from nothing to ready, and of `make phase0-exit`.
- [ ] Probe. Time three cold stamps after `docker compose down -v`, and three `phase0-exit` runs. Trunk has no stamp, so set absolute budgets.
- [ ] Baseline. Record trunk `make test` time first, as the reference for the regression lane.
- [ ] Rule. A cold stamp must finish in under 60 seconds with the images cached. `make phase0-exit` must finish in under 5 minutes. Either breach fails.

**Review gate.** None. P6 is not review-gated.

**Merge.**

- [ ] Root's clean verdict at the exact head SHA.
- [ ] Bugbot triage done.
- [ ] Rebased onto P5's branch, and onto P4 once P4 lands, after the verdict, patch-id unchanged.
- [ ] The root appends P6 to the stack and the operator lands it bottom-up.

## Close the program

- [ ] Every box above is checked with its evidence.
- [ ] T9 from the Phase 0 plan has passed, or the operator has accepted it as still open.
- [ ] Reply to the operator with the report the execution playbook names, listing each PR with its verdict.

## Appendix A. Prototype evidence

Two throwaway prototypes ran on 2026-11-01 under the pinned versions. Their scripts are in the session scratchpad. They are throwaway, not committed, and P1 turns each one into a contract test. Each finding below was observed, unless it is marked inferred.

Persistence, with `langgraph-checkpoint-postgres` 3.2.0, `psycopg` 3.3.6, and Postgres 16.

- `AsyncPostgresSaver` imports from `langgraph.checkpoint.postgres.aio`. `AsyncPostgresStore` imports from `langgraph.store.postgres.aio`, and `PostgresStore` from `langgraph.store.postgres`.
- `EncryptedSerializer.from_pycryptodome_aes()` reads `LANGGRAPH_AES_KEY` as raw bytes of length 16, 24, or 32, not base64. Blobs and writes were stored as `msgpack+aes`, with 0 of 12 rows holding the plaintext marker. The `checkpoints.checkpoint` and `checkpoints.metadata` columns stay plaintext JSONB, so tenant ids in metadata are visible to anyone with database access.
- The store has `TTLConfig`, per-item `ttl=`, and `start_ttl_sweeper`. The saver has no TTL but has `aprune`, `adelete_thread`, and `adelete_for_runs`.
- `asearch` defaults to `limit=10`. Prefix matching is per label, so `("tenant-a",)` does not match `tenant-ab`. A label containing a dot raises `InvalidNamespaceError`.
- Two concurrent `ainvoke` calls on one thread raised no error. They forked two checkpoint chains, and the later writer won. With `pg_advisory_lock(hashtext(thread_id))` held across the run, the runs serialized into one chain holding both turns.
- One `AsyncConnectionPool` backed both saver and store. A held advisory lock pins one connection for the whole run, so P3 gives locks their own pool. That sizing rule is inferred.

APIs, with `deepagents` 0.7.32, `langchain` 1.4.7, `langfuse` 5.1.0, and `opentelemetry-sdk` 1.45.2.

- `create_deep_agent` accepts `context_schema` and `store`. A pydantic context passed as `context=` reached `before_agent`, `wrap_model_call` through `request.runtime.context`, and a tool through `ToolRuntime`.
- `runtime.server_info` exists and is `None` outside Agent Server.
- `StoreBackend(namespace=lambda rt: ...)` read the tenant from `rt.context`. A `write_file("/memories/note.md")` landed at `('tenants','acme','users','u7','memories')`, and I re-ran that check myself.
- `MemoryMiddleware` loaded two `AGENTS.md` sources from two namespaces into `<agent_memory>`. Memory loads once per thread.
- `HarnessProfile` exists, but only through the module-global `register_harness_profile`, keyed by provider or model. It removed `delete`, `glob`, and `task` from the bound tools. It cannot vary per tenant.
- `HumanInTheLoopMiddleware(interrupt_mode="per_call")` exists. `create_deep_agent(interrupt_on=...)` does not expose the mode, so per-call mode means passing the middleware directly. That last point is inferred from the signature.
- LangSmith OTel produced 0 spans with only `LANGSMITH_OTEL_ENABLED` and `LANGSMITH_OTEL_ONLY`, and 3 spans once `LANGSMITH_TRACING=true` was added. I re-ran both. Those spans also carried every `LANGSMITH_*` variable as metadata, and the full prompt in `gen_ai.prompt`.
- Langfuse's `CallbackHandler` imports from `langfuse.langchain`. User, session, and tags come from `config["metadata"]` keys such as `langfuse_user_id`. `Langfuse(span_exporter=..., mask=...)` worked with an in-memory exporter and produced `user.id`, `session.id`, and `usage_details`.
- `on_llm_end` receives `usage_metadata` but not `metadata`. `on_chat_model_start` receives `metadata`, so a ledger joins the two on `run_id`.

Still unproven, each assigned to the PR that proves it.

- A Langfuse project receives the collector-forwarded spans with user and session intact. P6 lane 9 covers this when keys exist.
- The perf budgets in P3, P4, and P5 are guesses until each PR's probe measures trunk.
- Whether `SelectionMiddleware` state survives into declarative subagents. P2 adds a test.

## Appendix B. Alternatives rejected

- LangSmith OTel as the trace emitter lost to the Langfuse handler with an OTLP exporter. The LangSmith path needs `LANGSMITH_TRACING=true` on top of the documented flags, stamps every `LANGSMITH_*` variable into span metadata, and has no masking hook. Langfuse already emits OTel spans, so one emitter feeds both the collector and Langfuse.
- A collector that routes many tenants by attribute lost to one collector per tenant compose project. The report asks for hard walls between tenants, and separate processes give that wall without routing rules.
- Keeping the selection cache on the middleware instance lost to agent state. The instance cache is shared across tenants in a long-lived process, falls back to `"_default"`, and is lost on restart. State is per thread, persisted, and encrypted.
- `FilesystemPermission(mode="interrupt")` on `/org/` writes is deferred to Phase 1 with HITL. Phase 0b uses `mode="deny"`, because nothing in Phase 0b answers an interrupt yet.
- A separate `agentkit-contracts` workspace package lost to a root `contracts/` directory with markers. The suite ships no library code.
- Per-tenant harness profiles are not possible, because `register_harness_profile` is process-global. Tenant policy lives in middleware that reads `runtime.context`.
- Pruning by raw SQL lost to `adelete_thread`, which exists in the installed saver.

## Appendix C. Risks

- `control-cli`, `/deslop`, and `asciinema` are not installed. Lanes drive the CLI with `Bash` and `script`, P2 and P4 use the macOS screen recorder for their videos, and `pstack:comment-sicko` stands in for `/deslop`. P1 through P6 owners record each substitution.
- Checkpoint metadata is plaintext. Owners in P3 and P5 keep secrets and user content out of `metadata`.
- Advisory locks pin a connection per running thread. The P3 owner watches lane 9 for pool exhaustion.
- `prune` reads `ts` from checkpoint JSON, an internal field. P1's contract suite pins it in the `pg` contract.
- deepagents ships about 15 releases a month. The P1 canary is the early warning, and owners do not bump pins inside this program.
- T9 is not part of this plan. Phase 0 is not complete until T9 passes.
- The existing `b2blocal-postgres` and `b2blocal-redis` containers belong to another project. Every owner uses compose project names that start with `agentkit-`, and never stops other containers.

## Appendix D. Links and reading list

- `reports/Reusable agent platform components.md`, the sections on the factory, hard walls between tenants, the roadmap, and risks.
- `docs/superpowers/specs/2026-11-01-agentkit-phase0-design.md` and `docs/superpowers/plans/2026-11-01-agentkit-phase0-plan.md`.
- P2, P3, and P5 run the `architect` skill against the Appendix E shapes before implementing. P5 runs the `interrogate` skill on the emitter choice in Appendix B before its code-ready head.
- The decision trail stays local per the `show-me-your-work` skill, under the session scratchpad.

## Appendix E. Data shapes

These sketches are the contract each owner implements. A deviation is reported, not absorbed.

```python
# agentkit_core/context.py
Label = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9_-]{0,62}$")]
Scope = Literal["user", "global"]

class PlatformContext(BaseModel):
	model_config = ConfigDict(frozen=True)
	tenant: Label
	product: Label
	team: Label
	user_id: Label
	thread_id: str
	agent_name: Label
	agent_version: str

def store_namespace(ctx: PlatformContext, scope: Scope, kind: Label) -> tuple[str, ...]:
	owner = ctx.user_id if scope == "user" else "global"
	return (ctx.tenant, ctx.product, ctx.team, owner, kind)

# agentkit_persistence/open.py
class PersistenceSettings(BaseSettings):
	database_url: SecretStr
	langgraph_aes_key: SecretStr
	pool_max_size: int = 10
	lock_pool_max_size: int = 20
	store_default_ttl_minutes: int | None = None

@dataclass(frozen=True)
class Persistence:
	pool: AsyncConnectionPool
	lock_pool: AsyncConnectionPool
	saver: AsyncPostgresSaver
	store: AsyncPostgresStore

@asynccontextmanager
async def open_persistence(settings: PersistenceSettings) -> AsyncIterator[Persistence]: ...

@asynccontextmanager
async def thread_lock(p: Persistence, thread_id: str) -> AsyncIterator[None]: ...

async def prune(p: Persistence, older_than: timedelta) -> int: ...

# agentkit_telemetry
def configure_tracing(settings: TelemetrySettings) -> Langfuse | None: ...
def run_config(ctx: PlatformContext, prompt_hash: str, ledger: CostLedger) -> RunnableConfig: ...

@dataclass(frozen=True)
class UsageRow:
	tenant: str
	thread_id: str
	run_id: UUID
	model: str
	input_tokens: int
	output_tokens: int
	cached_input_tokens: int
	decisions_input_tokens: int
	decisions_output_tokens: int
```
