# agentkit

Shared, self-hosted agent platform on DeepAgents / LangChain v1 / LangGraph.
Phase 0 goal: a deep-research agent built through the `build_deep_agent` factory, provider chosen by config only.
Design: `docs/superpowers/specs/2026-11-01-agentkit-phase0-design.md` · Plan: `docs/superpowers/plans/2026-11-01-agentkit-phase0-plan.md`

## Quickstart

```bash
cp .env.example .env        # fill in keys; .env is git-ignored, never commit it
make test                   # uv sync (pinned via constraints.txt) + offline tests
make lint                   # ruff + mypy
```

Run the research agent (needs the chosen provider's key plus `TAVILY_API_KEY`):

```bash
UV_CONSTRAINT=constraints.txt uv run research "your question"
UV_CONSTRAINT=constraints.txt uv run research-eval --judge anthropic
```

The agent is defined in `apps/research_agent/agent.yaml` (tools, subagents and prompts are picked by name from
`libraries/`). Switching provider = `--model <registry entry>`; `--tier` and `--no-selection` override the
other two keys; `--agent <file>` runs a different agent file.

`--model` defaults to the file's `fireworks-glm` (`accounts/fireworks/models/glm-5p3-flash`). Keys always come
from the nearest `.env` (searched upward from the current directory), and `.env` values win over shell
exports. Both CLIs log progress to stderr: resolved model, which keys are set (names only), the Decisions
selection, every delegation, search, fetch and file write, and total run time. Add `-v` for tool output and
token counts, or `-q` for warnings only.

## Test it manually

Run every command from the repo root. The CLIs read `.env` and the default agent path relative to the
current directory. Each step below costs real tokens except step 1.

### 1. Check the offline build

```bash
make test        # expect: 144 passed, 7 deselected
make lint        # expect: no ruff or mypy errors
```

### 2. Check which keys you have

```bash
cp .env.example .env    # then fill in the keys you have
grep -oE '^[A-Z_]+=.' .env | cut -d= -f1    # lists the keys that are set, never their values
```

Each run needs these keys.

| What you run | Keys it needs |
|---|---|
| The shipped `apps/research_agent/agent.yaml` | `TAVILY_API_KEY`, `OPENAI_API_KEY` (it sets `selection: decisions`), and the provider's own key |
| Any run with `--no-selection` | `TAVILY_API_KEY` and the provider's own key |
| `research-eval` | The above, plus the key of the `--judge` entry (default `anthropic`) |

To try a provider without an OpenAI key, pass `--no-selection`. The agent then sees every tool and stays on
the configured tier. To search without a Tavily key, set `backend: duckduckgo` on the `web_search` tool
(`tools: [{web_search: {backend: duckduckgo}}, fetch_url]`).

### 3. Check that each model answers

```bash
uv run pytest -m live packages/agentkit-core/tests/test_live_providers.py -v
```

This makes one short call per registry entry. An entry whose key is missing is skipped, not failed.

### 4. Run one research question

```bash
uv run research "When should a team choose RAG over fine-tuning?" \
	--model fireworks-glm --out report.md
```

Check `report.md`. A good run gives a structured report with inline citations, and each citation is a URL
the agent fetched. Common failures:

- `ConfigError` naming a key means that key is missing from `.env`.
- A Decisions API error does not stop the run. The middleware logs `selection unavailable for thread ...`
  and falls back to all tools and the default tier.
- An empty `report.md` means the model never wrote `/report.md`. Try another `--model`, and note the model in
  `docs/phase0-results.md`.

### 5. Score an agent with the eval

```bash
uv run research-eval --model fireworks-glm --judge anthropic \
	--out eval_results.md
```

The eval runs the 10 questions in `apps/research_agent/evals/smoke.jsonl` and judges each report for
citations, groundedness, and completeness. It writes `eval_results.md` and `eval_results.json`. Use
`--dataset` to point at a smaller JSONL file for a cheaper run. If you lack the judge's key, pass
`--judge` with an entry you have a key for, such as `openai`.

### 6. Run the full live suite

```bash
RESEARCH_LIVE_MODELS=fireworks-glm \
	uv run pytest -m live -v
```

A model whose keys are missing is skipped. Record each result in `docs/phase0-results.md`.

## Layout

| Package | Purpose |
|---|---|
| `agentkit-core` | settings, model registry (`models.yaml`), `get_model` |
| `agentkit-tools` | Tavily search, HTTP fetch, LangChain tool wrappers |
| `agentkit-middleware` | retry/backoff + circuit breaker, per-thread `SelectionMiddleware` |
| `agentkit-deep` | `build_deep_agent` factory, scripted fake model for tests |
| `agentkit-evals` | dataset, citation checks, openevals LLM judge, runner |
| `agentkit-config` | declarative `agent.yaml` loader (`load_agent`), libraries of prompts, skills, subagents |
| `apps/research_agent` | `agent.yaml`, `research` and `research-eval` CLIs |

## Extending

- **Add a provider/model:** add an entry to `packages/agentkit-core/src/agentkit_core/models.yaml` (select it with `--model`).
- **Add an agent:** write an `agent.yaml` (`apiVersion: agentkit/v1`, `kind: Agent`) that picks `tools`, `skills`, `prompt` and `subagents` by name from the libraries (`libraries/prompts/*.md`, `libraries/subagents/*.yaml`, skills). Run it with `research --agent path/to/agent.yaml`. Bad names fail at load time, listing the known ones.
- **Add a tool:** implement the `SearchTool`/`FetchTool` protocol or write a LangChain tool; pass it to `build_deep_agent(tools=...)`.
- **Live tests:** mark with `@pytest.mark.live`; run with `uv run pytest -m live`.

## Status

Done: T1-T9. There are 66 offline tests. T9 passed live on 2026-11-02. All six model ids answer a live call,
two real Decisions responses are now test fixtures, and the research agent runs end to end with Decisions
and Tavily. Results and eval scores are in `docs/phase0-results.md`.

Live testing of the sample agent uses only `fireworks-glm` (`accounts/fireworks/models/glm-5p3-flash`).
Its eval baseline is completed 1.00, citation validity 0.96, completeness 0.97 and groundedness 0.64.

OpenAI, Google and Anthropic use one cheap fast model on every tier: `gpt-6-luna`, `gemini-3.8-flash`,
and `claude-haiku-5-5`.

**Next: declarative agents and flows.** Build agents and LangGraph flows from YAML that picks tools,
skills, prompts, subagents and middleware from shared pools.
Spec: `docs/superpowers/specs/2026-11-01-agentkit-declarative-agents-design.md`.
Plan: `docs/superpowers/plans/2026-11-02-agentkit-declarative-agents-plan.md`.

**Phase 0b** (persistence, telemetry, tenant context, per-tenant stamps) is planned in
`docs/superpowers/plans/2026-11-01-agentkit-phase0b-plan.md` and not started.
