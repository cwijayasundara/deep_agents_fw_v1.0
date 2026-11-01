# agentkit Phase 0 — implementation plan

Spec: `docs/superpowers/specs/2026-11-01-agentkit-phase0-design.md`
Finish line: a deep-research agent, built via `build_deep_agent`, runs locally, switches provider by config only,
uses the OpenAI Decisions API to pick model tier + visible tools, and is scored by a small eval run.

Versions verified on PyPI 2026-11-01: deepagents 0.7.32, langchain 1.4.7, langchain-core 1.7.3,
langgraph 1.2.19, openevals 0.2.2. All pins live in one `constraints.txt`.

Working rules: TDD (test first, then code), one commit per task, no network in unit tests (fakes/`respx`),
live-provider checks are opt-in via `pytest -m live`.

## Layout

```
pyproject.toml            # uv workspace root, members = packages/*, apps/*
constraints.txt           # single source of version pins
.env.example              # OPENAI_/ANTHROPIC_/GOOGLE_/FIREWORKS_API_KEY, SEARCH_API_KEY
packages/
  agentkit-core/          # settings, model registry, init_chat_model wrapper
  agentkit-middleware/    # Decisions client + tool/model selection middleware
  agentkit-tools/         # Search/Fetch interfaces + one web-search impl
  agentkit-deep/          # build_deep_agent factory
  agentkit-evals/         # minimal runner on openevals
apps/research_agent/      # config + prompts + CLI entrypoint
```

## Tasks

### T1 — Workspace scaffold
- uv workspace root, 5 package skeletons + app, Python 3.12, ruff + pytest + mypy config, `constraints.txt`,
  `.env.example`, CI-less `Makefile` (`make test`, `make lint`).
- Done when: `uv sync --constraint constraints.txt` and `uv run pytest` (empty) pass.

### T2 — agentkit-core: settings + model registry
- `Settings` (pydantic-settings) reading env; fails fast with a clear message naming the missing key for the
  *selected* provider only.
- Registry maps logical name → `(provider, model_id, kwargs)` for: OpenAI, Gemini, Anthropic, and the three
  Fireworks ids (`accounts/fireworks/models/...`). Tiers: `fast | default | strong` per provider, from YAML config.
- `get_model(spec)` wraps `langchain.chat_models.init_chat_model`.
- Tests: registry resolution, missing-key error, unknown provider error. No network.

### T3 — agentkit-tools: search/fetch
- `SearchTool` protocol (`search(query, k) -> list[Source]`) and `FetchTool` (`fetch(url) -> Page`, size-capped,
  timeouts, readable-text extraction). One concrete web-search impl behind the protocol (provider chosen by env;
  **default Tavily — confirm with user**). All tools async, read-only, return `Source(url, title, snippet)`.
- Tests with `respx`-mocked HTTP; includes timeout and oversize cases.

### T4 — agentkit-middleware: Decisions client
- Async `DecisionsClient` for `POST /v1/decisions` (model `gpt-6-luna`): one request carries shared `input`
  (so ≥1,024-token prefix caches), N boolean tool-relevance questions (1–400) plus one `choice` question for model tier.
- Real exponential backoff with jitter, per-request timeout, circuit breaker (open after K failures, half-open probe).
- Fix list from the report's repo review: no constant backoff, no sync-in-async, no hidden built-ins.
- Tests: request shape, response parsing, backoff schedule (fake clock), breaker transitions.
  Exact request/response schema must be copied from the API guide, not guessed — first step is to fetch and fixture it.

### T5 — agentkit-middleware: selection middleware
- LangChain v1 `AgentMiddleware` that on first model call of a thread asks Decisions once, then caches
  `(tier, tool_names)` per thread (keeps provider prompt cache warm); `wrap_model_call` applies the tier's model
  and filters `request.tools`.
- Always include DeepAgents built-ins (`read_file`, `write_file`, `edit_file`, `ls`, `glob`, `grep`, `write_todos`, `task`).
- Failure mode: Decisions error / open breaker → all tools, default tier; emit a structured warning once per thread.
- Tests with a fake `DecisionsClient`: caching (one call per thread), built-ins preserved, fallback path.

### T6 — agentkit-deep: `build_deep_agent`
- Factory: `build_deep_agent(settings, tools, subagents, prompt, middleware=[...])` → compiled DeepAgents graph,
  model resolved via T2, selection middleware from T5 attached by default, checkpointer injectable.
- Test: builds with a fake chat model and runs a one-step invocation; asserts middleware order and tool filtering.

### T7 — apps/research_agent
- Prompts: orchestrator (plan via todos → gather → synthesize → cited report to `report.md`), read-only
  `researcher` subagent (search + fetch only, returns findings with source URLs).
- Config: `config/{openai,gemini,anthropic,fireworks-deepseek,fireworks-glm,fireworks-minimax}.yaml`
  differing only in the model block.
- CLI: `uv run research "question" --config config/anthropic.yaml` → streams progress, writes the report.
- Test: end-to-end with fake model + fake search producing a report with ≥1 citation.

### T8 — agentkit-evals
- Runner over a small JSONL dataset (≈10 questions) using openevals LLM-as-judge for: citation presence/validity
  (programmatic URL check against gathered sources), groundedness, completeness. Judge model configurable.
- Output: per-question scores + aggregate JSON/markdown table; `--config` selects the agent provider so results
  compare across all six model configs.
- Test: scoring logic with canned reports; dataset schema validation.

### T9 — Live verification + docs
- `pytest -m live` smoke per provider (one cheap call each) and one full research run per provider config.
- Run evals across all six configs; record results table in `docs/phase0-results.md`.
- README: quickstart, how to add a provider, how to add a tool. Update `CLAUDE.md` "Current work" to Phase 1.

## Order and dependencies

T1 → T2 → (T3, T4 in parallel) → T5 → T6 → T7 → T8 → T9.
Live tasks (T9) need all four provider keys plus a search key; everything before it runs offline.

## Risks / things to confirm

- **Search provider** (open question in spec) — plan assumes Tavily behind a swappable interface.
- Decisions API is new: schema fixture in T4 is the first thing built; if the shape differs from the spec's
  assumptions, T5's design (single batched request, per-thread cache) is the part to revisit.
- Fireworks model ids are from the spec; verify they resolve at T9 and adjust the registry if not.
- Provider-specific tool-calling quirks (Gemini schema strictness, Fireworks OSS models) may need per-provider
  kwargs in the registry — expect to discover these in T9.
