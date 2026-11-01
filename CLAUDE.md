# deep_agents_fw_v1.0 — agentkit

Shared, self-hosted agent platform on DeepAgents / LangChain v1 / LangGraph for multi-tenant organizations.

- Research & architecture: `reports/Reusable agent platform components.md` (notes in `research_notes/`).
- Current work: **Phase 0** — see `docs/superpowers/specs/2026-11-01-agentkit-phase0-design.md`.
  Plan written: `docs/superpowers/plans/2026-11-01-agentkit-phase0-plan.md`. T1-T8 built (offline-tested; T4 from `docs/reference/openai-decisions-api.md`). Next: T9 live verification (needs network + keys). See README "Status".
- Providers to support: OpenAI, Gemini, Anthropic, Fireworks (deepseek-v4p1-flash-1017,
  glm-5p3-flash, minimax-m3p1-flash). Model/tool selection via OpenAI Decisions API (`gpt-6-luna`).
- Prior work to learn from (not vendored): github.com/cwijayasundara/deep_agents_utils_v1.0,
  github.com/cwijayasundara/sub_agents_to_main_loop_v1.0.
- After T9 (research agent runs end to end live), generate a project verification skill with
  `/pstack:create-verification-skill` (pstack plugin from the `cursor/plugins` marketplace). It must
  cover: launch the research agent CLI per provider/model, doctor (API keys present, Decisions API
  reachable), drive one real research question, keep the report + trace + eval scores as evidence.
- Conventions: uv workspace, Python 3.12, pinned versions in one constraints file, never commit `.env`.
