# agentkit Phase 2 platform shape (P2-C audit, P2-B seams, P2-A guards) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Audit what of each model request is durably logged. Make search backends and secret resolvers
pluggable through entry points. Enforce tenant tool policy and side-effect policy on every tool call,
including calls made inside subagents.

**Architecture:** A recording callback plus an audit script compare provider-level requests against
checkpoints, the usage ledger and run metadata, and the findings go in a doc. A small `Seam` loader in
agentkit-core turns entry-point groups into provider lookups, filtered by tenant. A deny-only
`GuardMiddleware` in agentkit-middleware is always inserted by `build_deep_agent`: on the main agent,
on every declared subagent, and on an explicit `general-purpose` subagent.

**Tech Stack:** Python 3.12, uv workspace, LangChain v1 middleware (`wrap_tool_call`), deepagents 0.7.x,
`importlib.metadata` entry points, pydantic-settings, pytest (`asyncio_mode=auto`).

**Spec:** `docs/superpowers/specs/2026-11-03-agentkit-phase2-design.md` (sections P2-A, P2-B, P2-C, and
"Refinements after reading the code").

## Global Constraints

- Python `>=3.12,<3.13`; no new third-party dependencies (stdlib `importlib.metadata` only).
- Live runs use **fireworks-glm only** (`--model fireworks-glm`), against a throwaway stamped tenant.
- Wording: "tenant", never client names (public repo).
- Never commit `.env` or `deploy/tenants/*.env`.
- After editing any `pyproject.toml` entry points, run `uv sync` before tests (entry points are read from
  installed metadata).
- Error messages name variables and refs, never secret values.
- Defaults: `AGENTKIT_ALLOWED_SIDE_EFFECTS=read,external`; `auto` search order stays
  Parallel -> Brave -> Tavily -> DuckDuckGo.
- A denied tool call counts against `tool_call_limit` (decided with the user).

## Review Focus

1. **A deepagents upgrade adds a built-in tool** that is missing from `BUILTIN_TOOLS`. The guard would then
   deny it as unregistered and break every run. Pin it: Task 6 has a test that every tool name on a built
   agent (and its subagents) is either in `BUILTIN_TOOLS` or carries agentkit metadata.
2. **`AGENTKIT_ALLOWED_SIDE_EFFECTS` set in the repo `.env`.** Settings prefers `.env` over process env, so
   it would silently override every tenant stamp, just like `AGENTKIT_TENANT`. Pin it: Task 5 extends
   `tenant_env.sh`'s refusal to this variable, with a test.
3. **A malformed side-effects value** (e.g. `read, writ`) must be a startup `ConfigError` naming the bad
   value, not a silent deny-all. Pin it: Task 5 test.
4. **The explicit `general-purpose` subagent changes behavior.** It must keep the parent's tools and model
   and still appear in the `task` tool. Pin it: Task 6 test.
5. **A third-party search backend with the same name as a built-in** (e.g. `brave`). Expected: a
   `ConfigError` at load naming both entry points, never a silent shadowing. Pin it: Task 2 test.

---

### Task 1: P2-C audit (request capture + audit script + findings doc)

**Files:**
- Create: `packages/agentkit-evals/src/agentkit_evals/capture.py`
- Create: `packages/agentkit-evals/tests/test_capture.py`
- Create: `scripts/audit_model_visible.py`
- Create: `docs/phase2-model-visible-audit.md`
- Modify: `packages/agentkit-evals/src/agentkit_evals/__init__.py` (export the new names)

**Interfaces:**
- Produces:
  - `digest(messages: Sequence[BaseMessage]) -> str`: sha256 hex of
    `json.dumps([[m.type, m.content, getattr(m, "tool_calls", None), getattr(m, "tool_call_id", None)] for m in messages], sort_keys=True, default=str)`.
  - `@dataclass(frozen=True) class CapturedRequest`: `namespace: str` (metadata `checkpoint_ns`,
    `""` = main agent), `step: int | None` (metadata `langgraph_step`), `model: str | None`
    (invocation params `model` or `model_name`), `tools: tuple[str, ...]` (sorted names from
    invocation params `tools`), `system_sha: str | None` (sha256 of the system message text, or None),
    `messages_sha: str` (`digest` of the non-system messages), `message_count: int`.
  - `class RequestCapture(AsyncCallbackHandler)` with `records: list[CapturedRequest]`, filled in
    `on_chat_model_start`.

- [ ] **Step 1: Write the failing tests** in `test_capture.py`:
  - `test_capture_records_each_model_call`: build `build_deep_agent(model=scripted(tool_call("write_file", {"file_path": "/a.md", "content": "x"}, "1"), AIMessage(content="done")), system_prompt="p")`, invoke it with `config={"callbacks": [cap]}` and `context=ctx()`. Assert `len(cap.records) == 2`, every record has `namespace == ""`, and `cap.records[1].message_count > cap.records[0].message_count`.
  - `test_capture_reads_model_and_tools_from_invocation_params`: call `await cap.on_chat_model_start({}, [[SystemMessage("s"), HumanMessage("q")]], run_id=uuid4(), metadata={"checkpoint_ns": "", "langgraph_step": 3}, invocation_params={"model": "m-1", "tools": [{"type": "function", "function": {"name": "web_search"}}]})`. Assert the record is `model == "m-1"`, `tools == ("web_search",)`, `step == 3`, `system_sha == sha256("s")`, `message_count == 1`.
  - `test_digest_is_order_and_content_sensitive`: `digest([HumanMessage("a"), AIMessage("b")]) != digest([AIMessage("b"), HumanMessage("a")])`, and the same digest for equal lists.
- [ ] **Step 2: Run** `uv run pytest packages/agentkit-evals/tests/test_capture.py -v`. Expected: FAIL (ImportError).
- [ ] **Step 3: Implement `capture.py`.** Tool names come from `invocation_params["tools"]` entries (`t["function"]["name"]`, else `t["name"]`); a missing key gives `()`. Only the first message list of `messages` is read (chat models get one).
- [ ] **Step 4: Run** the tests again. Expected: PASS.
- [ ] **Step 5: Write `scripts/audit_model_visible.py`** (argparse: `--tenant`, `--question`, `--agent apps/research_agent/agent.yaml`, `--model fireworks-glm`, `--out evidence/audit/<run-id>/`). It runs one persisted turn the way `research_agent.cli.run` does (reuse `persistence_for`, `require_tenant`, `load_agent`, `platform_context`, `run_config`, `ledger_for`), adding `RequestCapture` to `config["callbacks"]`. Then:
  - Read `graph.aget_state_history({"configurable": {"thread_id": thread}})`.
  - For each main-agent capture, take the checkpoint whose `metadata["step"] == capture.step - 1`.
  - Compare, per field:
    - `messages_sha` vs `digest` of that state's `messages`;
    - `tools` vs `state["agentkit_selection"]["tools"] ∪ BUILTIN_TOOLS`;
    - `model` vs the model ids in that thread's `agentkit_usage` rows;
    - `system_sha` vs the run's `prompt_hash` (expected to differ: the hash covers pre-harness text only).
  - Count subagent captures (`namespace != ""`) and record them as "not in parent checkpoints".
  - Write `audit.json` (one object per capture: field -> `match | differs | not-recorded`) and `captures.jsonl`.
- [ ] **Step 6: Run it live.** `make stamp TENANT=audit-p2`, then
  `scripts/tenant_env.sh audit-p2 uv run python scripts/audit_model_visible.py --tenant audit-p2 --question "What changed in LangGraph 1.2?" --out evidence/audit/$(date +%Y%m%d-%H%M)/`.
  Expected: exit 0, `audit.json` has at least one main-agent capture. Then `make unstamp TENANT=audit-p2`.
- [ ] **Step 7: Write `docs/phase2-model-visible-audit.md`:** a table of field × status from the run,
  the subagent count, the evidence path, and for each `differs`/`not-recorded` field the smallest logging
  change that would close it. That doc is the input to the follow-up P2-C plan.
- [ ] **Step 8: Commit**
```bash
git add packages/agentkit-evals scripts/audit_model_visible.py docs/phase2-model-visible-audit.md
git commit -m "feat(evals): request capture and the model-visible audit (P2-C step 1)"
```
(The `evidence/` run dir follows the repo's existing evidence convention; commit it only if
`evidence/verify/` runs are committed.)

---

### Task 2: Seam loader in agentkit-core

**Files:**
- Create: `packages/agentkit-core/src/agentkit_core/seams.py`
- Create: `packages/agentkit-core/tests/test_seams.py`
- Modify: `packages/agentkit-core/src/agentkit_core/__init__.py` (export `Seam`, `ProviderMeta`, `provider`, `provider_meta`)

**Interfaces:**
- Produces:
  - `class ProviderMeta(BaseModel)` (frozen): `owner: str`, `version: str` (MAJOR.MINOR.PATCH, same
    validator as `ToolMeta`), `tenants: frozenset[str] | None = None`.
  - `provider(*, owner: str, version: str, tenants: Iterable[str] | None = None) -> Callable[[F], F]`
    sets `__agentkit_provider__`; `provider_meta(factory) -> ProviderMeta | None`.
  - `class Seam[T]`: `Seam(group: str, kind: str)`;
    `names(tenant: str) -> list[str]` (sorted, tenant-visible only);
    `get(name: str, tenant: str) -> Callable[[Settings], T]`.
    Discovery calls `importlib.metadata.entry_points(group=group)` on every call (no cache). Use a
    module-level import, `from importlib.metadata import entry_points`, so tests can monkeypatch
    `agentkit_core.seams.entry_points`.
  - Errors (all `ConfigError`), with this exact text:
    - duplicate: `duplicate {kind} provider {name!r}: {ep_a.value} and {ep_b.value}`
    - unknown: `unknown {kind} provider {name!r}; known: {", ".join(names) or "(none)"}`
    - restricted: `{kind} provider {name!r} is not available to tenant {tenant!r}`

- [ ] **Step 1: Write failing tests.** Fake entry points are
  `importlib.metadata.EntryPoint(name, "tests_seam_fixtures:<attr>", group)`, with a fixture module
  `packages/agentkit-core/tests/tests_seam_fixtures.py` defining `alpha`, `beta_b_only`
  (`@provider(..., tenants=["tenant-b"])`) and `alpha_again`. Monkeypatch `agentkit_core.seams.entry_points`.
  - `test_get_returns_the_factory`
  - `test_names_hide_other_tenants_providers`: `names("tenant-a") == ["alpha"]`
  - `test_restricted_provider_error_names_tenant`
  - `test_unknown_provider_lists_known`
  - `test_duplicate_names_fail_naming_both_entry_points` (Review Focus 5)
- [ ] **Step 2: Run** `uv run pytest packages/agentkit-core/tests/test_seams.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement `seams.py`** per the Interfaces block. A factory without `ProviderMeta` is visible to every tenant.
- [ ] **Step 4: Run** the tests. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "feat(core): entry-point Seam loader with tenant-private providers"`

---

### Task 3: `agentkit.secrets` seam

**Files:**
- Create: `packages/agentkit-core/src/agentkit_core/secrets.py`
- Create: `packages/agentkit-core/tests/test_secrets.py`
- Modify: `packages/agentkit-core/pyproject.toml` (add `[project.entry-points."agentkit.secrets"]` `env = "agentkit_core.secrets:env_secrets"`)
- Modify: `packages/agentkit-connectors/src/agentkit_connectors/tools.py:211,422` (use `resolve_secret`)
- Delete: `packages/agentkit-connectors/src/agentkit_connectors/secrets.py`; update `agentkit_connectors/__init__.py` and `packages/agentkit-connectors/tests/test_connectors.py:5,59-68`

**Interfaces:**
- Consumes: `Seam`, `provider` (Task 2).
- Produces:
  - `class SecretsProvider(Protocol): def resolve(self, name: str) -> str` (`name` is the part after `scheme://`).
  - `env_secrets(settings: Settings) -> SecretsProvider`, decorated `@provider(owner="platform", version="1.0.0")`. Missing var -> `ConfigError("secret env://{name} is not set")`.
  - `SECRETS: Seam[SecretsProvider] = Seam("agentkit.secrets", "secrets")`.
  - `resolve_secret(ref: str, settings: Settings) -> str`. A ref without `://` raises `ConfigError(f"unsupported secret ref {ref!r}: expected <scheme>://<name>")`. An unknown scheme re-raises the Seam error prefixed `unsupported secret ref scheme {scheme!r}: `.
  - Exported from `agentkit_core`.

- [ ] **Step 1: Write failing tests** in `test_secrets.py`:
  - `test_env_ref_resolves` (monkeypatch env `KB_X`)
  - `test_missing_env_var_names_the_var_not_a_value`
  - `test_unknown_scheme_is_unsupported`: `match="unsupported secret ref scheme 'vault'"`
  - `test_fake_scheme_resolves_through_entry_points`: a fake `test` provider via a monkeypatched `entry_points` (as in Task 2); `resolve_secret("test://k", s) == "v-k"`

  Then move the three `EnvSecrets` assertions in `test_connectors.py` to `resolve_secret` (keep `match="unsupported secret ref scheme"`).
- [ ] **Step 2: Run** `uv sync && uv run pytest packages/agentkit-core/tests/test_secrets.py packages/agentkit-connectors/tests/test_connectors.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement `secrets.py`**, then switch the two call sites in `agentkit_connectors/tools.py` to `resolve_secret(spec.dsn, ctx.settings)`.
- [ ] **Step 4: Run** the same tests plus `uv run pytest packages/agentkit-connectors -v`. Expected: PASS (pg tests skip without `AGENTKIT_TEST_DATABASE_URL`).
- [ ] **Step 5: Commit** `git commit -m "feat(core): agentkit.secrets seam; connectors resolve refs through it"`

---

### Task 4: `agentkit.search_backends` seam

**Files:**
- Modify: `packages/agentkit-tools/src/agentkit_tools/factories.py:22-62` (replace `_CLASSES`/`_backend`)
- Create: `packages/agentkit-tools/src/agentkit_tools/backends.py` (the four provider factories)
- Modify: `packages/agentkit-tools/pyproject.toml` (add the `[project.entry-points."agentkit.search_backends"]` entries `parallel`, `brave`, `tavily`, `duckduckgo` -> `agentkit_tools.backends:<name>`)
- Test: `packages/agentkit-tools/tests/test_search_seam.py`

**Interfaces:**
- Consumes: `Seam`, `provider` (Task 2).
- Produces:
  - `parallel/brave/tavily/duckduckgo(settings: Settings) -> SearchTool`, each `@provider(owner="platform", version="1.0.0")`. The keyed ones raise the existing message: `{ENV} is required for the {name} web search backend`.
  - `SEARCH_BACKENDS: Seam[SearchTool] = Seam("agentkit.search_backends", "web_search backend")`.
  - The `web_search` factory signature becomes `backend: str | list[str] = "auto"`; `auto` is unchanged (`AUTO_ORDER` built-ins whose key is set, then duckduckgo). Named backends go through `SEARCH_BACKENDS.get(name, ctx.settings.deployment_tenant)`.

- [ ] **Step 1: Write failing tests:**
  - `test_third_party_backend_is_used_without_editing_agentkit_tools`: a fake `fake` backend via monkeypatched `agentkit_core.seams.entry_points` (combine the real built-in entry points with the fake). `web_search(ctx, backend="fake")` runs a query through the fake.
  - `test_auto_order_unchanged_with_only_builtins`: all three keys set -> chain order `["parallel", "brave", "tavily", "duckduckgo"]`. Read the order through whatever `FallbackSearch` exposes, or `_names`.
  - `test_unknown_backend_lists_known`: `match="unknown web_search backend provider 'nope'"`.

  Existing tests in `packages/agentkit-tools/tests/` must stay green unchanged, apart from the
  `ConfigError` text for unknown names.
- [ ] **Step 2: Run** `uv sync && uv run pytest packages/agentkit-tools -v`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement** `backends.py` and rewire `factories.py`. Keep `_key()` for the `auto` filter.
- [ ] **Step 4: Run** `uv run pytest packages/agentkit-tools packages/agentkit-config -v` and `uv run agentkit tools snapshot --check` (or the repo's snapshot test). Expected: PASS. The `web_search` tool-call schema is unchanged, so no version bump.
- [ ] **Step 5: Commit** `git commit -m "feat(tools): search backends are an entry-point seam"`

---

### Task 5: Guards and their tenant-stamp config

**Files:**
- Create: `packages/agentkit-middleware/src/agentkit_middleware/guards.py`
- Create: `packages/agentkit-middleware/tests/test_guards.py`
- Modify: `packages/agentkit-core/src/agentkit_core/settings.py` (new field)
- Modify: `packages/agentkit-middleware/src/agentkit_middleware/__init__.py` (exports)
- Modify: `deploy/tenants/example.env`, `scripts/stamp_tenant.sh:58-70` (write `AGENTKIT_ALLOWED_SIDE_EFFECTS=read,external`), `scripts/tenant_env.sh` (export it; refuse it in `.env`), `deploy/README.md` (one paragraph)
- Test: `packages/agentkit-deep/tests/test_tenant_env.py` (extend)

**Interfaces:**
- Produces:
  - `Settings.allowed_side_effects: frozenset[Literal["read", "write", "external"]]`, alias `AGENTKIT_ALLOWED_SIDE_EFFECTS`, default `{"read", "external"}`. It is parsed from a comma-separated string (`NoDecode` + `field_validator(mode="before")`); an unknown value raises a validation error naming it.
  - `@dataclass(frozen=True) class Deny: guard: str; reason: str`.
  - `class Guard(Protocol): name: str; def check(self, call: ToolCall, tool: BaseTool | None) -> Deny | None`.
  - `TenantToolPolicyGuard(tenant: str)`, `name = "tenant_tool_policy"`:
    - `tool is None` -> abstain;
    - name in `BUILTIN_TOOLS` -> abstain;
    - no `tool.metadata["agentkit"]` -> `Deny(name, "unregistered tool {tool_name!r}")`;
    - `tenants` set and tenant not in it -> `Deny(name, "tool {tool_name!r} is not available to tenant {tenant!r}")`.
  - `SideEffectsGuard(allowed: frozenset[str])`, `name = "side_effects"`: abstains on built-ins and on tools without metadata (the policy guard owns those). Otherwise it denies when `side_effects not in allowed`: `"tool {tool_name!r} has side effects {cls!r}; allowed: {sorted}"`.
  - `GuardMiddleware(guards: Sequence[Guard])`, `name = "agentkit_guards"`, with `wrap_tool_call` and `awrap_tool_call`:
    - Guards run in order and the first `Deny` wins.
    - A guard that raises becomes `Deny(guard.name, f"guard failed: {type(e).__name__}")`.
    - A deny returns `ToolMessage(content=f"Tool call refused by {deny.guard}: {deny.reason}", tool_call_id=call["id"], name=call["name"], status="error")` and logs a warning. The handler is not called.
  - `platform_guards(settings: Settings) -> GuardMiddleware`, which returns `GuardMiddleware([TenantToolPolicyGuard(settings.deployment_tenant), SideEffectsGuard(settings.allowed_side_effects)])`.

- [ ] **Step 1: Write failing tests** in `test_guards.py` (call `awrap_tool_call` directly with a `ToolCallRequest` and a handler that records calls):
  - `test_builtin_tool_passes`
  - `test_unregistered_tool_is_denied`
  - `test_tool_of_another_tenant_is_denied_and_handler_not_called`
  - `test_write_tool_denied_by_default_read_and_external_allowed`
  - `test_raising_guard_denies_not_crashes`
  - `test_first_deny_wins_and_names_guard`
  - `test_settings_parse_comma_list_and_reject_unknown` (`"read, writ"` -> error mentioning `writ`; Review Focus 3)

  Extend `test_tenant_env.py`: `tenant_env.sh` exits 2 when the repo `.env` has `AGENTKIT_ALLOWED_SIDE_EFFECTS=`, and it exports the stamp's value (Review Focus 2).
- [ ] **Step 2: Run** `uv run pytest packages/agentkit-middleware/tests/test_guards.py packages/agentkit-deep/tests/test_tenant_env.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** the Settings field, `guards.py`, and the script changes. `guards.py` imports `BUILTIN_TOOLS` from `.selection`; do not define a second set.
- [ ] **Step 4: Run** the same tests plus `uv run pytest packages/agentkit-middleware packages/agentkit-core -v`. Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "feat(middleware): deny-only tool guards; side-effect policy from the tenant stamp"`

---

### Task 6: `build_deep_agent` installs the guards everywhere

**Files:**
- Modify: `packages/agentkit-deep/src/agentkit_deep/factory.py:27-98`
- Create: `packages/agentkit-deep/tests/test_guards_integration.py`
- Test: `packages/agentkit-config/tests/` (one test, below)

**Interfaces:**
- Consumes: `platform_guards`, `GuardMiddleware`, `BUILTIN_TOOLS` (Task 5).
- Produces (behavior of `build_deep_agent`):
  - Settings come from `settings` or a cached process `Settings()` (replace `_process_tenant` with `_process_settings() -> Settings`).
  - The main middleware is `[TenantGuardMiddleware, guards, *middleware]`.
  - Every subagent dict gets `"middleware": [guards, *spec.get("middleware", [])]`.
  - If no subagent is named `GENERAL_PURPOSE_SUBAGENT["name"]`, it appends `{**GENERAL_PURPOSE_SUBAGENT, "middleware": [guards]}`. It omits `"tools"` and `"model"`, so the parent's tools and model are inherited.
  - A caller-passed `GuardMiddleware` raises `ValueError("build_deep_agent adds GuardMiddleware itself; do not pass one")`.

- [ ] **Step 1: Write failing tests** in `test_guards_integration.py`. Use `ScriptedChatModel` via `scripted(...)`, `ctx()`, and a `@tool` whose body increments a counter and carries `metadata={"agentkit": {"tenants": ["tenant-b"], "side_effects": "read"}}`:
  - `test_main_agent_call_to_other_tenants_tool_is_refused`: the body counter stays 0, and the final state has a `ToolMessage` with `status == "error"` and `"refused by tenant_tool_policy"`.
  - `test_general_purpose_subagent_call_is_refused`: the script is `task(subagent_type="general-purpose")` -> restricted call -> "sub done" -> "main done"; the body counter stays 0.
  - `test_declared_subagent_call_is_refused`: the same, with `subagents=[{"name": "r", "description": "d", "system_prompt": "s", "tools": [restricted]}]`.
  - `test_general_purpose_subagent_still_offered`: `"general-purpose"` appears in the `task` tool description bound on the first call (`model.bound`/tool description). Review Focus 4.
  - `test_denied_call_counts_against_tool_call_limit`: with `ToolCallLimitMiddleware(tool_name="restricted", run_limit=1)` and two scripted calls, the second is blocked by the limit, not by the guard.
  - `test_every_built_tool_is_builtin_or_registered`: build the research agent via `load_agent("apps/research_agent/agent.yaml", settings=Settings(_env_file=None, fireworks_api_key="x"), overrides={"selection": "off"}, model=scripted(AIMessage("x")))` (selection off: no Decisions API call), then invoke it once. Every tool name in `model.bound[0]` is in `BUILTIN_TOOLS` or is a tool from `agent.yaml`'s `tools`. Review Focus 1.
  - `test_passing_guard_middleware_is_rejected`

  In agentkit-config: `test_yaml_cannot_name_the_guard`. An `agent.yaml` with `middleware: [{type: agentkit_guards}]` fails validation with `unknown middleware 'agentkit_guards'`.
- [ ] **Step 2: Run** `uv run pytest packages/agentkit-deep/tests/test_guards_integration.py -v`. Expected: FAIL.
- [ ] **Step 3: Implement** the factory changes and update the `build_deep_agent` docstring: guards, subagent coverage, and why the general-purpose spec is explicit.
- [ ] **Step 4: Run** the full offline suite: `uv run pytest -q`. Expected: PASS, including the research agent's existing tests and evals (`steps.jsonl` single-step evals).
- [ ] **Step 5: Commit** `git commit -m "feat(deep): guards on the main agent and every subagent, including general-purpose"`

---

### Task 7: Live verification and docs

**Files:**
- Modify: `.claude/skills/verify-agentkit/features/` (add `tool-guards.md`; follow the shape of `tenant-isolation.md`)
- Create: `docs/phase2a-results.md`
- Modify: `CLAUDE.md` (Phase 2 line: what landed and where the results are)

- [ ] **Step 1: Run the verify-agentkit flow** on fireworks-glm against a throwaway tenant. Expected: report written, as before.
- [ ] **Step 2: Run the deny case.** In the throwaway tenant's env file, set `AGENTKIT_ALLOWED_SIDE_EFFECTS=read`. `web_search`/`fetch_url` are `external`, so both are denied. Run the research question again. Expected: the transcript shows `Tool call refused by side_effects` for both tools (including calls made from the `researcher` subagent, visible in spans), `agentkit_usage` rows are still written, and the run ends without crashing. Keep the transcript, spans and rows under `evidence/verify/<run-id>/`.
- [ ] **Step 3: Write `docs/phase2a-results.md`.** Cover what each spec acceptance line maps to (test name or evidence path), the audit outcome from Task 1, and what is deferred: `agentkit.guards` group, `call_budget`, vectorstore/embeddings/tool_sources seams, P2-C steps 2–4.
- [ ] **Step 4: Update** the verify-agentkit feature map (`/pstack:maintain-verification-skill`) and `CLAUDE.md`.
- [ ] **Step 5: Commit** `git commit -m "docs: phase 2 platform-shape results and the tool-guards verify feature"`
