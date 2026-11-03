# Phase 2 model-visible audit (P2-C step 1)

Question: for each model request, can we recover from what we already record exactly what the
model was sent? Method: `scripts/audit_model_visible.py` runs one persisted turn of
`apps/research_agent/agent.yaml` on `fireworks-glm` (tenant `audit-p2`, question "What changed in
LangGraph 1.2?") with a `RequestCapture` callback, then compares every captured main-agent request
with the thread's checkpoints, the `agentkit_usage` rows and the run's `prompt_hash`.

Evidence: `evidence/audit/20261103-1705/` (`audit.json`, `captures.jsonl`). 8 main-agent model
requests, 0 subagent requests (the agent made 0 `task` calls this run, so the subagent path is
untested by this run).

## Matching rule

The request at `langgraph_step = N` is compared with the checkpoint whose `metadata["step"] == N - 1`
(the state the model node read). This lined up for all 8 captures. In practice a model call's
`checkpoint_ns` is `model:<id>` for the main agent, so `RequestCapture.namespace` drops the last
segment of `checkpoint_ns`: `""` is the main agent, anything else is nested (subagent).

## Field x status

| Field | Compared with | Status (8 requests) |
|---|---|---|
| messages (non-system) | digest of checkpoint `messages` | match 8/8 |
| model | model ids in the thread's `agentkit_usage` rows | match 8/8 (`accounts/fireworks/models/glm-5p3-flash`) |
| tools | `agentkit_selection.tools` + `BUILTIN_TOOLS` | differs 7/8, not-recorded 1/8 |
| system prompt | run `prompt_hash` | differs 8/8 (expected) |
| subagent requests | parent checkpoints | not in parent checkpoints (0 observed) |

## Gaps and the smallest logging change to close each

- **tools, differs (7/8).** Recorded set (selection + `BUILTIN_TOOLS`) lists `execute` and
  `write_todos`, which were not sent; nothing sent was missing from the record. The record is a
  superset, not the truth. Smallest fix: have `SelectionMiddleware` write the final bound tool names
  (after the harness filters) into `agentkit_selection` (or a `sent_tools` field) instead of
  deriving them from `BUILTIN_TOOLS`.
- **tools, not-recorded (1/8, first request).** Selection runs inside the first model step, so the
  pre-model checkpoint has no `agentkit_selection`. Same fix covers it if the sent tools are
  written to the post-step state and the audit reads the following checkpoint for the first call.
- **system prompt, differs (8/8).** `prompt_hash` covers only the pre-harness prompt text; the
  model sees the harness-assembled system message (base prompt, middleware sections, skills).
  Smallest fix: record `sha256` of the final system message per model call (e.g. a span attribute
  or a column on a per-call row), alongside `prompt_hash`; keep `prompt_hash` as the authored-prompt id.
- **model, matches** but only at run granularity: `agentkit_usage.model` is a comma-joined set per
  run, so a mid-run fallback would not say which call used which model. Smallest fix: record the
  model id per call (span attribute) if per-call attribution is needed.
- **messages, matches** against the checkpoint, but only because no middleware rewrote messages in
  this run. A request-time rewrite (PII redaction, summarization) would show as `differs` and is
  not recoverable from checkpoints; recording `messages_sha` per call is the smallest fix.
- **subagent requests** are never in the parent thread's checkpoints. Smallest fix: persist a
  per-call record (namespace, step, model, tools, system_sha, messages_sha, count: the
  `CapturedRequest` shape) from a callback in production.

This document is the input to the follow-up P2-C plan.
