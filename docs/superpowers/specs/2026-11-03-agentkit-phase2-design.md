# agentkit — Phase 2 design

Status: **draft**. Covers three platform-shape items taken from a review of DeepSeek Harness
(github.com/deepseek-ai/deepseek-harness: `docs/architecture.md`, `docs/tool-execution-pipeline.md`,
`docs/cordis-primer.md`). The rest of Phase 2's scope (see "Phase 2 scope" below) is still to be designed.
No implementation plan yet.

## Intent

Phase 2 ("Libraries") is about the second team in each tenant shipping agents using only library references:
the MCP gateway, the skills library, subagent specs, `PlatformGraph`, and calibrated judges. Three things
make that safe. Policy must be enforced at run time, not only when an agent is loaded. Capabilities must be
swappable without editing platform packages. And every model request must be reconstructable after the
fact, because trace-to-golden mining and single-step evals depend on it.

## What we take from DeepSeek Harness, and what we don't

DeepSeek Harness ("dsh") is built on the Cordis plugin framework: every part, including the agent loop, is a
plugin that can be replaced from config. That suits a single-user local harness. agentkit is a multi-tenant
policy layer on DeepAgents, so its value lies in the parts that **cannot** be replaced: the canonical
middleware order, tenant namespaces, and tool policy. The rule for this phase:

**Capabilities are plugins; policy is fixed.**

Not taken: owning the agent loop (LangGraph/DeepAgents owns it), a Cordis-style dependency-injection or
hot-reload framework (agents are built per run), and model-driven plugin mounting (dsh `extensions/`).

## Phase 2 scope

From `reports/Reusable agent platform components.md` (roadmap table), still to be designed:

- MCP gateway (ContextForge or equivalent) and `load_mcp_tools`
- Skills library with CI and Store sync
- Subagent YAML specs with mandatory response schemas
- `PlatformGraph` builder and `make_agent`
- Calibrated rubric judges with TPR/TNR cards
- HITL for tools with side effects (open item from Phase 1)
- Gating on a median/trimmed token metric (open item from Phase 1)

Designed here: items P2-A, P2-B and P2-C below. P2-A and P2-B are prerequisites for the MCP gateway and HITL;
P2-C is a prerequisite for trace-to-golden mining.

---

## P2-A. A guard tier that cannot be reordered

### Problem

- Tenant tool policy (`@platform_tool(tenants=...)`) is checked only when an agent is loaded
  (`agentkit_config/validate.py:127`). Nothing checks it when a tool is called. That is enough while every
  tool comes from a reviewed entry point. It stops being enough once MCP servers supply tools at run time.
- `side_effects` is recorded on every tool but nothing enforces it (Phase 1 open item).
- `TenantGuardMiddleware` is the only guard. The factory forces it first
  (`agentkit_deep/factory.py:78-97`). Any other policy is ordinary middleware, which `STACK_ORDER` ranks but
  an `agent.yaml` can leave out.

### Design

Borrowed from dsh's tool pipeline, which places "monotonic guards" between its transforming stages: checks
that can only **deny or abstain** and that no plugin can reorder.

- **Guard contract.** A guard is a `Guard` protocol with
  `check(call: ToolCallRequest, ctx: PlatformContext) -> Deny | None` (plus a model-call variant if needed).
  A guard cannot modify the call, cannot call `next()`, and cannot short-circuit with a substitute result.
  Returning `Deny` produces a refused `ToolMessage` naming the guard and the reason. A guard that raises
  counts as a deny (fail closed).
- **Fixed position.** One `GuardMiddleware` runs every registered guard inside `wrap_tool_call`, placed
  outermost among tool wrappers. It sits after selection and fallback, but before `tool_retry`, so a denied
  call is never retried. The factory always adds it, as it does `TenantGuardMiddleware`. `agent.yaml` cannot
  remove, reorder or wrap it.
- **Who supplies guards.** Only the platform and the deployment's tenant config. Guards come from an
  `agentkit.guards` entry-point group, and only those named in the tenant stamp are enabled. Agent specs
  cannot add or remove guards.
- **First guards.**
  1. `tenant_tool_policy`: re-checks `tenants` for the tool actually being called, closing the
     load-time-only gap for MCP or other dynamic tools.
  2. `side_effects`: a tool whose `side_effects` class is not allowed by the tenant policy is denied. This is the hook HITL will use: HITL becomes a guard outcome of "ask", resolved by an
     approval service. If nobody can answer, the call is denied.
  3. `call_budget` (optional): a hard per-tenant ceiling, kept separate from the per-agent `call_limit`.
- **Approval** (HITL design is still open). dsh resolves an "ask" *before* the guards and treats an
  unanswerable ask as a deny. We keep that rule; the approval transport (LangGraph `interrupt`, Slack,
  ...) is decided with HITL.

### Refinements after reading the code (2026-11-03)

- **Subagents.** deepagents gives the auto-added `general-purpose` subagent only its own default
  middleware; our custom middleware is not passed to it (`deepagents/graph.py`, `_gp_inheritable`). Declared
  subagents get only their spec's `middleware`. So `build_deep_agent` adds `GuardMiddleware` to every
  subagent spec, and supplies an explicit `general-purpose` spec carrying it. Without this, a tool called
  through `task` would bypass every guard.
- **Guards read no run context.** The tenant guard already pins the run's tenant to the deployment tenant,
  so guards are built from `Settings` (deployment tenant and policy) and judge only the call and the tool's
  `metadata["agentkit"]`. This also avoids depending on how deepagents passes the runtime context to
  subagents.
- **Side-effect values** are `read | write | external` (`ToolMeta`). The tenant stamp sets
  `AGENTKIT_ALLOWED_SIDE_EFFECTS` (default `read,external`, so `write` tools are denied until allowed).
- **Tools without agentkit metadata.** deepagents built-ins (`BUILTIN_TOOLS`) are passed through. Any other
  tool without metadata is denied as unregistered (fail closed); that is the MCP case.
- **Deferred:** the `agentkit.guards` entry-point group and `call_budget`. This plan ships the two built-in
  guards, which are always on; extra guards come when there is a third one.
- **Counting:** `ToolCallLimitMiddleware` counts calls in `after_model`, when the model emits them. Denied
  calls therefore count already; a test pins it.

### Acceptance

- A unit test proves no `agent.yaml` can drop or reorder `GuardMiddleware`: a spec that tries is a
  `SpecError`.
- A tool restricted to tenant B, injected after load (fake MCP tool), is denied for a tenant-A run with a
  `ToolMessage` naming `tenant_tool_policy`.
- A guard that raises results in a deny, not a crash and not an allow.
- A denied call is not retried by `tool_retry` and still counts against `tool_call_limit`. (Open question
  below: should it count?)
- Live: `verify-agentkit` run with a stamped tenant whose policy denies `fetch_url`; the transcript shows the
  denial and the report is still written.

---

## P2-B. Capability seams (interface / providers / consumer)

### Problem

agentkit discovers tools and middleware through entry points, but the providers *behind* a tool are
hard-coded. Adding a search backend means editing `agentkit_tools/factories.py:27` (`_CLASSES`). Secrets
support `env://` only (`agentkit_connectors/secrets.py`). The KB vector engine and embeddings are wired
directly in `agentkit_connectors/engines.py` and `embeddings.py`.

### Design

Borrowed from dsh's "capability seam": a swappable capability has an **interface** (a `Protocol` in a
platform package), **providers** (implementations, possibly from third-party packages), and **consumers**
(usually a model-facing tool). One of the three alone is not a seam; adding a capability means designing
all three.

- Each seam is an entry-point group, `agentkit.<seam>`, whose members are provider factories
  `(settings: Settings) -> <Protocol>`. The loader (`agentkit_core.seams.Seam`) lives in agentkit-core,
  because agentkit-tools and agentkit-connectors cannot depend on agentkit-config, where `Registry` is.
  It raises `ConfigError` for duplicate names.
- **This plan:** `agentkit.secrets` and `agentkit.search_backends`. `vectorstores`, `embeddings` and
  `tool_sources` come with the MCP gateway plan.
- Provider factories carry metadata like `@platform_tool` does (`owner`, `version`, `tenants`, and the
  secret refs they need), so `agentkit tools list` gains a sibling, `agentkit seams list`.
- Consumers depend on the `Protocol`, never on a concrete provider. That is already true of `web_search`
  (`SearchTool`); the change is where the providers come from.

| Seam (entry-point group) | Interface | Providers now | Consumers |
|---|---|---|---|
| `agentkit.search_backends` | `SearchTool` | parallel, brave, tavily, duckduckgo | `web_search` (`auto` chain order stays platform-owned) |
| `agentkit.secrets` | `SecretsProvider` | `env` | connectors, search keys; a `vault://` provider closes the Phase 1 open item |
| `agentkit.vectorstores` | to define (wraps `get_vectorstore`) | pgvector | `kb_search`, `agentkit-kb` |
| `agentkit.embeddings` | LangChain `Embeddings` + dimensions | current `get_embeddings` entries | `kb_search`, ingest |
| `agentkit.tool_sources` | to define (yields `BaseTool`s + metadata) | entry points (today's pool) | the MCP gateway becomes a second provider here |

- **Policy stays fixed.** Seams let a tenant *choose* a provider. They cannot weaken a guard: every tool a
  provider in `agentkit.tool_sources` yields still passes P2-A.
- **Snapshot.** Extend the tool-schema snapshot so provider names and versions per seam are frozen in CI.
  Without that, a newly installed provider would change behavior silently.

### Acceptance

- A test package in `tests/` registers a fake `agentkit.search_backends` provider through entry points, and
  `web_search: {backend: fake}` uses it with no edit to `agentkit-tools`.
- `env://` behavior and error messages are unchanged (existing tests pass); a fake `test://` secrets
  provider resolves through the same call sites.
- `auto` still produces Parallel -> Brave -> Tavily -> DuckDuckGo when only built-ins are installed.

---

## P2-C. "Model-visible means logged"

### Problem

dsh's rule: every model request must be reconstructable from the durable log, and any new model-visible
input needs a logged event. agentkit has checkpoints, OTel spans and `agentkit_usage` rows, but no stated
rule and no test. Known places where the request differs from checkpointed state:

- `SelectionMiddleware` filters tools and swaps the model in `awrap_model_call`. Tier and tool names are
  stored in private state (`agentkit_selection`), so this one is mostly covered.
- `ModelFallbackMiddleware` swaps the model on failure. Whether the model actually used is recorded in
  state is unverified; the ledger rows may record it.
- The system prompt is resolved from the prompt registry by label. Whether the resolved version is recorded
  per run is unverified.
- DeepAgents' own middleware (summarization, filesystem tools) rewrites history.

### Design

The first implementation plan covers step 1 only. Steps 2–4 are planned once the audit shows which fields
are actually missing. Known already: prompt `name@version` and the prompt hash are on the agent's run
metadata (`build_deep_agent`), and subagent requests are not in the parent thread's checkpoints at all.

1. **Audit first.** For one research-agent run, compare each model request as the provider received it
   (captured with a recording callback) against what can be rebuilt from checkpoint state + `agentkit_usage`
   + spans. The audit lists every field that cannot be rebuilt. Output: `docs/phase2-model-visible-audit.md`.
2. **Close the gaps by logging, not by restricting middleware.** Each middleware that changes a
   model-visible input writes what it decided into state (as selection already does) under one
   `agentkit_request` private-state key: model id actually used, prompt name@version, tool names offered,
   and redaction counts (counts only; never the redacted values).
3. **Rebuild function.** `agentkit_evals.reconstruct(thread_id, step) -> ModelRequestRecord` rebuilds a
   request from the durable stores. Single-step evals and future trace-to-golden mining use it instead of
   their own extraction.
4. **Rule for new middleware.** A platform middleware that changes a model-visible input without logging
   it fails review. A contract test enforces the rule for registered middleware.

### Acceptance

- Contract test: run the research agent offline against a fake model; for every step,
  `reconstruct()` equals the recorded request (messages, model id, tool names, prompt version).
- Live: one `verify-agentkit` run on fireworks-glm keeps the reconstructed requests next to the
  transcript under `evidence/verify/<run-id>/`, with a diff count of zero.
- Recording does not store PII that `pii` middleware redacted (test with a seeded email).

---

## Order of work

1. P2-C audit (small; tells us how much of P2-C is real work).
2. P2-B seams, starting with `agentkit.secrets` and `agentkit.search_backends` (both are refactors of code
   that already works, so lowest risk).
3. P2-A guard tier. The `tenant_tool_policy` guard ships before the MCP gateway; the `side_effects` guard
   ships with HITL.
4. Then the MCP gateway as an `agentkit.tool_sources` provider, behind P2-A.

## Decisions settled with the user (2026-11-03)

- A denied tool call **counts** against `tool_call_limit`, so a model that keeps calling a denied tool
  still runs out of budget.
- Guard configuration lives in the **tenant stamp** (`make stamp`): one place per tenant.
- Seams **allow tenant-private providers** (a package installed only in one tenant's deployment), gated
  by the provider's `tenants` metadata.
