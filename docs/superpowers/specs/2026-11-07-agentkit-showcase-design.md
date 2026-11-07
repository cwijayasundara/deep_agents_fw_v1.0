# agentkit showcase: "One chassis, many agents" — design

Date: 2026-11-07 · Status: draft for approval

## Intent and why

We need one piece that shows how agentkit uses DeepAgents with tools, subagents, prompts, connectors,
middleware and guards, and how a **new agentic system is created by configuring parts, not writing code**.

Audience: **a customer and our own team members.**

- The customer should leave believing *"we could stand up our own agent by configuring parts — and the
  platform keeps it safe."*
- The team should leave knowing *where each part lives in the repo* and how YAML resolves to a running harness.

It is **presented live** in a meeting, then **shared as a link** for the audience to explore afterwards.

Positioning, from a survey of peers (2026-11-07): the industry shows "configure, don't code" with
template galleries (LangSmith Fleet; OpenAI Agent Builder, sunsetting 2026-11-30), manifest files (Google ADK
Agent Config, CrewAI YAML, M365 declarative agents, kagent CRDs, Letta `.af`, Dify DSL), or "same recipe, many
agents" (LangChain, *The five components of building a company harness*, 2026-10-24: channel presence,
identity, memory, sandboxes, scheduled/ambient runs). None of them visibly shows **configuration bounded by
guardrails the config cannot remove** — that is agentkit's differentiator and the spine of this piece.

## Goals

1. A **recipe matrix**. Rows are the parts:
   - model and fallback
   - prompt (name and version)
   - tools
   - subagents
   - connectors
   - middleware
   - guards
   - memory tier
   - tenant side-effect policy
   - evals and gates

   Columns are `research_agent`, `kb_agent`, and an empty **"your agent"** column. Cells that are the same for
   every agent (platform-provided) are styled differently from cells that differ (set in config). The visible
   claim is "two different agents, roughly 10 lines of YAML apart".
2. An **assembly view**. Pick an agent and its `agent.yaml` appears, with each line linked to the part it
   resolves to. The resolved harness is drawn as layers:
   - outermost: the guards the factory always adds (marked "YAML cannot remove or reorder");
   - the canonical middleware order (YAML order does not matter);
   - the model with its fallback;
   - the tools, filtered by tenant policy;
   - the subagents, each with its own guard and middleware.

   Every part links to its source path in the repo, which is the team's map.
3. A **build-your-own bench**:
   - Clone a template card (research or kb) and toggle tools, subagents, connectors and middleware. The
     generated YAML updates live.
   - It shows the platform rules as warnings, for example a tool whose side-effect class the tenant does not
     allow, a missing `require_output`, or an unknown part.
   - It ends with the real command to run: `agentkit validate …` and then `uv run research --agent <file>`.
   - The bench **does not** run agents in the browser.
4. A **run replay**. A recorded real run plays back step by step: model calls, tool calls, subagent
   delegation, the guard, a hit limit or fallback when one occurs, PII masking, the final `/report.md`, and
   tokens and cost. Each event lights up the part in the assembly view that handled it.
5. **Positioning.** agentkit is compared against LangChain's five components and the peer survey above, and
   it marks honestly where agentkit is behind: no channel or Slack presence, no sandbox, no crons, HITL and MCP
   still open. Skills and MCP are shown as **"coming (Phase 2)"**, not faked.
6. **Two modes on one page.**
   - **Presenter mode:** arrow keys step through a guided story (matrix → assembly → bench → replay →
     positioning), with one highlighted takeaway per step.
   - **Explore mode:** the default for the shared link. All views are free to click, with a short "start here"
     strip.

## Non-goals

- Running agents, calling models, or touching Postgres/OTel from the page.
- A full visual agent editor or round-trip graph-to-YAML editing. The bench only generates YAML.
- Replacing `architecture.md` or the existing inventory catalog. This page complements them.
- A slide deck.

## Anti-goals (a failure even if it works)

- **Drift:** a hand-written page that disagrees with the repo. Everything except the narrative copy and the
  peer comparison must be **generated from the repo** by introspection.
- **Faking capabilities:** showing skills, MCP, HITL or Slack as working when they are not.
- **Leaking open items:** the "Open items / decision debt" list (P10 thread binding, P3 plaintext primitive
  state, AES key rotation and so on) must **not** appear anywhere in the page or its embedded data.
- A demo that depends on a network, an API key or a live model during the meeting.

## Constraints

- It builds on the existing introspection in `scripts/platform_catalog.py` (stdlib and pyyaml; it reads entry
  points, model registry, libraries, apps and evals; it never reads secret values, only key names). It is
  currently uncommitted.
- One generator gives two outputs:
  - `--serve`, a local live page for the meeting;
  - `--write <path>`, a self-contained HTML snapshot. Claude publishes the snapshot as a private claude.ai
    Artifact link, and the user decides when to share it.
- The snapshot must work offline as a single file: inline CSS and JS, no CDN dependency.
- The guard and middleware ordering shown must come from the same source the factory uses, not a copied list.
- Data the customer may see: eval scores, token and cost figures, baselines, and the text of real research
  runs. Excluded: the open-items list.
- Repo conventions: uv workspace, Python 3.12, never commit `.env`.

## Decisions made

- **User:** both live presentation and a shared link; hide the open items; everything else may be shown.
- **Claude's call:** the "One chassis, many agents" concept, with the four views plus positioning.
- **Claude's call:** extend the existing catalog generator rather than starting a new tool.
- **Claude's call:** the replay source. The existing evidence is thin: `evidence/audit/.../captures.jsonl` has
  8 model-visible captures holding hashes only. So we record **one fresh live research run on fireworks-glm**
  via the `verify-agentkit` skill and commit a trimmed **replay fixture** (events, tool args and results cut
  to a short preview, token and cost rows) under `evidence/showcase/`. A KB-agent replay is optional.
- **Claude's call:** the bench's validation warnings mirror the real rules, imported or derived from
  `agentkit-config`. Where that is impractical, a warning is labelled as a hint, and the CLI command is shown as
  the authority.

- **User (hiding):** what is hidden is the **whole decision-debt list**. That covers P10 thread-to-user
  binding, P3 primitive state plaintext, AES key rotation and backup, `env://`-only secrets, `eval-<hex>`
  store items never being pruned, the prune tenant filter, and the innermost guard check. These must not
  appear in the page, its embedded data, the replay fixture or the report text, and a test enforces the
  denylist against the generated HTML. Features that are **not built** may and should be named honestly:
  MCP, HITL approval, sandbox, crons/ambient runs, and Slack/channel presence.
- **User (replay):** the topic is **agentic AI platforms**. The run is **steered** so the guardrails visibly
  fire:
  - the question includes an email address, so PII masking shows;
  - one tool limit is set low enough to trip, using a demo `agent.yaml` variant under `evidence/showcase/`,
    never the shipped one.

  The full report may be shown to the customer.
- **User (code change):** a small product-code change is allowed. Export the guard order, and a description
  of the memory routes, as constants that `agentkit_deep/factory.py` and the catalog both read, with a test
  showing the factory follows the constant. The verify feature `tool-guards` must still pass.
- **Repo fact:** skills are **supported, none shipped yet**. `skills:` is an agent-spec field and the factory
  mounts `/skills/<owner>/`. Show skills as a real matrix row and bench toggle with the note "supported; no
  skills in the library yet". MCP, HITL, sandbox, crons and Slack are the parts shown as "coming".
- **Claude's call:** the tenant policy shown is the committed `deploy/tenants/example.env` value
  (`read,external`), labelled "example tenant". It is never read from the presenter's shell. The bench has a
  read-only toggle (read / external / write) to show what a stricter or looser tenant would allow.
- **Claude's call:** the customer snapshot leaves out machine state: which API keys are set, `.env` key names,
  and the presence of local DSNs. `--serve` may still show them to the team.
- **Claude's call:** the bench's run command depends on the template.
  - Research-derived agents: `uv run research --agent <file>`.
  - KB-derived agents: also `uv run research --agent <file>` (the verify-agentkit skill runs `kb_agent` this
    way), with the prerequisites listed (kb_reader DSNs, `agentkit-kb setup|ingest`).
  - In both cases `agentkit validate` comes first.

## Left to the builder

- Visual design, layout, typography and the diagram style of the layered harness.
- Whether the showcase is a new section or tab of the existing catalog page or a separate page from the same
  generator.
- The replay fixture's schema and how it is trimmed. Keep it small and stable, and strip secrets and DSNs.
- How "same as platform" versus "set in config" is computed for matrix cells.
- The exact presenter-mode copy (one takeaway per step).
- Tests: introspection unit tests, plus a check that the open-items text never appears in the generated HTML.
