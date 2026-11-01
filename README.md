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

## Status (end of cloud session 1)

Done and tested offline: T1, T2, T3, T5, T6, T7, T8, and the resilience half of T4.
Not done:
- **T4 Decisions client** — schema now in `docs/reference/openai-decisions-api.md` (copied from the guide; fields it doesn't document are marked). Implement a `Selector` (see `agentkit_middleware.selection`) that makes one batched request and wraps `call_with_retry`/`CircuitBreaker`, then pass `SelectionMiddleware(selector)` to `build_deep_agent(middleware=[...])`.
- **T9 live verification** — nothing has run against a real provider. Verify: Tavily request format, OpenAI/Gemini ids in `models.yaml` (placeholders), the three Fireworks ids, and the DeepAgents report extraction (`extract_report`) against a real run.
