# agentkit Phase 0b — execution plan (in-session)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Deliver Phase 0b: a validated tenant context on every run, encrypted Postgres persistence with resumable threads and memory tiers, per-tenant tracing plus a cost ledger, and per-tenant deployment stamps.

**Architecture:** Same design as the source plan, adapted to the declarative loader that landed after the source plan was written.

**Source plan (the design authority):** `docs/superpowers/plans/2026-11-01-agentkit-phase0b-plan.md`. Each task below implements one of its PR sections. The **Files**, **Build**, **You see** and **Verify, unit** blocks, plus Appendix A (prototype evidence) and Appendix E (data shapes), are binding unless this document changes them.

**Execution mode (operator's call, 2026-11-02):** in-session subagent-driven development on one branch, `phase0b`. The source plan's program checklist does not apply here. That covers stacked PRs, owners, swarms, ten live lanes, Bugbot, review gates with screenshots or video, and `/loop` ticks. Each task gets one implementer and one task reviewer, and a final whole-branch review closes the program. The operator merges to `main` at the end.

## Global Constraints

- uv workspace, Python 3.12, mypy strict, ruff line length 100. Pins live only in `constraints.txt`. All nine new pins from P1 were verified on PyPI on 2026-11-02.
- Live LLM runs use only the `fireworks-glm` registry entry, once each and only where a task says so. Web search defaults to DuckDuckGo.
- Postgres for tests and local checks comes from `deploy/compose.dev.yaml`, run as compose project `agentkit-dev` with `AGENTKIT_PG_PORT=55432`. Never touch containers this program did not start; `b2blocal-*` belong to another project. Tear the project down when a task finishes.
- `pg` tests skip with a reason that names `AGENTKIT_TEST_DATABASE_URL` when it is unset. `make test` stays green with no Postgres running.
- Single responsibility per module, about 200 lines or fewer. `spec/` in agentkit-config stays free of framework imports.
- Never commit `.env`, `deploy/tenants/*.env` (other than `example.env`), logs, or the untracked root `report.md`. Commits end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- The repo is public. Use "tenant" wording and keep client names out.

### Adaptations to the declarative loader (binding)

- **A1. Context reaches every entry point.** `PlatformContext` is a per-run value passed to `graph.ainvoke(..., context=ctx)`. `build_deep_agent` always passes `context_schema=PlatformContext` and puts `TenantGuardMiddleware` first. `load_agent` needs no new argument, because it calls `build_deep_agent`. The flow compiler compiles its `StateGraph` with `context_schema=PlatformContext`, and agent nodes forward `runtime.context` to the inner agent's `ainvoke`.
- **A2. `BuildContext` gains `platform: PlatformContext | None = None`.** It is build-time only, and nothing requires it yet.
- **A3. Default tenant.** `Settings.deployment_tenant` reads `AGENTKIT_TENANT` and defaults to `"default"`. `research --tenant` and `research-eval --tenant` also default to `"default"`, so local runs work with no environment variables. `--user` defaults to `"local"`, and `product`/`team` default to `"agentkit"`/`"platform"`. `agent_name` and `agent_version` come from the loaded spec.
- **A4. Persistence is opt-in on the CLIs.** Both `research` and `research-eval` take `--persist`, which needs `DATABASE_URL` and `LANGGRAPH_AES_KEY`. Under `--persist`, every turn runs inside `thread_lock`, and `--thread <id>` resumes. Without `--persist`, `--thread` is rejected with a clear error. This replaces the source plan's "every `research` turn inside `thread_lock`", so the CLI keeps working without Docker.
- **A5. Skills route.** `memory_backend()` absorbs `agentkit_deep.skills_mount`'s routes: `/skills/<owner>/` becomes one more route in the same `CompositeBackend`, and the `/skills/**` write-deny is kept. `resolve.py` passes the skills routes in, rather than building a second composite, whenever persistence is on.
- **A6. `/report.md`** stays on the default `StateBackend` route, so `read_output` keeps working.
- **A7. Live verification is reduced.** Each task's implementer runs the checks listed under the task's **Live checks** below, against `agentkit-dev`, and pastes the outputs into its report. The source plan's ten lanes are not run.
- **A8. Perf rules.** Each rule from the source plan is measured once, with a small Python timing script, since `hyperfine` is not installed. The result is recorded in the report. A breach is reported as a concern, not silently accepted, and the controller rules on it.
- **A9. Missing tools.** `shellcheck` and `act` are not installed. `make lint` runs `shellcheck` only when it is present, and prints a skip line otherwise. The canary workflow is checked by running its steps by hand.

---

### Task 1: Contract suite (source plan P1)

Implement the source plan's section "Pin the upstream APIs with a contract suite (P1)": Files, Build, You see, Verify unit. That includes proving that three contracts can fail, with red output pasted into the report.
**Live checks:** `uv run pytest contracts -m contract -v` under `HTTPS_PROXY=http://127.0.0.1:9`; `uv run pytest contracts -m pg -v` against `agentkit-dev` (create `deploy/compose.dev.yaml` here, as specified in P3, because the pg contracts need it); the same with `AGENTKIT_TEST_DATABASE_URL` unset shows skips naming the variable; the concurrency contract passes 10 times in a loop; a grep for `inspect.signature` in `contracts/` finds nothing.
**Perf:** contract suite under 60 s; `make test` within 1.5× of its time before the task.

### Task 2: Tenant context (source plan P2, plus A1–A3)

Implement "Carry a validated tenant context through every run (P2)", with A1, A2 and A3. The research CLI and eval CLI changes apply to the current `cli.py`/`eval_cli.py` and `agent.py` helpers (`add_agent_args`, `overrides_from`). `scripts/smoke.py` builds its agent through `build_deep_agent` on `ScriptedChatModel`. Add a test that a flow's agent node receives the flow's `PlatformContext` (A1). Add a test that `SelectionMiddleware` state works for declarative subagents; the source plan's Appendix A lists this as unproven.
**Live checks:** source lanes 2, 3, 4, 5, 6 and 8, run through `scripts/smoke.py`, `research --help` and grep. No real-model run here.
**Perf:** 200 scripted runs, head median within 1.05× of the run before the task.

### Task 3: Encrypted persistence package (source plan P3)

Implement "Persist threads and memory in encrypted Postgres (P3)" (`agentkit-persistence`, `open_persistence`, `thread_lock`, `prune`, `agentkit-prune`, compose file if Task 1 did not finish it).
**Live checks:** source lanes 2, 3, 4, 5, 6, 7, 8 and 9 against `agentkit-dev`.
**Perf:** p50 per super-step at most 15 ms over the run before the task; ten-step p95 at most 200 ms over.

### Task 4: Memory tiers and resumable research (source plan P4, plus A4–A6)

Implement "Wire persistence and memory tiers into the factory and the research agent (P4)", with A4, A5 and A6.
**Live checks:** source lanes 2, 3, 4, 5, 6, 7, 8 and 9 against `agentkit-dev`, all with scripted models.
**Perf:** a scripted ten-step run with `--persist` adds at most 300 ms to the median.

### Task 5: Tracing and cost ledger (source plan P5)

Implement "Trace every run to its tenant and record its cost (P5)". The local collector is the `otel/opentelemetry-collector-contrib` container with a file exporter, run in compose project `agentkit-dev`. Langfuse keys are absent, so Langfuse forwarding stays configured-but-off.
**Live checks:** source lanes 2, 3, 4, 5, 6, 7, 8 and 9.
**Perf:** head median at most 5% plus 20 ms over the run before the task.

### Task 6: Per-tenant stamps and Phase 0 exit (source plan P6)

Implement "Stamp one isolated deployment per tenant and prove the exit criterion (P6)", with A9.
**Live checks:** source lanes 2, 3, 4, 5, 6, 7, 8 and 10. Tear down `agentkit-tenant-a` and `agentkit-tenant-b` afterwards.
**Perf:** cold stamp under 60 s with cached images; `make phase0-exit` under 5 minutes.

### Task 7: One real run on fireworks-glm, and close-out

With `tenant-a` stamped: `uv run research "What is the Model Context Protocol?" --model fireworks-glm --tenant tenant-a --persist`, then a follow-up turn with `--thread <id>`. Pass when both turns write a cited report, the second prints `resumed thread`, the tenant-a collector file holds the run's spans, and `agentkit_usage` holds both rows. Record the results in `docs/phase0-results.md` under "Phase 0b close-out, 2026-11-02". Update the README Status and the CLAUDE.md current-work line: Phase 0 is complete, and the next step is the verification skill and then Phase 1. Tear down every `agentkit-*` compose project this program started.
