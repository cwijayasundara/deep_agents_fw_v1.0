# Research eval

`research-eval` runs the research agent on each case of a JSONL dataset (each on its own new
thread), scores the reports with citation checks and an LLM judge, and writes a Markdown table and
a JSON summary with per-case scores, errors, trace ids and token usage. For verification it runs a
ONE-case dataset, judged by `fireworks-glm`.

## Sub-features

- `eval-run` runs every dataset case and writes `eval_results.md` and `eval_results.json`.
- `eval-scores` per case `has_citation`, `citation_validity`, `sources_section`, `source_count_ok`, `tool_recall`, `groundedness`, `completeness`; aggregate `completed`, `mean_latency_s`, `mean_total_tokens`; per case `latency_s` and `tool_calls`.
- `eval-gate` `--gate <gates.yaml>` compares the run with the committed baseline: `gate: PASS` exit 0, `gate: FAIL <metric>: ...` exit 1, `gate: baseline mismatch: ...` or `gate: no baseline at ...` exit 2. `--write-baseline` (needs `--gate`) records the run, refusing (exit 2) if any case errored.
- `eval-user` a persisted eval runs as a fresh `eval-<hex>` user (printed `eval user: eval-<hex>`).
- `eval-trace-usage` each case records its `trace_id` and `usage`, and a ledger row under `--persist`.
- `eval-tenant-check` a tenant other than the deployment's is refused up front (`ConfigError: TenantMismatch`, exit 2).

## How to get to it (user POV)

- `scripts/tenant_env.sh <tenant> uv run research-eval --model fireworks-glm --judge fireworks-glm --tenant <tenant> --persist --dataset <one-case.jsonl> --out <file.md>`.
- Release gate (not a verification drive: 25 turns plus judging): `uv run research-eval --model fireworks-glm --dataset apps/research_agent/evals/golden.jsonl --judge anthropic --gate apps/research_agent/evals/gates.yaml --out <file.md>`.

## Driving it with verify-agentkit scripts

Preconditions:

- `$S/stamp.sh "$RUN_ID"` printed `doctor: OK`.
- Budget: one agent turn plus a few judge calls.

- **One-case eval.** Run `$S/drive_eval.sh "$RUN_ID" mcp`. It writes `eval-dataset.jsonl` with exactly the `mcp` case of `apps/research_agent/evals/smoke.jsonl`. `eval.exit` is `0`; `eval.stdout` has `eval user: eval-<8 hex>`, a `usage:` line and the Markdown table.
- **Scores.** Read `eval_results.json`. `judge` is `fireworks-glm`, `persist` is `true`, `aggregate.completed` is `1.0`, the case has all seven scores in 0..1, `error` is `null`, `trace_id`, `usage`, `latency_s` and `tool_calls` are set (`tool_calls` lists `web_search` and `fetch_url`), and `aggregate` has `mean_latency_s` and `mean_total_tokens`. The committed golden baseline (25 cases, judge `anthropic`) is in `apps/research_agent/evals/baseline.json` and `docs/phase1-results.md`; one case judged by fireworks-glm is a smoke signal, not a regression measure.
- **Gate wiring (one more turn).** Rerun the one-case eval with the gate: `scripts/tenant_env.sh "verify-$RUN_ID" uv run --no-sync research-eval --model fireworks-glm --judge fireworks-glm --tenant "verify-$RUN_ID" --dataset evidence/verify/$RUN_ID/eval-dataset.jsonl --gate apps/research_agent/evals/gates.yaml --out evidence/verify/$RUN_ID/gate_results.md`. The scores table prints, then `gate: baseline mismatch: baseline dataset_sha256 mismatch: ...; re-record the baseline` and exit `2`: the committed baseline belongs to `golden.jsonl` and the anthropic judge, so any other dataset or judge is refused rather than compared. `apps/research_agent/evals/baseline.json` is unchanged afterwards (`git status`).
- **Gate argument check (free).** `uv run --no-sync research-eval --write-baseline --dataset x.jsonl` exits `2` with `--write-baseline requires --gate` before any model call.
- **Side effects.** Run `$S/collect_evidence.sh "$RUN_ID"`. The case's `trace_id` is in `spans-summary.txt` and `agentkit_usage.csv` has a row for it; `checks.txt` all PASS.
- **Tenant check (free).** Run `scripts/tenant_env.sh "verify-$RUN_ID" uv run --no-sync research-eval --dataset evidence/verify/$RUN_ID/eval-dataset.jsonl --judge fireworks-glm --model fireworks-glm --tenant someone-else`. Exit `2`, stderr `ConfigError: TenantMismatch: run tenant 'someone-else' != deployment tenant 'verify-<RUN_ID>'`, before any model call.

## Gotchas

- Never point a proof at the default 10-case `smoke.jsonl`; that is ten turns plus judging.
- The default `--judge` is `anthropic`; the helper pins `fireworks-glm` to keep live calls on one entry. Scores are not directly comparable to the anthropic-judged baseline.
- A judge that omits its score is retried 3 times and then shows as `JudgeError` in the case's `error`; `completed` drops below 1.0. Report it; do not rerun until it passes.
- The gate's mismatch check runs after the cases, so a mismatched `--gate` run still costs its turns. Never pass `--write-baseline` in a verification drive: it overwrites the committed baseline with a one-case, fireworks-judged run.
- A gate run of the golden set is a release check, not a verification step: it costs 25 turns and 25 anthropic judge rounds (about 15-30 min).
- The `eval-<hex>` user's store items are never pruned (open item); harmless on a verify tenant that cleanup destroys.
