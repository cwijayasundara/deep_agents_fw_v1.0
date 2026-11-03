# Phase 1 (rest) results: KB pilot, single-step baseline, research gate

Recorded 2026-11-02 on branch `phase1-rest`. Live agent runs used `fireworks-glm` only
(`accounts/fireworks/models/glm-5p3-flash`). The judge was `--judge anthropic`, whose strong tier is
`claude-opus-5-5`, and embeddings used `fireworks-nomic` (768 dimensions). Evidence is under
`evidence/phase1b/`: Markdown and JSON are committed, and the raw `.stdout`/`.log` transcripts stay local.

This closes the roadmap's Phase 1. It adds:

- `@platform_tool` and tenant tool policy
- the versioned prompt registry
- connectors with `kb_search` and `sql_query`
- single-step evals and the pytest plugin
- a second, knowledge-base pilot agent gated by a 20-case golden set, which passes.

Architecture: `docs/architecture.md` sections 3.7, 6.1, 6.2 and 14.7 to 14.9.

## Live commands

| Step | Command (abridged) | Exit | Wall time | Evidence |
|---|---|---|---|---|
| 1 Research golden gate | `research-eval --model fireworks-glm --dataset apps/research_agent/evals/golden.jsonl --judge anthropic --gate apps/research_agent/evals/gates.yaml` | 1 (tokens only, see below) | 551 s | `evidence/phase1b/golden/golden_gate.{md,json}` |
| 2 Single-step baseline | `research-eval --model fireworks-glm --dataset apps/research_agent/evals/steps.jsonl --judge anthropic --gate apps/research_agent/evals/gates_steps.yaml --write-baseline` | 0 | 25 s | `evidence/phase1b/steps/steps_baseline.{md,json}` |
| 2 Plugin, attempt 1 | `pytest apps/research_agent/tests/test_eval_steps.py --agentkit-live` | 1 (12 x `ConfigError`, no model call) | 2 s | `evidence/phase1b/steps/plugin_live_attempt1_noenv_summary.txt` |
| 2 Plugin, after fix | same | 0 (12 passed) | 48 s | `evidence/phase1b/steps/plugin_live_summary.txt` |
| 3 KB baseline | `tenant_env.sh kbpilot-1b research-eval --agent apps/kb_agent/agent.yaml --model fireworks-glm --tenant kbpilot-1b --dataset apps/kb_agent/evals/golden.jsonl --judge anthropic --gate apps/kb_agent/evals/gates.yaml --write-baseline` | 0 | 82 s | `evidence/phase1b/kb/kb_baseline.{md,json}` |
| 3 KB gate (new floors) | same without `--write-baseline` | 0, `gate: PASS` | 86 s | `evidence/phase1b/kb/kb_gate.{md,json}` |

Concurrency was the default 6 throughout. Steps 1 and 2 ran at the same time.

## Research golden gate (Step 1)

The run completed 25/25. It failed only on tokens: `gate: FAIL mean_total_tokens: 296563 rose 32.7% above
baseline 223437 (max_rise 30%)`. Every quality metric met its floor:

| Metric | Old baseline | Step 1 run | Floor |
|---|---|---|---|
| completed | 1.00 | 1.00 | 0.96 |
| has_citation / sources_section / source_count_ok / tool_recall | 1.00 | 1.00 | 0.96 / 0.90 / - / 0.90 |
| citation_validity | 0.96 | 0.96 | 0.85, max_drop 0.05 |
| completeness | 0.97 | 0.98 | 0.85, max_drop 0.05 |
| groundedness | 0.67 | 0.62 | 0.55, max_drop 0.10 |
| mean_latency_s | 101.9 | 90.2 | - |
| mean_total_tokens | 223,437 | 296,563 | max_rise 0.30 |

**Is the rise from Task 1's tool descriptions?** No.

- **Prompt size.** Task 1 added about four lines of when-to-use text and pydantic argument schemas to
  `web_search` and `fetch_url`. That is roughly 100 more prompt tokens per model call, or 1-2% of a
  case.
- **Tool use.** The model did not start asking for larger results: the mean `web_search` output was
  2,681 characters, against 2,661 in the old baseline run.
- **Search failures.** DuckDuckGo failures were about the same: 86 `search failed` warnings, against 84.
- **Spread.** The rise comes from a few outlier cases. 10 of 25 cases used fewer tokens than in the
  old baseline run. `structured-output` alone went from 304k to 1.49M tokens (80 tool calls and 3
  delegations, against 24 calls), `pii-llm` from 158k to 544k, and `oss-models` from 101k to 459k.
- **Run-to-run range.** Earlier full runs of the same agent measured 209k to 268k tokens
  (`evidence/phase1/attempt*.json`; attempt 2, at 371k, had a tool-budget bug). The old baseline was one sample near the bottom of that range.

**Re-record (the one allowed).** The cause is run-to-run variance in a heavy-tailed metric, not a
change in the agent. So `apps/research_agent/evals/baseline.json` was re-recorded from this same 25/25
run. It goes through the same checks and the same `Baseline.from_summary` path that `--write-baseline`
uses, so there was no extra live run (`evidence/phase1b/golden/rerecord.txt`; the previous baseline is
kept as `evidence/phase1b/golden/baseline_before.json`). Against the new baseline the run gives `gate:
PASS`. The `min` floors in `gates.yaml` are unchanged, but the effective gate moved, because the
`max_drop` and `max_rise` checks are relative to the baseline.

New baseline: citation validity 0.96, completeness 0.98, groundedness 0.62, the four binary metrics
1.00, mean latency 90 s and 297k mean total tokens.

**Caveat: the re-record relaxed the gate.** The new baseline is itself an outlier sample.

- **Tokens.** 297k is above every earlier valid full run (209k-268k). Within this run, the per-case
  median is 185k and the mean without the top 3 cases is 189k; both are below the old 223k mean. The
  token ceiling (`max_rise` 0.30) went from about 290k to about 386k, so a real 30-70% token
  regression against a typical run would now pass.
- **Groundedness.** The `max_drop` reference fell by 0.06 (0.675 to 0.615), so the effective
  groundedness gate went from 0.575 (0.675 - 0.10) down to the 0.55 floor.
- **Others.** Citation validity and completeness rose slightly, so their `max_drop` gates tightened
  by under 0.01.

**Recommendation for Phase 2:** gate a median or trimmed `total_tokens` metric instead of
`mean_total_tokens`, and record baselines over several runs (pass^k), then re-record.

## Single-step baseline and the plugin (Step 2)

`apps/research_agent/evals/baseline_steps.json`: `step_pass` 0.83 (10/12), `completed` 1.00, which
clears the `step_pass` 0.80 floor.

| Case | Baseline run | Plugin run |
|---|---|---|
| first-factual | pass | pass |
| first-comparison | **fail**: `no tool call` (the model answered in text first) | pass |
| first-recent | pass | pass |
| after-plan | pass | pass |
| fetch-official | pass | pass |
| fetch-primary-paper | pass | pass |
| search-after-dead-link | pass | pass |
| write-after-enough-sources | **fail**: `called fetch_url, expected ^write_file$` | pass |
| write-on-call-limit | pass | pass |
| report-has-citations | pass | pass |
| follow-up-needs-new-facts | pass | pass |
| first-multi-part | pass | pass |

Neither failure repeated in one further run: the plugin run, minutes later, passed all 12. Two
samples cannot tell sampling variance from an intermittent behaviour gap, so no case was changed and
pass^k runs (Phase 2) are needed to settle it.

- `first-comparison`: the agent sometimes opens a comparison with prose instead of a plan or a search.
- `write-after-enough-sources`: it sometimes fetches one more source before writing.

**Bug found and fixed (`e5b5163`).** The first plugin run failed all 12 cases in 2 seconds with
`ConfigError: OPENAI_API_KEY is required for provider 'openai'`.

- **Cause.** The root `conftest.py` drops `.env` for every test not marked `live`, and `agentkit_eval`
  tests carry no `live` marker. They cannot carry one, because `addopts = -m 'not live'` would deselect
  them.
- **Fix.** `live` and `agentkit_eval` tests both keep `.env`.
- **Test.** `apps/research_agent/tests/test_conftest_dotenv.py`.
- **Check.** One case first (`-k first-factual`, passed), then the full plugin run.

## KB pilot (Step 3)

**Setup.**

- Throwaway tenant `kbpilot-1b`, stamped and torn down afterwards: `make unstamp`, then its env file and
  otel-out directory were deleted.
- `agentkit-kb setup --connector kb-docs --reader-password-env KB_READER_PASSWORD` with the tenant's
  admin DSN. It printed `setup: schema kb and role kb_reader ready`.
- `make kb-ingest` loaded `ingest: 141 chunk(s) from 4 file(s) into kb.kb_docs` (README,
  `docs/architecture.md`, `docs/phase0-results.md`, `docs/phase1-results.md`, before this task's doc
  edits).
- Both `KB_DATABASE_URL` and `KB_READER_DATABASE_URL` were kb_reader DSNs for every agent run. Before the
  runs, a check confirmed the login was `current_user = kb_reader` and saw 141 rows.

**Baseline** (`apps/kb_agent/evals/baseline.json`, 20/20 completed):

| Metric | Baseline | Research margin | Floor (`gates.yaml`) | Gate re-run |
|---|---|---|---|---|
| completed | 1.00 | -0.04 | 0.96 | 1.00 |
| has_citation | 0.90 | -0.04 | 0.86 | 1.00 |
| sources_section | 0.90 | -0.10 | 0.80 | 1.00 |
| source_count_ok | 0.90 | (not gated) | - | 1.00 |
| citation_validity | 0.90 | -0.11 | 0.79, max_drop 0.05 | 1.00 |
| completeness | 0.997 | -0.12 | 0.87, max_drop 0.05 | 1.00 |
| groundedness | 0.886 | -0.12 | 0.76, max_drop 0.10 | 0.908 |
| tool_recall | 1.00 | -0.10 | 0.90 | 1.00 |
| mean_latency_s | 11.1 | - | - | 11.7 |
| mean_total_tokens | 22,100 | - | max_rise 0.30 | 22,355 |

**How the floors were set.** Each margin is the research gate's own margin: the gap between
`apps/research_agent/evals/gates.yaml` and the baseline it was set against (for example, completeness
0.974 baseline, 0.85 floor, so 0.12). Each floor is the KB baseline minus that margin, rounded down, so
no floor sits above its baseline. A test now asserts that (`apps/kb_agent/tests/test_kb_agent.py`).

The provisional floors were lower than the baseline in some places and higher in others.
`has_citation` 0.95 would have failed the recorded 0.90, so it came down to 0.86. `groundedness` 0.60
and `completeness` 0.80 went up to 0.76 and 0.87.

**Gate re-run.** `gate: PASS`, exit 0.

**Two uncited reports in the baseline.** `validate-yaml` and `stamp-tenant` produced correct, judged-
complete reports with `[n]` markers but no `## Sources` list and no URL, so has_citation,
sources_section, citation_validity and source_count_ok were 0. The prompt (`kb/answerer@1.0.0`) asks for
the list. In the gate re-run both cases cited fully (all 20 cases 1.00 on the binary metrics), so the
lapse did not repeat in one further run; two samples cannot say how often it happens. The cases were
not loosened.

Compared with the research agent, the KB agent is about 8x faster (11 s against 90 s per case) and uses
about 13x fewer tokens (22k against 297k). Its groundedness is much higher (0.89 against 0.62): it
answers from retrieved chunks, not from fetched web pages.

## verify-agentkit run `20261102-phase1b`

| Check | Result |
|---|---|
| Doctor | OK |
| Tenant | `verify-20261102-phase1b` stamped |
| Persisted research turn (after the tool-description change) | exit 0, 34 s, `## Sources`, selection `fetch_url, web_search` |
| `agentkit tools list` | four tools at `1.0.0` |
| `agentkit-kb setup` and `make kb-ingest` on the verify tenant | 161 chunks: the docs now include this task's architecture sections |
| Persisted `apps/kb_agent` turn as `kb_reader` | exit 0, 4 model calls, `## Sources` of GitHub blob URLs |
| Plugin without `--agentkit-live` | 12 skipped |
| Plugin live case `first-factual` | PASSED |
| `checks.txt` | all PASS: 163 masked spans of the tenant only, 2 usage rows, one per thread |
| Cleanup | removed the tenant |

Evidence stays local under `evidence/verify/20261102-phase1b/`, which is git-ignored. The feature map
gained `features/kb-agent.md` and plugin and single-step entries in `features/research-eval.md`.

## Open items

- **Research token gate.** The re-recorded baseline relaxed the token ceiling to about 386k and the
  groundedness reference by 0.06 (see Step 1). Phase 2: gate a median or trimmed token metric over a
  multi-run baseline.
- **Single-step flakiness.** Live single-step cases are single samples. pass^k (k-trial) runs are a
  Phase 2 item.
- **KB `## Sources` lapses.** The kb agent occasionally omits its `## Sources` list (2/20 in one run, 0/20
  in the next).
- **Governance not yet enforced.** `side_effects`, `identity` and `classification` are recorded, not
  enforced. HITL for write tools is Phase 2.
- **Secrets providers.** Only `env://` secret refs exist; Vault and cloud secret providers are Phase 2.
- **Unchanged from before:**
  - P10 thread-to-user binding
  - P3 primitive state stored in plaintext
  - AES key rotation and backup
  - never-pruned `eval-<hex>` store items
  - the prune tenant filter
  - strong tiers for `openai`, `google_genai` and `fireworks-deepseek`.
