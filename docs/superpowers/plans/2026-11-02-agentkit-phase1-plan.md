# agentkit Phase 1: Standard Middleware Stack + Eval Gates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every YAML agent a standard, canonically ordered middleware stack (model fallback, model
retry, tool retry, model/tool call limits, PII redaction), and turn `research-eval` into a regression
gate over a 25-case golden set with deterministic, trajectory and cost metrics against a committed
baseline.

**Architecture:** New middleware factories in `agentkit-middleware` wrap LangChain v1's built-in
middleware and register as `agentkit.middleware` entry points, so YAML references them by `type`.
`agentkit_config.resolve` stops using file order and sorts middleware into one canonical stack, with
Decisions selection in its fixed slot. `agentkit-evals` gains richer cases, trajectory capture, a gate
spec and a baseline file. `research-eval --gate` exits non-zero on a regression.

**Tech Stack:** Python 3.12, uv workspace, langchain 1.4.7 (`langchain.agents.middleware`),
deepagents 0.7.32, pydantic, pytest + respx, openevals judge.

**Spec:** No separate spec. This plan argues from the roadmap's Phase 1 row in
`reports/Reusable agent platform components.md` ("Phased roadmap") and from the gap noted in
`docs/architecture.md` section 4 ("canonical platform middleware list ... The code enforces only the
guard's position"). Decisions that spec would have held are listed below under **Decisions**.

## Global Constraints

- uv workspace, Python 3.12, versions pinned in `constraints.txt`; run tests with `uv run --no-sync pytest`
  after `make sync` (macOS hides `.pth` files otherwise).
- No new third-party dependencies. Everything here uses installed `langchain.agents.middleware`.
- Live runs of the research agent use **fireworks-glm only**. The judge stays `--judge anthropic`
  (registry `strong` tier, which is now `claude-opus-5-5`).
- Public repo: say "tenant", never name clients. Never commit `.env`.
- `make lint` (ruff, ruff format, mypy, `agentkit validate`) must pass at every commit.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Decisions

1. **Canonical order** (outermost first, after the factory-owned `TenantGuardMiddleware`):
   `selection` → `model_fallback` → `model_retry` → `tool_retry` → `call_limit` → `tool_call_limit` →
   `pii` → any other pool middleware, in file order. Reason: selection overrides the request's model,
   so fallback must be inside it to swap the model on failure. Retry sits inside fallback, so each
   model is retried before the next one is tried.
2. **`model_retry` raises after its last attempt** (`on_failure="error"`, unlike LangChain's default
   `"continue"`), or fallback would never see the failure.
3. **Shipped tools keep returning errors as text** (`ERROR: ...`), so `tool_retry` never fires for
   `web_search`/`fetch_url`. `tool_retry` exists for pool tools that raise. Changing shipped tools to
   raise would crash any agent built without the middleware (LangChain's ToolNode re-raises non-validation
   errors), including DeepAgents' general-purpose subagent, which gets no user middleware.
4. **Fallback models are registry entries**, written `entry` or `entry:tier` (default tier `default`),
   resolved with `ModelRegistry.default()` and built with `get_model` at build time. So a missing key is
   a `ConfigError` at load, not a runtime surprise.
5. **Stack is opt-in per YAML file**, with no implicit defaults. `agentkit validate` warns
   (`no call_limit; a runaway loop is unbounded`) when an Agent lacks `call_limit`. The research agent
   and `researcher` subagent opt in.
6. **Golden set** = the 10 smoke cases + 15 new ones (25, within the roadmap's 20–50), in
   `apps/research_agent/evals/golden.jsonl`. `smoke.jsonl` stays as the quick set.
7. **Gate = absolute floors + max drop from a committed baseline.** The baseline records the dataset
   SHA-256 and the agent and judge model ids. A gate run against a baseline that differs on any of those
   refuses to compare (exit 2) rather than reporting a false pass or fail.
8. **Deferred (not in this plan):** single-step evals, a pytest plugin, k-trial pass^k, judge TPR/TNR
   cards, built-in transient retry inside shipped tools.

## Review Focus

1. **Retry swallowing the failure:** an agent with `model_fallback` + `model_retry` whose primary
   always errors must answer from the fallback model, not with a "continue" error message (Task 2 test
   `test_retry_then_fallback_answers_from_fallback`).
2. **Selection plus fallback:** with `selection: decisions` and a failing tier model, the fallback
   model answers, which only works if fallback is inside selection (Task 2
   `test_fallback_inside_selection`).
3. **PII redaction eating citations:** `pii` must refuse `type: url` (a redacted URL breaks
   `citation_validity`); validate errors on it (Task 1 `test_pii_rejects_url_type`).
4. **Stale baseline:** a baseline recorded with the old Haiku judge, another model, or an edited
   dataset must not be compared (Task 5 `test_gate_refuses_mismatched_baseline`).
5. **Errored cases hiding a regression:** a case that errors drops out of the score means, so means can
   rise while a case breaks. The gate must also fail when a case that completed in the baseline errors
   now (Task 5 `test_gate_fails_on_newly_errored_case`).

---

### Task 1: Middleware factories

**Files:**
- Modify: `packages/agentkit-middleware/src/agentkit_middleware/factories.py`
- Modify: `packages/agentkit-middleware/pyproject.toml` (entry points)
- Test: `packages/agentkit-middleware/tests/test_factories.py`

**Interfaces:**
- Consumes: `BuildContext(settings, spec, name)`, `ModelRegistry.default().resolve(entry, tier)`,
  `get_model(spec, settings)` from `agentkit_core`.
- Produces (all `(ctx: BuildContext, **params) -> AgentMiddleware`, entry-point names in backticks):
  - `call_limit(ctx, *, max_model_calls: int, thread_limit: int | None = None, exit_behavior: Literal["end","error"] = "end")` → `ModelCallLimitMiddleware(run_limit=max_model_calls, thread_limit=..., exit_behavior=...)`. Keeps the existing `max_model_calls` name.
  - `tool_call_limit(ctx, *, run_limit: int, tool_name: str | None = None, thread_limit: int | None = None)` → `ToolCallLimitMiddleware(..., exit_behavior="continue")`
  - `model_fallback(ctx, *, models: list[str])` → `ModelFallbackMiddleware(first, *rest)`; `models` non-empty, items `entry` or `entry:tier`.
  - `model_retry(ctx, *, max_retries: int = 2, initial_delay: float = 1.0, max_delay: float = 30.0)` → `ModelRetryMiddleware(..., on_failure="error", jitter=True)`
  - `tool_retry(ctx, *, max_retries: int = 2, tools: list[str] | None = None, initial_delay: float = 1.0, max_delay: float = 30.0)` → `ToolRetryMiddleware(..., on_failure="continue")`
  - `pii(ctx, *, type: str, strategy: Literal["block","redact","mask","hash"] = "redact", apply_to_input: bool = True, apply_to_output: bool = False, apply_to_tool_results: bool = False)` → `PIIMiddleware(type, ...)`. `type` in `{"email","credit_card","ip","mac_address"}`; `"url"` raises `ConfigError("pii type 'url' would redact citations; not allowed")`.
  - Every bad param raises `agentkit_core.ConfigError` (validate reports factory errors through the existing `_middleware_errors` path).

- [ ] **Step 1: Write the failing tests** in `test_factories.py`:
  `test_call_limit_passes_thread_limit_and_exit_behavior`, `test_tool_call_limit_builds`,
  `test_model_fallback_resolves_entries_and_tiers` (`models=["fireworks-deepseek", "anthropic:strong"]`
  with a `Settings(_env_file=None, fireworks_api_key="f", anthropic_api_key="a")`; assert
  `isinstance(mw, ModelFallbackMiddleware)` and the two built models' `model_name`s are the registry ids
  `accounts/fireworks/models/deepseek-v4p1-flash-1017` and `claude-opus-5-5`),
  `test_model_fallback_missing_key_is_config_error`, `test_model_fallback_rejects_empty_and_bad_tier`,
  `test_model_retry_raises_on_final_failure` (assert `mw.on_failure == "error"`),
  `test_tool_retry_builds`, `test_pii_builds_per_type` (assert `mw.name == "PIIMiddleware[email]"`),
  `test_pii_rejects_url_type`, `test_pii_rejects_unknown_type`.
- [ ] **Step 2: Run** `uv run --no-sync pytest packages/agentkit-middleware/tests/test_factories.py -v`. Expected: FAIL (import errors for the new factories).
- [ ] **Step 3: Implement the factories** with the signatures above. Keep the existing `# type: ignore[assignment]` pattern for the generic-middleware mypy mismatch.
- [ ] **Step 4: Register entry points** `tool_call_limit`, `model_fallback`, `model_retry`, `tool_retry`, `pii` under `[project.entry-points."agentkit.middleware"]`, then `make sync`.
- [ ] **Step 5: Run** the test file. Expected: PASS. Also `uv run --no-sync python -c "from agentkit_config import CodePools; print(sorted(CodePools.from_entry_points().middleware.names()))"` lists all six.
- [ ] **Step 6: Commit** `feat(middleware): fallback, retry, tool limits and PII factories`.

### Task 2: Canonical stack order in resolve, plus validation

**Files:**
- Create: `packages/agentkit-config/src/agentkit_config/stack.py`
- Modify: `packages/agentkit-config/src/agentkit_config/resolve.py:42-46,107-118` (`_middleware`, selection append), `resolve.py:79` (subagents)
- Modify: `packages/agentkit-config/src/agentkit_config/validate.py` (`_middleware_errors`, Agent checks)
- Test: `packages/agentkit-config/tests/test_stack.py`, `packages/agentkit-config/tests/test_validate.py`

**Interfaces:**
- Consumes: Task 1 factory type names.
- Produces:
  - `STACK_ORDER: tuple[str, ...] = ("selection", "model_fallback", "model_retry", "tool_retry", "call_limit", "tool_call_limit", "pii")` in `stack.py`.
  - `order_stack(items: list[tuple[str, AgentMiddleware]]) -> list[AgentMiddleware]`: stable sort by `STACK_ORDER.index(type)`, unknown types after all known ones in input order.
  - `SINGLETONS = {"selection", "model_fallback", "model_retry", "tool_retry", "call_limit"}`: validate errors `duplicate middleware 'model_retry'` on a second enabled one. `pii` may repeat with different `type`; `tool_call_limit` may repeat with different `tool_name`. A repeat of the same key is an error (LangChain rejects duplicate middleware names).
  - Validate warning constant `NO_CALL_LIMIT = "no call_limit; a runaway loop is unbounded"` on Agent specs (not subagents) without an enabled `call_limit`.
  - `resolve_agent` builds `[("selection", decisions_mw)]` when `selection: decisions` and passes the combined list through `order_stack`. Subagent middleware goes through `order_stack` too.

- [ ] **Step 1: Write the failing unit tests** in `test_stack.py`: `test_order_stack_canonical` (input
  `pii, call_limit, model_fallback, custom_a, selection, model_retry, custom_b` → output
  `selection, model_fallback, model_retry, call_limit, pii, custom_a, custom_b`), `test_order_stack_is_stable_for_repeats` (two `pii` keep file order).
- [ ] **Step 2: Write the failing behaviour tests** (scripted models from `agentkit_deep.testing`; build
  through `load_agent` with a tmp YAML and `CodePools.from_entry_points().override(middleware=...)` so
  `model_fallback` returns `ModelFallbackMiddleware(scripted(AIMessage("from fallback")))`):
  - `test_retry_then_fallback_answers_from_fallback`: primary is a `ScriptedChatModel` subclass whose `_agenerate` always raises `RuntimeError("boom")`; YAML lists `model_retry` (`max_retries: 1, initial_delay: 0`) before `model_fallback` in the *reverse* of canonical order; the final AI message is `"from fallback"`, and the primary saw 2 calls.
  - `test_fallback_inside_selection`: a stub `Selector` returning tier `strong`, with `models={"strong": <failing model>}`, plus `model_fallback`. Final answer `"from fallback"`.
  - `test_yaml_file_order_no_longer_matters`: same agent with entries shuffled builds the same middleware class sequence (`[type(m).__name__ for m in kwargs["middleware"]]`).
- [ ] **Step 3: Write the failing validate tests** in `test_validate.py`: `test_duplicate_singleton_middleware_is_error`, `test_two_pii_types_ok_same_type_error`, `test_agent_without_call_limit_warns`, `test_subagent_without_call_limit_does_not_warn`.
- [ ] **Step 4: Run** `uv run --no-sync pytest packages/agentkit-config -v`. Expected: the new tests FAIL.
- [ ] **Step 5: Implement** `stack.py` and wire it into `resolve.py` and `validate.py`.
- [ ] **Step 6: Run** `uv run --no-sync pytest -q` (full suite). Expected: PASS, including `apps/research_agent/tests/test_review_flow.py` (which monkeypatches `decisions_middleware`; the spy must still be the outermost user middleware).
- [ ] **Step 7: Update `docs/architecture.md`**: replace "the pool entries in file order, then `SelectionMiddleware` last" (section 4 table) with the canonical order and its reason, add the six middleware types to the Extending / pools section, and narrow the section 4 **Gap** to what remains (prompt composer, general-purpose subagent).
- [ ] **Step 8: Commit** `feat(config): canonical middleware stack order and validation`.

### Task 3: Research agent opts into the stack

**Files:**
- Modify: `apps/research_agent/agent.yaml`, `libraries/subagents/researcher.yaml`
- Modify: `apps/research_agent/tests/fixtures/python_build_snapshot.json` (regenerate)
- Test: `apps/research_agent/tests/test_agent.py`

**Interfaces:**
- Consumes: Task 1 types, Task 2 ordering.
- Produces: shipped YAML:
  - `agent.yaml` `middleware:` `model_fallback {models: ["fireworks-glm:strong"]}` (glm-5p3: a different deployment of the same family, so live runs stay glm-only), `model_retry {max_retries: 2}`, `call_limit {max_model_calls: 60}`, `tool_call_limit {run_limit: 40}`, `pii {type: email}`, `pii {type: credit_card, strategy: mask}` (input only).
  - `researcher.yaml` `middleware:` `model_retry {max_retries: 2}`, `call_limit {max_model_calls: 30}`, `tool_call_limit {run_limit: 25}`.

- [ ] **Step 1: Write the failing test** `test_shipped_agent_has_standard_stack`: load `DEFAULT_AGENT` with a scripted model and fake keys; assert the middleware class names after the guard are, in order, `SelectionMiddleware, ModelFallbackMiddleware, ModelRetryMiddleware, ModelCallLimitMiddleware, ToolCallLimitMiddleware, PIIMiddleware, PIIMiddleware`; the researcher subagent dict has `ModelRetryMiddleware, ModelCallLimitMiddleware, ToolCallLimitMiddleware`.
- [ ] **Step 2: Run it.** Expected: FAIL.
- [ ] **Step 3: Edit both YAML files** as above.
- [ ] **Step 4: Regenerate the snapshot**: `UPDATE_SNAPSHOT=1 uv run --no-sync pytest apps/research_agent/tests/test_snapshot.py`, review the diff (only middleware entries change), then rerun without the flag. Expected: PASS.
- [ ] **Step 5: Run** `make lint`. Expected: `agentkit validate` shows no `NO_CALL_LIMIT` warning for the research agent.
- [ ] **Step 6: Commit** `feat(research_agent): standard middleware stack`.

### Task 4: Richer cases, trajectory capture and new metrics

**Files:**
- Modify: `packages/agentkit-evals/src/agentkit_evals/dataset.py`, `metrics.py`, `runner.py`, `__init__.py`
- Modify: `apps/research_agent/src/research_agent/progress.py` (`run_with_progress`), `eval_cli.py` (`run_agent`)
- Create: `apps/research_agent/evals/golden.jsonl`
- Test: `packages/agentkit-evals/tests/test_evals.py`, `apps/research_agent/tests/test_progress.py`

**Interfaces:**
- Produces:
  - `EvalCase` adds `tags: list[str] = []`, `expect_tools: list[str] = ["web_search"]`, `min_sources: int = 1`. Existing `smoke.jsonl` lines stay valid.
  - `RunResult` adds `tool_calls: list[str] = field(default_factory=list)` (tool names in call order, orchestrator and subagents) and `latency_s: float | None = None`. `CaseResult` adds `latency_s` and `tool_calls`.
  - `metrics.sources_section(report: str) -> float`: 1.0 if a line matching `^#{1,6}\s*Sources\b` (case-insensitive) exists.
  - `metrics.source_count_ok(report: str, min_sources: int) -> float`: 1.0 if `len(extract_urls(report)) >= min_sources`.
  - `metrics.tool_recall(expected: list[str], called: list[str]) -> float`: `|set(expected) ∩ set(called)| / |set(expected)|`, 1.0 when `expected` is empty.
  - `_one` adds these three to `scores`. `aggregate` adds `mean_latency_s` and `mean_total_tokens` (from `usage["input_tokens"] + usage["output_tokens"]`, over cases that have usage) when present.
  - `run_with_progress(..., tool_calls: list[str] | None = None)`: appends `tc["name"]` for every AI tool call in any namespace.
- [ ] **Step 1: Write the failing tests**: `test_case_defaults_keep_smoke_valid` (load `smoke.jsonl`), `test_sources_section`, `test_source_count_ok`, `test_tool_recall` (`(["web_search","fetch_url"], ["task","web_search"]) == 0.5`), `test_run_eval_adds_trajectory_scores`, `test_aggregate_latency_and_tokens`, and in `test_progress.py` `test_run_with_progress_collects_tool_call_names_from_subagents`.
- [ ] **Step 2: Run** them. Expected: FAIL.
- [ ] **Step 3: Implement**, and have `eval_cli.run_agent` pass `tool_calls=` and time the run with `time.monotonic()`.
- [ ] **Step 4: Write `golden.jsonl`**: the 10 smoke lines (adding `tags`), plus these 15, each with `expect_tools: ["web_search"]` unless noted:

  | id | question | must_cover | notes |
  |---|---|---|---|
  | pgvector-hnsw | How do you configure an HNSW index in pgvector, and which parameters trade recall for speed? | m, ef_construction, ef_search | expect_tools + fetch_url |
  | otel-genai | What do the OpenTelemetry GenAI semantic conventions define for LLM calls? | span attributes, token usage, model name | expect_tools + fetch_url |
  | react-pattern | What is the ReAct prompting pattern and what are its limitations? | interleaved reasoning and acting, tool calls, error compounding | |
  | speculative-decoding | How does speculative decoding speed up LLM inference? | draft model, verification by the target model, acceptance rate | |
  | quantization | What are the tradeoffs of 4-bit quantization for serving LLMs? | memory savings, accuracy loss, throughput | |
  | structured-output | How do LLM APIs guarantee structured JSON output, and where can it still fail? | JSON schema, constrained decoding, refusals or truncation | |
  | rag-eval | How are retrieval-augmented generation systems evaluated? | faithfulness, context relevance, answer relevance | |
  | agent-memory | What kinds of long-term memory do LLM agents use, and how are they stored? | episodic, semantic, vector store | |
  | pii-llm | What techniques reduce leakage of personal data in LLM applications? | redaction, access control, data retention | |
  | model-routing | Why and how do production LLM systems route between multiple models? | cost, latency, fallback on failure | |
  | mcp-false-premise | Why did the Model Context Protocol replace HTTP in 2024? | corrects the false premise, MCP runs over transports such as stdio and HTTP | tags [false-premise] |
  | postgres-rls | How does PostgreSQL row-level security work, and what are its pitfalls for multi-tenant apps? | policies, table owners and BYPASSRLS skip policies, performance | |
  | tokenization | Why do LLMs struggle with character-level tasks like counting letters in a word? | tokenization, subword units, workarounds | |
  | moe | What is a mixture-of-experts model, and why is it cheaper to serve per token? | router, sparse activation, total vs active parameters | |
  | circuit-breaker | What is the circuit breaker pattern, and how does it differ from retry with backoff? | closed/open/half-open states, failing fast, backoff with jitter | min_sources 2 |
- [ ] **Step 5: Run** `uv run --no-sync pytest packages/agentkit-evals apps/research_agent -q` and `uv run --no-sync python -c "from agentkit_evals import load_dataset; print(len(load_dataset('apps/research_agent/evals/golden.jsonl')))"`. Expected: PASS, `25`.
- [ ] **Step 6: Commit** `feat(evals): golden set, trajectory and source metrics`.

### Task 5: Gate spec, baseline and comparison

**Files:**
- Create: `packages/agentkit-evals/src/agentkit_evals/gates.py`
- Create: `apps/research_agent/evals/gates.yaml`
- Modify: `packages/agentkit-evals/src/agentkit_evals/__init__.py`
- Test: `packages/agentkit-evals/tests/test_gates.py`

**Interfaces:**
- Produces:
  - `MetricGate(BaseModel)`: `min: float | None`, `max: float | None`, `max_drop: float | None` (absolute, vs baseline), `max_rise: float | None` (relative, e.g. `0.30` = +30%).
  - `GateSpec(BaseModel)`: `baseline: Path` (relative to the gates file), `min_cases: int`, `metrics: dict[str, MetricGate]`. `load_gates(path) -> GateSpec`.
  - `Baseline(BaseModel)`: `dataset_sha256: str`, `model_id: str`, `judge_model_id: str`, `aggregate: dict[str, float]`, `completed_cases: list[str]`, `recorded: str` (ISO date). `Baseline.from_summary(summary: dict, dataset_path: Path) -> Baseline`; `dataset_sha256(path) -> str` (SHA-256 of the file bytes).
  - `GateFailure(metric: str, detail: str)` dataclass; `BaselineMismatch(ValueError)`.
  - `check_gates(spec: GateSpec, baseline: Baseline, summary: dict, dataset_path: Path) -> list[GateFailure]`: raises `BaselineMismatch` naming the field when the dataset hash, `model_id` or `judge_model_id` differ; a case count `< min_cases` is a failure; a metric missing from the run is a failure; each case in `baseline.completed_cases` that now has an error is a failure (`metric="completed"`, detail names the case).
  - `summary` (from `eval_cli.evaluate`) gains `model_id` and `judge_model_id` (registry ids) and `dataset`.
  - `gates.yaml`:
    ```yaml
    baseline: baseline.json
    min_cases: 20
    metrics:
      completed: {min: 0.96}
      has_citation: {min: 0.96}
      sources_section: {min: 0.9}
      citation_validity: {min: 0.85, max_drop: 0.05}
      completeness: {min: 0.85, max_drop: 0.05}
      groundedness: {min: 0.55, max_drop: 0.10}
      tool_recall: {min: 0.9}
      mean_total_tokens: {max_rise: 0.30}
    ```
- [ ] **Step 1: Write the failing tests**: `test_gate_passes_within_tolerance`, `test_gate_fails_below_floor`, `test_gate_fails_on_drop_vs_baseline`, `test_gate_fails_on_token_rise`, `test_gate_fails_below_min_cases`, `test_gate_fails_on_missing_metric`, `test_gate_fails_on_newly_errored_case`, `test_gate_refuses_mismatched_baseline` (parametrized over dataset edit, model id, judge id), `test_baseline_from_summary_round_trips`.
- [ ] **Step 2: Run** `uv run --no-sync pytest packages/agentkit-evals/tests/test_gates.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** `gates.py`, export the names, and write `gates.yaml`.
- [ ] **Step 4: Run** the tests. Expected: PASS.
- [ ] **Step 5: Commit** `feat(evals): regression gates against a committed baseline`.

### Task 6: `research-eval --gate` and `--write-baseline`

**Files:**
- Modify: `apps/research_agent/src/research_agent/eval_cli.py`
- Test: `apps/research_agent/tests/test_agent.py` (next to `test_eval_mints_one_thread_per_case`, reusing the `offline_cli` fixture)

**Interfaces:**
- Consumes: Task 5 `load_gates`, `check_gates`, `Baseline`, `BaselineMismatch`.
- Produces CLI behaviour:
  - `--gate PATH`: after writing `--out`, load the gates, compare, and print a `gate:` block (`gate: PASS` or one `gate: FAIL <metric>: <detail>` line per failure). Exit 1 on any failure; `BaselineMismatch` prints `gate: baseline mismatch: <field>` and exits 2. A missing baseline file also exits 2 with `run with --write-baseline first`.
  - `--write-baseline`: requires `--gate`; writes `Baseline.from_summary(...)` to the gate's `baseline` path and does not compare. Refuses (exit 2) if any case errored.
  - The default `--dataset` stays `smoke.jsonl`.
- [ ] **Step 1: Write the failing tests** (offline, scripted agent + a fake judge returning fixed scores):
  `test_eval_gate_pass_exits_0`, `test_eval_gate_regression_exits_1_and_names_metric`,
  `test_eval_gate_mismatch_exits_2`, `test_eval_write_baseline_then_gate_passes`,
  `test_eval_write_baseline_refuses_errored_case`.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement** the flags in `_main`.
- [ ] **Step 4: Run** `uv run --no-sync pytest -q` and `make lint`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(research-eval): --gate and --write-baseline`.

### Task 7: Live baseline, gate run, evidence and docs

**Files:**
- Create: `apps/research_agent/evals/baseline.json`
- Modify: `docs/architecture.md` (eval section 14.5, roadmap/known-issues 16.2), `docs/phase0-results.md` → add a Phase 1 section (or create `docs/phase1-results.md`), `CLAUDE.md` (current work line), `.claude/skills/verify-agentkit/` feature map (via `/pstack:maintain-verification-skill`)

- [ ] **Step 1: Record the baseline live**: `uv run research-eval --model fireworks-glm --dataset apps/research_agent/evals/golden.jsonl --judge anthropic --gate apps/research_agent/evals/gates.yaml --write-baseline --out evidence/phase1/baseline_run.md`. Expected: 25 cases, no errors, `baseline.json` written. If any case errors, fix or replace that case and rerun. Do not commit a baseline with errors.
- [ ] **Step 2: Check the floors against reality**: if the recorded aggregate is below a `gates.yaml` floor, lower that floor to (recorded − the metric's `max_drop`, or −0.05) and note the change in the results doc. Floors that no real run passes are noise.
- [ ] **Step 3: Gate run live**: the same command with `--gate` and without `--write-baseline`. Expected: `gate: PASS`, exit 0. Then prove the gate bites: rerun with `--no-selection`, or with a weakened prompt override and record whether it fails. Report either outcome honestly.
- [ ] **Step 4: Prove fallback live**: a scratch script calls `load_agent(DEFAULT_AGENT, model=init_chat_model("accounts/fireworks/models/does-not-exist", model_provider="fireworks", api_key=...), overrides={"selection": "off"})` and runs one short question. Expected: the answer arrives, and the ledger row's `model` lists `accounts/fireworks/models/glm-5p3`. Keep the transcript in the evidence folder.
- [ ] **Step 5: Run the `verify-agentkit` skill** on the branch, keeping evidence under `evidence/verify/<run-id>/`.
- [ ] **Step 6: Update docs** (architecture eval section: new metrics, gate, baseline; middleware stack; results doc with the baseline numbers and judge model; CLAUDE.md "Current work").
- [ ] **Step 7: Commit** `chore(evals): fireworks-glm golden baseline; Phase 1 docs`.
