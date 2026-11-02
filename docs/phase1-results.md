# Phase 1 results (partial): middleware stack and eval gates

Recorded 2026-11-02 on branch `phase1-early-fixes`. Live agent runs used `fireworks-glm` only
(`accounts/fireworks/models/glm-5p3-flash`, fallback `accounts/fireworks/models/glm-5p3`); the judge was
`--judge anthropic`, whose strong tier is `claude-opus-5-5`. Evidence: `evidence/phase1/` (Markdown and
JSON are committed; raw `.stdout`/`.log` transcripts stay local).

## Golden baseline

`apps/research_agent/evals/baseline.json`, 25 of 25 cases completed (`evidence/phase1/attempt4_sources_heading.*`):

| Metric | Baseline | Gate (`gates.yaml`) |
|---|---|---|
| completed | 1.00 | min 0.96 |
| has_citation | 1.00 | min 0.96 |
| sources_section | 0.96 | min 0.90 |
| source_count_ok | 1.00 | (not gated) |
| citation_validity | 0.98 | min 0.85, max_drop 0.05 |
| completeness | 0.97 | min 0.85, max_drop 0.05 |
| groundedness | 0.63 | min 0.55, max_drop 0.10 |
| tool_recall | 1.00 | min 0.90 |
| mean_latency_s | 87.2 | (not gated) |
| mean_total_tokens | 261,337 | max_rise 0.30 |

Floors: unchanged. Every floor is met by both clean recordings (attempt 4 above, and attempt 5:
citation validity 0.95, completeness 0.97, groundedness 0.71, sources_section 1.00, completed 0.96), so
none needed lowering.

The baseline was recorded on the prompt before two later changes: the explicit `## Sources` heading
(commit `acc9046`) and the `require_output` middleware (`8437852`). Attempt 5 ran with the `## Sources`
prompt (sources_section 1.00) but one case ended without a report, so `--write-baseline` refused it.
On the controller's instruction the baseline was not re-recorded again; attempt 4 is the only run with
all 25 cases. Re-record with `--write-baseline` on the next live gate run that completes every case.

## Recording attempts and what they fixed

| Attempt | Result | Cause | Fix |
|---|---|---|---|
| 1 | 11 x `GraphRecursionError`, 1 empty report | `run_config` recursion limit 100; every middleware hook is a graph step (about 9 per model call), so runs died after about 11 model calls | Recursion limit 1000 as a backstop; the call limits are the budget (`7d33de5`) |
| 2 | 2 empty reports | The all-tools `tool_call_limit {run_limit: 40}` blocked the final `write_file` after 40 search/fetch calls | Budget `web_search` (20) and `fetch_url` (25), never `write_file` (`c232712`) |
| 3 | 1 empty report (`structured-output`) | The model replied "Let me delegate ..." with no tool call, ending the run | Prompt: never end the turn before `/report.md` is saved (`ca117ff`) |
| 4 | 25/25, baseline written | `structured-output` scored sources_section 0 (no Markdown `Sources` heading) | Prompt asks for a `## Sources` heading; the regex was not loosened (`acc9046`) |
| 5 | 24/25 (`structured-output` empty report) | Same "announce, no tool call" ending despite the prompt | `require_output` middleware nudges the model back, at most twice (`8437852`) |

No golden case was replaced: every error was an agent or configuration bug, not a flaky case.
`structured-output` ("How do LLM APIs guarantee structured JSON output ...") is the case most prone to the
early ending (attempts 3 and 5); the `require_output` fix is covered by offline tests but has not had a
full live golden run yet.

**sources_section validity.** Across 85 completed live reports in attempts 1-4, 84 had a Markdown
`## Sources` heading and one did not. Reports are not stored by `research-eval`, so that one report's
format could not be inspected; the prompt now asks for the heading explicitly, and all 24 reports of
attempt 5 had it.

## Gate checks

- **Passing path (offline, controller ruling).** `check_gates` on the recorded summaries against the
  committed baseline (`evidence/phase1/offline_gate_check.txt`): attempt 4 `gate: PASS`; attempt 5
  `gate: FAIL completed: case structured-output completed in baseline, now errored: empty report`. The
  gate does catch the per-case regression rule; no separate live passing run was made.
- **The gate bites (live).** A weakened prompt (answer from memory, at most one search, no citations or
  sources; `evidence/phase1/gate_bites/`) run with `--gate`: exit 1 in 5 minutes, with
  `gate: FAIL` on has_citation (0.00), sources_section (0.00), citation_validity (0.00, min and max_drop),
  groundedness (0.03, min and max_drop) and tool_recall (0.00). Completeness stayed at 0.97: the judge
  scores coverage of `must_cover`, not sourcing, so a plausible answer from memory passes it.
- **Mismatch (live, verify run).** A one-case dataset judged by `fireworks-glm` with `--gate` printed
  `gate: baseline mismatch: baseline dataset_sha256 mismatch: ...; re-record the baseline`, exit 2, and
  left `baseline.json` unchanged.

## Fallback proof (live)

`evidence/phase1/fallback.md`: the shipped agent loaded with a primary model
`accounts/fireworks/models/does-not-exist` and selection off answered "what is MCP?" with a cited report
(exit 0, 17.5 s). The ledger row's `model` was
`accounts/fireworks/models/does-not-exist,accounts/fireworks/models/glm-5p3`
(`evidence/phase1/fallback_ledger.json`). Nothing on stderr says the primary failed; only the ledger shows
the switch.

## verify-agentkit run `20261102-phase1`

Doctor OK; tenant `verify-20261102-phase1` stamped; a persisted, traced `research-question` turn (exit 0,
35 s, report with `## Sources`, usage row on `glm-5p3-flash`); a one-case `mcp` eval judged by
`fireworks-glm` (all seven scores 1.00); the gate mismatch probe (exit 2); the TenantMismatch probe
(exit 1, no row); `--write-baseline` without `--gate` (exit 2). `checks.txt` all PASS (223 masked spans of
the tenant only, 2 usage rows). Cleanup removed the tenant. Two drives first failed with
`ImportError: cannot import name ... from 'agentkit_core' (unknown location)`: macOS had re-hidden the
editable-install `.pth` file; `chflags nohidden .venv/lib/python*/site-packages/*.pth` (what `make sync`
does) fixed it, and those failed transcripts are kept under `failed-importerror/`.

## Requirements and open items

- The shipped research agent needs `FIREWORKS_API_KEY` for any `--model`: its fallback model is built at
  load.
- Still open from the roadmap's Phase 1: pytest plugin, single-step evals, connectors, git prompt registry,
  `@platform_tool`.
- `research-eval` does not keep each case's report, so a low deterministic score cannot be inspected
  after the fact. Storing the report in `eval_results.json` would help.
- A 25-case live gate run takes 20-27 minutes and its means move by a few points between runs (attempt
  4 vs 5: groundedness 0.63 vs 0.71, citation validity 0.98 vs 0.95), so `max_drop` values are loose.
