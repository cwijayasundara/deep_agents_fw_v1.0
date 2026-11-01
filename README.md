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
UV_CONSTRAINT=constraints.txt uv run research "your question" --config apps/research_agent/config/fireworks-glm.yaml
UV_CONSTRAINT=constraints.txt uv run research-eval --config apps/research_agent/config/anthropic.yaml --judge anthropic
```

Switching provider = pick a different file in `apps/research_agent/config/` (one line: `model: <registry entry>`).

## Layout

| Package | Purpose |
|---|---|
| `agentkit-core` | settings, model registry (`models.yaml`), `get_model` |
| `agentkit-tools` | Tavily search, HTTP fetch, LangChain tool wrappers |
| `agentkit-middleware` | retry/backoff + circuit breaker, per-thread `SelectionMiddleware` |
| `agentkit-deep` | `build_deep_agent` factory, scripted fake model for tests |
| `agentkit-evals` | dataset, citation checks, openevals LLM judge, runner |
| `apps/research_agent` | prompts, per-provider configs, `research` and `research-eval` CLIs |

## Extending

- **Add a provider/model:** add an entry to `packages/agentkit-core/src/agentkit_core/models.yaml` (and a config file in the app).
- **Add a tool:** implement the `SearchTool`/`FetchTool` protocol or write a LangChain tool; pass it to `build_deep_agent(tools=...)`.
- **Live tests:** mark with `@pytest.mark.live`; run with `uv run pytest -m live`.

## Status

Done and tested offline (53 tests): T1-T8, including the Decisions client/selector (T4) built from
`docs/reference/openai-decisions-api.md` with mocked fixtures. The shipped provider configs enable
`selection: decisions` (needs `OPENAI_API_KEY`) so Decisions picks the visible tools and the model tier.

Not done - **T9 live verification** (needs network access to the provider/Tavily/OpenAI hosts and keys):
- Record a real `/v1/decisions` response and replace the T4 fixtures; confirm the undocumented bits
  (refusal shape, answer ordering, rate limits, timeouts) and that `usage.input_tokens_details.cached_tokens` > 0
  on the second call of a thread.
- Verify the Tavily request format, the OpenAI/Gemini ids in `models.yaml` (placeholders), the three Fireworks ids,
  and `extract_report` against a real run.
- `uv run pytest -m live`, then `research-eval` for all six configs; record results in `docs/phase0-results.md`.
- Then generate the verification skill (see `CLAUDE.md`).
