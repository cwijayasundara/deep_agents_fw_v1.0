# deep_agents_fw_v1.0 — agentkit

Shared, self-hosted agent platform on DeepAgents / LangChain v1 / LangGraph for multi-tenant organizations.

- Research & architecture: `reports/Reusable agent platform components.md` (notes in `research_notes/`).
- Current work: **Phase 0** — see `docs/superpowers/specs/2026-11-01-agentkit-phase0-design.md`.
  Plan written: `docs/superpowers/plans/2026-11-01-agentkit-phase0-plan.md`. T1-T9 done (T9 live, 2026-11-02; results `docs/phase0-results.md`).
  Live tests of sample agents use **fireworks-glm only**.
- Declarative agents: spec `docs/superpowers/specs/2026-11-01-agentkit-declarative-agents-design.md`, plan
  `docs/superpowers/plans/2026-11-02-agentkit-declarative-agents-plan.md`. The research agent is now
  `apps/research_agent/agent.yaml` built via `agentkit-config` `load_agent` (CLIs take `--agent`/`--model`). Then Phase 0b.
- Phase 0b (report's Phase 0 foundations: contracts, PlatformContext, encrypted Postgres persistence, memory
  tiers, telemetry + cost ledger, per-tenant stamps): `docs/superpowers/plans/2026-11-01-agentkit-phase0b-plan.md`.
  Delivered and live-verified (2026-11-02; `docs/phase0-results.md`). **Phase 0 is complete.** Per-tenant
  stamps: `make stamp TENANT=<t>` (`deploy/README.md`).
- **Phase 1: partly done** (branch `phase1-early-fixes`; plan
  `docs/superpowers/plans/2026-11-02-agentkit-phase1-plan.md`, results `docs/phase1-results.md`): middleware
  stack (fallback, retry, call limits, PII, canonical order) and eval gates (golden set, trajectory/source
  metrics, `research-eval --gate/--write-baseline` against `apps/research_agent/evals/baseline.json`).
  Still open from the roadmap's Phase 1: pytest plugin, single-step evals, connectors, prompt registry,
  `@platform_tool`. The shipped research agent needs `FIREWORKS_API_KEY` for any `--model` (fallback).
  Open items: P10 thread-to-user binding, P3 primitive state plaintext, AES key rotation/backup;
  `eval-<hex>` users' store items are never pruned (prune deletes threads only); prune needs a
  tenant filter if DBs are ever shared.
- Web search defaults to DuckDuckGo (no key); Tavily is opt-in via `web_search: {backend: tavily}`.
- Providers to support: OpenAI, Gemini, Anthropic, Fireworks (deepseek-v4p1-flash-1017,
  glm-5p3-flash, minimax-m3p1-flash). Model/tool selection via OpenAI Decisions API (`gpt-6-luna`).
- Prior work to learn from (not vendored): github.com/cwijayasundara/deep_agents_utils_v1.0,
  github.com/cwijayasundara/sub_agents_to_main_loop_v1.0.
- Verification: use the project skill `verify-agentkit` (`.claude/skills/verify-agentkit/`) to prove a change
  in the real CLI: doctor, stamp a throwaway tenant, drive the research agent live on fireworks-glm, keep the
  report + transcript + spans + agentkit_usage rows + eval scores under `evidence/verify/<run-id>/`. Keep its
  feature map current with `/pstack:maintain-verification-skill`.
- Conventions: uv workspace, Python 3.12, pinned versions in one constraints file, never commit `.env`.
