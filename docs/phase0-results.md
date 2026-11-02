# Phase 0 T9 results

T9 passed on 2026-11-02. The research agent runs end to end live, through the factory, with Decisions
selection and Tavily search. The reference model for live testing is **`fireworks-glm`** from now on.
The other providers get one live call each and offline coverage only (operator's call, 2026-11-02).

## Model ids and one live call each

`models.yaml` uses one cheap fast model per provider on every tier (operator's call, 2026-11-01).

| Entry | Model id | Live call (2026-11-02) |
|---|---|---|
| `openai` | `gpt-6-luna` | Passed |
| `google_genai` | `gemini-3.8-flash` | Passed |
| `anthropic` | `claude-haiku-5-5` | Passed |
| `fireworks-deepseek` | `accounts/fireworks/models/deepseek-v4p1-flash-1017` | Passed |
| `fireworks-glm` | `accounts/fireworks/models/glm-5p3-flash` | Passed |
| `fireworks-minimax` | `accounts/fireworks/models/minimax-m3p1-flash` | Passed |

Command: `uv run pytest -m live`. Result: `7 passed`, covering the six model calls plus one full research
run on the `anthropic` config with Decisions and Tavily.

The live tests used to skip any provider whose key was only in `.env`, because they checked
`os.environ`. They now use `Settings().keys_present()`, the same lookup the CLIs use.

## Decisions API

Two real `/v1/decisions` responses were recorded (`gpt-6-luna`, HTTP 200). They are now test fixtures
in `packages/agentkit-middleware/tests/fixtures/`. The response shape matches the T4 fixtures:
`answers[]` with `predicate` (`probability`) and `choice` (`choice`, `probabilities`, `confidence`),
plus `usage` with cached-token details.

| System prompt | web_search | fetch_url | sql (irrelevant) | Tier answer | Tier used |
|---|---|---|---|---|---|
| Real orchestrator prompt | 1.00 | 1.00 | 0.00 | fast, confidence 0.27 | default (below 0.5 floor) |
| One-line "You are a deep-research agent." | 0.03 | 0.01 | 0.00 | fast, confidence 0.97 | fast |

**Risk:** with a vague system prompt, Decisions hides every tool and the agent can't search. Agents
that use `selection: decisions` need a system prompt that says which tools to use and when. A
"minimum tools" guard is a candidate for the ToolSurface work in Phase 3.

## Evals (10 questions, judge `anthropic`)

Two eval bugs were found and fixed during T9:

1. **Groundedness undercounted.** The judge saw only the orchestrator's tool output, cut at 30k
   characters. Pages fetched inside the `researcher` subagent never reached it.
   `run_with_progress(tool_outputs=...)` now collects every tool result in every namespace, and the
   cap is 120k characters.
2. **Judge crashes counted as failed cases.** openevals raises `KeyError: 'score'` when the judge
   model omits the score. The judge now retries up to 3 times and then raises `JudgeError`.

Run 1 used the old eval code. Run 2 had fix 1 and the first half of fix 2; the `KeyError` retry
landed after run 2. Run 2 was stopped once the operator narrowed live testing to `fireworks-glm`, so
Gemini and minimax have no run-2 numbers.

| Config | Run | Completed | Citation validity | Completeness | Groundedness |
|---|---|---|---|---|---|
| **fireworks-glm** (baseline) | 2 | **1.00** | **0.96** | **0.97** | **0.64** |
| fireworks-glm | 1 | 0.90 | 0.98 | 0.98 | 0.28 |
| openai | 2 | 1.00 | 1.00 | 0.94 | 0.73 |
| anthropic | 2 | 0.70 (3 judge `KeyError`s) | 1.00 | 0.88 | 0.89 |
| fireworks-deepseek | 2 | 1.00 | 0.93 | 0.98 | 0.41 |
| google_genai | 1 | 1.00 | 0.99 | 0.96 | 0.11 (old eval code) |

Every completed report had a citation (`has_citation` 1.00). Run time per question was about 30s on
anthropic, 1–1.5 min on openai and glm, about 2 min on Gemini, and about 7 min on minimax.

Running six configs in parallel produced intermittent Tavily `HTTPStatusError`s on search and fetch.
Live evals should run one config at a time.

Evidence: `evidence/t9/run1/`, `evidence/t9/run2/` (Markdown and JSON per config) and
`evidence/t9/decisions-response*.json`. Raw run logs are kept locally and are not committed.

## Declarative re-run (agent.yaml), 2026-11-02

T9 re-run with the agent built from `apps/research_agent/agent.yaml` via `load_agent`, `fireworks-glm` only
(`uv run research-eval --model fireworks-glm --judge anthropic`, default concurrency, one run).

**Caveat: Tavily web_search failed on every call.** Tally from the local run logs (`<- web_search ok|error`):

| Run | web_search | fetch_url |
|---|---|---|
| Step 1 (`glm.log`) | 0 ok / 5 error | 5 ok / 1 error |
| Step 2 (`glm-ddg.log`, orchestrator on DuckDuckGo) | 3 ok / 2 error | not tallied |
| Eval (`eval.log`) | 0 ok / 102 error (orchestrator 44, subagent 58) | 431 ok / 208 error |

`glm.md` itself says web search was unavailable. The citations therefore came from `fetch_url` on URLs the
model chose from memory, and the eval measured a search-less agent. The logs are local-only (git-ignored);
the numbers above are the record.

Eval comparison (not a valid equivalence check of search: Tavily returned `HTTPStatusError` on every call;
the status code was not logged, likely exhausted credits or a rate limit):

| Run | Completed | Citation validity | Completeness | Groundedness |
|---|---|---|---|---|
| Baseline (run 2, Python-built) | 1.00 | 0.96 | 0.97 | 0.64 |
| Declarative (agent.yaml), search-less | 1.00 | 0.96 | 0.96 | 0.65 |

The numbers meet the brief's 0.10 rule on its letter, but they do not show that search works through the
YAML-built agent. Build equivalence with the Python-built agent is proven offline by the snapshot test.

Single-question runs ("What is the Model Context Protocol?"):

- Step 1, Tavily (`evidence/declarative/glm.md`): PASS on the brief's letter (citations and a Sources section
  present, log shows `selection=decisions` and the Decisions API call, 25.9s), but Tavily search failed on all calls.
- Step 2, DuckDuckGo (`evidence/declarative/agent-ddg.yaml`, name `research_agent_ddg`,
  `web_search: {backend: duckduckgo}` on the orchestrator; `evidence/declarative/glm-ddg.md`): DuckDuckGo search
  worked (3 of 5 calls ok), report has citations, 31.2s. The `researcher` subagent still used Tavily (subagent
  tools replace the parent's).

Evidence: `evidence/declarative/` (reports, `eval.md`, `eval.json`, `agent-ddg.yaml`).

## Follow-ups

- Tavily failed on every call: check credits and the key, then repeat the eval with working search.
- Log the HTTP status code in search errors.
- Consider DuckDuckGo as the default for local and eval runs.
- The researcher subagent cannot switch backend unless the subagent YAML sets it.

## DuckDuckGo default re-run, 2026-11-02

After Tavily failed on every call, web search was switched to DuckDuckGo by default (operator's call). The
fireworks-glm eval was re-run once through `apps/research_agent/agent.yaml` (judge `anthropic`, 10 questions).

| Metric | Baseline (run 2) | DuckDuckGo default | Delta |
|---|---|---|---|
| completed | 1.00 | 1.00 | 0.00 |
| citation_validity | 0.96 | 0.99 | +0.03 |
| completeness | 0.97 | 0.94 | -0.03 |
| groundedness | 0.64 | 0.66 | +0.02 |

**Pass**: no metric is more than 0.10 below the baseline. Search actually ran this time: DuckDuckGo answered 59 of
105 `web_search` calls (orchestrator 41/71, researcher subagent 18/34); the failures are DuckDuckGo rate limiting
under the eval's two concurrent questions. `fetch_url` succeeded 121 of 137 times. This closes the open item from
the declarative re-run: the YAML-built agent is live-verified with working search. Evidence:
`evidence/ddg-default/eval.md` and `eval.json` (logs are local-only).

## Phase 0b close-out, 2026-11-02

One real persisted, traced, two-turn conversation on `fireworks-glm` against a stamped tenant. Web search was
DuckDuckGo (4 of 4 `web_search` calls ok). No other provider, no eval, no retries.

Commands (each through `scripts/tenant_env.sh tenant-a`):

```
make stamp TENANT=tenant-a
uv run research "What is the Model Context Protocol?" --model fireworks-glm --tenant tenant-a --persist --out evidence/phase0b/turn1.md
uv run research "How does it compare to plain function calling?" --model fireworks-glm --tenant tenant-a --persist --thread <id> --out evidence/phase0b/turn2.md
```

Thread `173d8cc8-963a-443f-be1b-6552b487d796`.

| Criterion | Result |
|---|---|
| Turn 1 writes a cited report | PASS: `evidence/phase0b/turn1.md`, 6256 chars, [n] citations plus Sources |
| Turn 2 writes a cited report | PASS: `evidence/phase0b/turn2.md`, [n] citations plus Sources |
| Turn 2 prints `resumed thread <id> at step <n>` | PASS: `resumed thread 173d8cc8-... at step 15` |
| Collector file holds the run's spans for tenant-a | PASS: 9 batches, 56 spans, resource `agentkit.tenant` = `tenant-a` only (10 `model` spans = 6 + 4 model calls) |
| No prompt text in spans (masked default) | PASS: neither question text nor "Model Context Protocol" appears in the file |
| `agentkit_usage` has a row per turn, nonzero tokens | PASS: 2 rows, tenant `tenant-a`, same thread id |

| Turn | Duration | Model calls | Input (cached) | Output | Decisions input |
|---|---|---|---|---|---|
| 1 | 35s wall (agent 32.8s) | 6 | 88609 (63040) | 3696 | 684 |
| 2 | 29s wall | 4 | 133287 (119424) | 3743 | 0 |

Turn 2 made no Decisions call, since the thread resumed with the earlier selection. Evidence: reports in
`evidence/phase0b/` (logs are local-only). The stamp was torn down afterwards (`make unstamp`, tenant env
file deleted).

Open items carried forward: P10 thread-to-user binding, P3 primitive state stored in plaintext, AES key
rotation and backup, the encrypted store items of `eval-<hex>` users (never pruned: `agentkit-prune` deletes
threads only), and a tenant filter for prune if tenants ever share a database.
