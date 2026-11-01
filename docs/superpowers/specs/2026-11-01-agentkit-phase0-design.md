# agentkit — Phase 0 design

Status: agreed direction, not yet a written plan. Next step: `superpowers:writing-plans` from this doc.

## Intent

Organizations with many product teams need one shared, self-hosted agent platform ("agentkit") so every team builds
agents the same way on DeepAgents / LangChain v1 / LangGraph — no managed-agent runtime.
Background research: `reports/Reusable agent platform components.md` and `research_notes/`.

## Phase 0 finish line (agreed with user)

A **deep-research agent** (think LangChain's GTM / deep research agent) built *through the agentkit
factory* runs end-to-end locally:

1. Takes a question, plans, gathers sources, optionally fans out read-only subagents, writes a cited report.
2. Switching provider is a config change only, across:
   - OpenAI
   - Google Gemini
   - Anthropic
   - Open-source via Fireworks:
     - `accounts/fireworks/models/deepseek-v4p1-flash-1017`
     - `accounts/fireworks/models/glm-5p3-flash`
     - `accounts/fireworks/models/minimax-m3p1-flash`
3. The **OpenAI Decisions API** (`POST /v1/decisions`, model `gpt-6-luna`,
   https://developers.openai.com/api/docs/guides/decisions) chooses the model tier and the visible tool set.
4. A small eval run scores the reports.

## Decisions made (Claude's calls — user may override)

- Python 3.12, **uv workspace monorepo**. Phase 0 only builds the packages the research agent needs:
  `agentkit-core` (config, model registry/`init_chat_model` wrapper), `agentkit-middleware`
  (Decisions-based tool + model selection), `agentkit-deep` (`build_deep_agent` factory),
  `agentkit-tools` (search/fetch tools), `agentkit-evals` (minimal runner on openevals),
  plus `apps/research_agent`. LangGraph builder, MCP, connectors, FastAPI server come in later phases.
- Pin versions as of 2026-11-01: deepagents 0.7.32, langchain 1.4.7, langchain-core 1.7.3,
  langgraph 1.2.19, openevals 0.2.2 (verify on PyPI at build time; one shared constraints file).
- Decisions API usage: ask **all tool-relevance predicates in one request** (API allows 1–400
  questions, caches shared `input` ≥1,024 tokens), plus a `choice` question for model tier. **Cache
  the selection per thread** rather than re-selecting on every model call (keeps provider prompt
  cache warm). Always include DeepAgents built-ins (`read_file`, `write_file`, `ls`, `task`, ...).
- Failure mode: if Decisions API errors/times out → keep all tools, stay on default tier (same as
  `deep_agents_utils_v1.0`), with real exponential backoff and a circuit breaker.
- Lift ideas from the user's repos but fix the issues listed in the report's repo-review table
  (constant backoff, no cache, sync-in-async, ledger `session=None`, hidden built-ins).
- Secrets via env: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `FIREWORKS_API_KEY`
  (+ search provider key). `.env.example` committed, `.env` never.

## Open (not yet answered by user)

- **Research data source** for phase 0 (which web search provider, or internal data). Builder default:
  a pluggable `search` tool interface with one web-search implementation; confirm with user.

## Non-goals for phase 0

Hosted server, Slack/channel adapters, identity/on-behalf-of, scheduling, MCP gateway, multi-tenant infra.
