# Research eval

`research-eval` runs the research agent on each case of a JSONL dataset (each on its own new
thread), scores the reports with citation checks and an LLM judge, and writes a Markdown table and
a JSON summary with per-case scores, errors, trace ids and token usage. For verification it runs a
ONE-case dataset, judged by `fireworks-glm`.

## Sub-features

- `eval-run` runs every dataset case and writes `eval_results.md` and `eval_results.json`.
- `eval-scores` per case `has_citation`, `citation_validity`, `groundedness`, `completeness`; aggregate `completed`.
- `eval-user` a persisted eval runs as a fresh `eval-<hex>` user (printed `eval user: eval-<hex>`).
- `eval-trace-usage` each case records its `trace_id` and `usage`, and a ledger row under `--persist`.
- `eval-tenant-check` a tenant other than the deployment's is refused up front (`ConfigError: TenantMismatch`, exit 2).

## How to get to it (user POV)

- `scripts/tenant_env.sh <tenant> uv run research-eval --model fireworks-glm --judge fireworks-glm --tenant <tenant> --persist --dataset <one-case.jsonl> --out <file.md>`.

## Driving it with verify-agentkit scripts

Preconditions:

- `$S/stamp.sh "$RUN_ID"` printed `doctor: OK`.
- Budget: one agent turn plus a few judge calls.

- **One-case eval.** Run `$S/drive_eval.sh "$RUN_ID" mcp`. It writes `eval-dataset.jsonl` with exactly the `mcp` case of `apps/research_agent/evals/smoke.jsonl`. `eval.exit` is `0`; `eval.stdout` has `eval user: eval-<8 hex>`, a `usage:` line and the Markdown table.
- **Scores.** Read `eval_results.json`. `judge` is `fireworks-glm`, `persist` is `true`, `aggregate.completed` is `1.0`, the case has all four scores in 0..1, `error` is `null`, and `trace_id` and `usage` are set. Baseline for comparison (10 cases, judge `anthropic`): citation validity 0.96, completeness 0.97, groundedness 0.64; one case judged by fireworks-glm is a smoke signal, not a regression measure.
- **Side effects.** Run `$S/collect_evidence.sh "$RUN_ID"`. The case's `trace_id` is in `spans-summary.txt` and `agentkit_usage.csv` has a row for it; `checks.txt` all PASS.
- **Tenant check (free).** Run `scripts/tenant_env.sh "verify-$RUN_ID" uv run --no-sync research-eval --dataset evidence/verify/$RUN_ID/eval-dataset.jsonl --judge fireworks-glm --model fireworks-glm --tenant someone-else`. Exit `2`, stderr `ConfigError: TenantMismatch: run tenant 'someone-else' != deployment tenant 'verify-<RUN_ID>'`, before any model call.

## Gotchas

- Never point a proof at the default 10-case `smoke.jsonl`; that is ten turns plus judging.
- The default `--judge` is `anthropic`; the helper pins `fireworks-glm` to keep live calls on one entry. Scores are not directly comparable to the anthropic-judged baseline.
- A judge that omits its score is retried 3 times and then shows as `JudgeError` in the case's `error`; `completed` drops below 1.0. Report it; do not rerun until it passes.
- The `eval-<hex>` user's store items are never pruned (open item); harmless on a verify tenant that cleanup destroys.
