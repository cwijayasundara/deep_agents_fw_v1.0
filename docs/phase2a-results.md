# Phase 2a results: platform shape

Branch `phase2-platform-shape` (commits 87566b1..5c8ce0a plus this docs commit). Spec:
`docs/superpowers/specs/2026-11-03-agentkit-phase2-design.md`; plan:
`docs/superpowers/plans/2026-11-03-agentkit-phase2-platform-shape-plan.md`.

## Live verification

RUN_ID `20261103-173607`, throwaway tenant `verify-20261103-173607`, `fireworks-glm` only. Evidence
(git-ignored): `evidence/verify/20261103-173607/`. Doctor OK, stamp OK, cleanup removed the project,
env file and collector dir (`cleanup.log`). `checks.txt` all PASS (203 masked spans of the tenant only,
2 usage rows, both threads covered).

| Label | Policy | Result |
|---|---|---|
| `allow` | default | exit 0, 34 s, 8 model calls, 5 `web_search` + 6 `fetch_url` calls, report with 6 source lines |
| `deny` | `AGENTKIT_ALLOWED_SIDE_EFFECTS=read` in the tenant env file | exit 0, 34 s, 6 model calls; guard log `tool call 'web_search' refused by side_effects: ... external; allowed: ['read']` twice and `'fetch_url'` once; report written with a note that both tools were blocked and no retrieved citations (0 source lines); `agentkit_usage` row and trace written |

Limits of this evidence, stated plainly:
- The `researcher` subagent was NOT invoked in either run (only `orchestrator -> ...` calls). Subagent
  denial is covered only offline, by `test_guards_integration.py` (declared and general-purpose subagents).
- Span payloads are masked, so the literal `Tool call refused by side_effects` tool message is not in
  `spans.jsonl`; the refusal is evidenced by the guard WARNING lines in `deny.stderr.log` and by the
  report text. The message format comes from `GuardMiddleware`.

## Acceptance mapping

P2-A (guards):
- YAML cannot drop or reorder the guard: `packages/agentkit-config/tests/test_load.py::test_yaml_cannot_name_the_guard`; `packages/agentkit-deep/tests/test_guards_integration.py::test_passing_guard_middleware_is_rejected`.
- Tool of another tenant denied naming `tenant_tool_policy`: `packages/agentkit-middleware/tests/test_guards.py::test_tool_of_another_tenant_is_denied_and_handler_not_called`; at the agent level, main / general-purpose / declared subagent: `test_guards_integration.py::test_main_agent_call_to_other_tenants_tool_is_refused`, `::test_general_purpose_subagent_call_is_refused`, `::test_declared_subagent_call_is_refused`.
- A raising guard denies: `test_guards.py::test_raising_guard_denies_not_crashes`.
- Denied call counts against `tool_call_limit`: `test_guards_integration.py::test_denied_call_counts_against_tool_call_limit`. "Not retried by `tool_retry`": the guard returns a ToolMessage rather than raising, so retry never sees an error; no dedicated test, covered by that structure only.
- Live: deny run above (`deny` label). The spec phrased it as denying `fetch_url` by tenant policy; the run used the side-effects policy, which refuses both external tools.

P2-B (seams):
- Fake `agentkit.search_backends` provider used with no edit to `agentkit-tools`: `packages/agentkit-tools/tests/test_search_seam.py::test_third_party_backend_is_used_without_editing_agentkit_tools`.
- `env://` unchanged, fake `test://` provider resolves: `packages/agentkit-core/tests/test_secrets.py` (`test_env_ref_resolves`, `test_missing_env_var_names_the_var_not_a_value`, `test_fake_scheme_resolves_through_entry_points`); loader behavior: `packages/agentkit-core/tests/test_seams.py`.
- `auto` order Parallel -> Brave -> Tavily -> DuckDuckGo with built-ins only: `test_search_seam.py::test_auto_order_unchanged_with_only_builtins`.

P2-C (model-visible-means-logged): only the audit step (Task 1) was in this plan. The contract test
for `reconstruct()`, the live zero-diff run and the PII-recording test are NOT done (see Deferred).

## Audit outcome (Task 1)

Full detail: `docs/phase2-model-visible-audit.md`, evidence `evidence/audit/20261103-1705/`. Of 8
main-agent requests: messages match 8/8 and model matches 8/8; tools differ 7/8 (recorded set is a
superset, adds `execute` and `write_todos`) and are not recorded for the first request; the system
prompt differs 8/8 (`prompt_hash` covers only the pre-harness text); subagent requests are not in
parent checkpoints (none were made in the audit run). So P2-C is real work: record the final bound
tools and a system-message hash per call, and persist a per-call record for subagents.

## Deferred

- `agentkit.guards` entry-point group (third-party guards); only built-in guards ship.
- `call_budget` guard.
- vectorstore, embeddings and tool_sources seams.
- P2-C steps 2-4 (recording per-call requests, `reconstruct()`, contract and live zero-diff checks).
- Subagent denial in a live run (needs a prompt that makes the model call `researcher`).
