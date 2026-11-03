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
- **Phase 1: complete** (branch `phase1-rest`). Part 1 (plan `docs/superpowers/plans/2026-11-02-agentkit-phase1-plan.md`,
  results `docs/phase1-results.md`): middleware stack (fallback, retry, call limits, PII, canonical order) and eval
  gates. Part 2 (plan `docs/superpowers/plans/2026-11-02-agentkit-phase1-rest-plan.md`, results
  `docs/phase1b-results.md`): `@platform_tool` + tenant tool policy (`agentkit tools list|snapshot`), versioned
  prompt registry (`libraries/prompts/<name>/v<x.y.z>.md`, `labels.yaml`), `agentkit-connectors`
  (`kb_search`, `sql_query`, `agentkit-kb setup|ingest`), single-step evals (`steps.jsonl`, `baseline_steps.json`),
  the pytest plugin (`--agentkit-live`), and the KB pilot `apps/kb_agent` (20-case gate passes; baseline
  `apps/kb_agent/evals/baseline.json`). Research golden baseline re-recorded 2026-11-02 from an outlier run (297k mean tokens; median 185k):
  token ceiling ~290k -> ~386k, groundedness reference -0.06; Phase 2: gate a median/trimmed token metric.
  KB runs: both `KB_DATABASE_URL` and `KB_READER_DATABASE_URL` are kb_reader DSNs; admin DSN only for setup/ingest.
  The shipped research agent needs `FIREWORKS_API_KEY` for any `--model` (fallback).
  Open items: P10 thread-to-user binding, P3 primitive state plaintext, AES key rotation/backup;
  `eval-<hex>` users' store items are never pruned (prune deletes threads only); prune needs a
  tenant filter if DBs are ever shared; tool side effects recorded not enforced (HITL is Phase 2); only `env://`
  secrets. Next: Phase 2 (roadmap in `reports/Reusable agent platform components.md`). Draft spec:
  `docs/superpowers/specs/2026-11-03-agentkit-phase2-design.md` (guard tier, capability seams,
  model-visible-means-logged; rest of Phase 2 still to design). Plan:
  `docs/superpowers/plans/2026-11-03-agentkit-phase2-platform-shape-plan.md`. **Phase 2a (platform shape) done**
  (branch `phase2-platform-shape`; results `docs/phase2a-results.md`, audit `docs/phase2-model-visible-audit.md`):
  `agentkit_core.seams.Seam`, `agentkit.secrets` and `agentkit.search_backends` seams, deny-only `GuardMiddleware`
  on the main agent and every subagent, `AGENTKIT_ALLOWED_SIDE_EFFECTS` per tenant stamp (default `read,external`;
  in tenant env files only), verify feature `tool-guards`.
- Web search `backend: auto` (default) chains Parallel -> Brave -> Tavily (each if its key is set) -> DuckDuckGo;
  pin with `web_search: {backend: <name or list>}`. Backends are the `agentkit.search_backends` entry-point seam (third-party ones by name only; `auto` uses the four built-ins). Rationale: `research_notes/2026-11-03-web-search-provider.md`.
- Providers to support: OpenAI, Gemini, Anthropic, Fireworks (deepseek-v4p1-flash-1017,
  glm-5p3-flash, minimax-m3p1-flash). Model/tool selection via OpenAI Decisions API (`gpt-6-luna`).
- Prior work to learn from (not vendored): github.com/cwijayasundara/deep_agents_utils_v1.0,
  github.com/cwijayasundara/sub_agents_to_main_loop_v1.0.
- Verification: use the project skill `verify-agentkit` (`.claude/skills/verify-agentkit/`) to prove a change
  in the real CLI: doctor, stamp a throwaway tenant, drive the research agent live on fireworks-glm, keep the
  report + transcript + spans + agentkit_usage rows + eval scores under `evidence/verify/<run-id>/`. Keep its
  feature map current with `/pstack:maintain-verification-skill`.
- Conventions: uv workspace, Python 3.12, pinned versions in one constraints file, never commit `.env`.
