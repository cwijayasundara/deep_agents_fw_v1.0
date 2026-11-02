# agentkit — declarative agents and flows (YAML + loader)

Status: draft for review. Builds on Phase 0 (`2026-11-01-agentkit-phase0-design.md`).
Reference prior art: github.com/cwijayasundara/langchain_1_x_agent_builder (`configs/agents/*.yaml`,
`agent_api/services/*`).

## Intent

Today every new agent is Python: `apps/research_agent/src/research_agent/agent.py` hard-codes the
prompts, tools, the `researcher` subagent and the middleware. The user wants to **create agents by
picking the right tool, skills, system prompt, subagents and middleware from shared pools in a YAML
file**, and the same for LangGraph flows. Python is written only when a pool lacks a capability (a new
tool, a new middleware type, a new flow node function).

Why: many teams build agents on one platform; most new agents are new *combinations* of existing
parts. Config makes them cheap to create, reviewable as data, and lintable in CI (the contribution model
in `reports/Reusable agent platform components.md` — platform team owns code, domain teams own YAML,
prompts and skills).

## Goals

1. An `agent.yaml` format that fully describes a DeepAgents agent: model (registry entry + tier),
   selection mode, system prompt, tools, skills, subagents, middleware, output file.
2. Pools (registries) that resolve names to objects: tools, skills, prompts, subagents, middleware,
   models (existing `ModelRegistry`), and, for flows, node functions and state schemas.
3. A generic `load_agent(path, overrides=...)` → compiled DeepAgents graph, via the existing
   `build_deep_agent` factory.
4. Every reference checked **at load time, before any network call**, with all errors reported together
   (file, field path, what's wrong, what's known).
5. The research agent rebuilt as `apps/research_agent/agent.yaml`; behaviour unchanged; T9 runs it.
6. A `flow.yaml` format + compiler for deterministic LangGraph flows whose nodes are pool functions,
   YAML-defined agents, or human-review interrupts.
7. A `agentkit validate <paths…>` CLI for CI.

## Non-goals (this spec)

- Builder UI, REST API, runtime overrides through an API (user: "just the yaml and loader for now").
- MCP servers in YAML (no `agentkit-mcp` yet). The schema rejects unknown keys, so adding it later is
  additive.
- Memory/persistence keys. Phase 0b wires checkpointer/store/memory tiers inside the factory; YAML gains
  a `memory:` section only after 0b lands.
- Tenant filtering and layered pools (org → tenant → team), versioned prompt refs (`name@^2`). The
  library search path is a list so layering can be added without format changes.
- Flow fan-out (`Send`), subgraphs-in-flows, async subagents.

## Anti-goals (failure even if it works)

- **A god class/file.** The old builder's 1,400-line `agent_factory.py` is the counter-example. Hard
  rule: single responsibility per module; aim ≤ ~200 lines per module; no class that both parses,
  resolves and builds.
- An expression language in YAML. Conditions and transforms are named Python functions from a pool.
- Runtime code generation (the old builder's LLM-generated tools). New tools arrive as code via PR.
- Silent fallback on a bad reference (skip the unknown tool and carry on). Bad refs fail the load.
- Having to edit an agent's YAML to change provider. Provider stays a one-flag override.

## Constraints

- uv workspace, Python 3.12, pins in `constraints.txt`, mypy strict, ruff (existing conventions).
- deepagents 0.7.32: `create_deep_agent(..., skills: list[str], subagents: [SubAgent], backend=...,
  permissions=..., response_format=...)`. `SubAgent` keys: name, description, tools, model,
  middleware, interrupt_on, skills, permissions, response_format, system_prompt, mode. Subagent
  `tools` **replace** the parent's; subagent `skills` are **not** inherited.
- `build_deep_agent` stays the one place that calls `create_deep_agent` and owns platform middleware
  order. The loader feeds it; it never calls `create_deep_agent` itself.
- Spec parsing has no LangChain imports (pure pydantic), so CI lint is fast and dependency-light.

## The `agent.yaml` format

Illustrative (the `critic` subagent, `citations` skill and `call_limit` middleware show the format; the
converted research agent contains only what it has today):

```yaml
apiVersion: agentkit/v1
kind: Agent
name: research_agent
description: Deep-research agent that writes a cited report.
version: 0.1.0
tags: [research]

model: fireworks-glm        # ModelRegistry entry; override with --model
tier: default               # fast | default | strong
selection: decisions        # optional; omit = all tools, fixed tier

prompt: research/orchestrator          # PromptRegistry name -> libraries/prompts/research/orchestrator.md
tools:
  - web_search
  - fetch_url: {max_chars: 20000}      # name, or {name: params}
skills: [citations]                    # SkillRegistry names
subagents:
  - researcher                         # SubagentRegistry name -> libraries/subagents/researcher.yaml
  - name: critic                       # or inline, same shape as a subagent file
    description: Checks a draft report for unsupported claims.
    prompt: research/critic
    tools: [fetch_url]
middleware:
  - type: call_limit
    params: {max_model_calls: 40}
    enabled: true                      # format kept from the old builder
output: /report.md                     # file the CLI/eval treat as the result
```

A subagent file (`kind: SubAgent`) has `name, description, prompt, tools, skills, middleware, model?,
tier?, response_schema?`. `model` omitted = inherit the parent's resolved model.

Overrides: `load_agent(path, overrides={"model": "anthropic"})` and CLI `--model anthropic`
(and `--tier`, `--no-selection`). The six `apps/research_agent/config/*.yaml` files are replaced by
one `agent.yaml` + `--model`.

## Pools

| Pool | Source | Entry shape |
|---|---|---|
| tools | Python, registered by packages (e.g. `agentkit-tools`) | `name -> ToolFactory(ctx, **params) -> BaseTool` |
| middleware | Python | `type -> MiddlewareFactory(ctx, **params) -> AgentMiddleware` |
| node functions, routers, state schemas (flows) | Python | `name -> callable / type` |
| response schemas | Python (pydantic models) | `name -> type[BaseModel]` |
| prompts | files `libraries/prompts/<domain>/<name>.md` | text, optional front matter |
| skills | dirs `libraries/skills/<name>/SKILL.md` (Agent Skills standard) | path + parsed metadata |
| subagents | files `libraries/subagents/<name>.yaml` | `SubAgentSpec` |
| models | existing `ModelRegistry` (`models.yaml`) | unchanged |

`ctx` is a small `BuildContext` (settings, resolved model spec, agent name) so factories get API keys
without reading the environment themselves (e.g. `web_search` builds `TavilySearch` from settings —
today's `_require` logic moves into that factory).

Prompts render `{{agent_name}}` and `{{date}}` at build time; any other `{{var}}` is a load error.
Runtime-context variables are out of scope.

## Validation rules (load time)

Collected, not first-failure. Each error: file, YAML path (`subagents[1].tools[0]`), message, known
names.

- Unknown keys anywhere (`extra="forbid"`), wrong `kind`/`apiVersion`.
- Unknown model entry, tier, tool, skill, prompt, subagent, middleware type, response schema.
- Tool/middleware params not accepted by the factory signature.
- Duplicate tool names after resolution; subagent name clashes.
- Prompt with undeclared variables.
- **Skills-to-tools:** a skill whose `SKILL.md` metadata names tools (`metadata.include_tools` /
  `allowed-tools`) that the consuming agent (or subagent) does not have.
- Subagent without `response_schema`: **warning** in v1 (report wants it mandatory; the current
  researcher has none, and making it required would change T9 behaviour).
- Missing secrets are *not* a validation error (lint must run in CI without keys); they fail at build.

## Flows: the `flow.yaml` format

```yaml
apiVersion: agentkit/v1
kind: Flow
name: research_with_review
state: research.ReviewState            # state-schema pool
nodes:
  research: {agent: research_agent, input: question, output: draft}   # agent node
  critique: {fn: research.critique}                                    # function node
  review:   {interrupt: true}                                          # human-in-the-loop pause
edges:
  - START -> research -> critique
  - from: critique
    route: research.needs_rework       # router pool fn: state -> key
    to: {rework: research, ok: review}
  - review -> END
```

- Agent nodes reference an agent by name (agents pool = `agent.yaml` files on the search path) and map
  one state field in (as the user message) and one out (the agent's `output` file, else final message).
- Function nodes are plain `state -> partial state` callables (sync or async).
- `interrupt: true` compiles to a node that calls LangGraph `interrupt()`; resume value merged into state.
- The compiler validates: every node reachable from START, END reachable, router `to` keys are node
  names, no edge to an undefined node. Checkpointer is required when any interrupt node exists.
- Proof flow: `research_with_review` above, in `apps/research_agent`, offline-tested with a fake model.

## Module layout (single responsibility)

New package **`agentkit-config`** (my call on the name), plus small additions elsewhere:

```
packages/agentkit-config/src/agentkit_config/
  spec/agent.py        # AgentSpec, SubAgentSpec, ToolRef, MiddlewareRef (pydantic only)
  spec/flow.py         # FlowSpec, NodeSpec, EdgeSpec (+ "a -> b -> c" parsing)
  errors.py            # SpecError(file, path, msg), SpecErrors (collection)
  registry.py          # Registry[T]: register/get/names/contains; one small generic base
  pools/prompts.py     # PromptRegistry (file-backed) + renderer
  pools/skills.py      # SkillRegistry (dir-backed, parses SKILL.md front matter)
  pools/subagents.py   # SubagentRegistry (file-backed)
  pools/code.py        # code pools (tools, middleware, nodes, schemas) via entry points
  library.py           # Library: search path -> all pools; the one place pools are assembled
  validate.py          # cross-reference checks over a spec + Library -> SpecErrors
  resolve.py           # AgentSpec + Library + BuildContext -> factory kwargs
  load.py              # load_agent(): parse -> validate -> resolve -> build_deep_agent
  flow_compile.py      # FlowSpec -> StateGraph (uses load_agent for agent nodes)
  cli.py               # `agentkit validate`
```

- Code pools are populated through Python entry points (groups `agentkit.tools`, `agentkit.middleware`,
  `agentkit.nodes`, `agentkit.schemas`), so a new tool package plugs in without editing the loader
  (open/closed). My call; a decorator + explicit import list is the fallback if entry points prove awkward.
- `agentkit-tools` registers `web_search` and `fetch_url` factories; `make_research_tools` goes away.
- `agentkit-middleware` internals are untouched. `selection: decisions` in YAML is resolved by
  `resolve.py` into the existing `SelectionMiddleware` (the logic now in
  `research_agent/agent.py::_decisions_middleware` moves there). It is a top-level key, not a
  `middleware:` entry, because the factory owns where platform middleware sits in the order.
- `build_deep_agent` gains `skills`, `backend`, `permissions`, `response_format` pass-throughs as needed.
- Library roots: repo-level `libraries/` plus the app's own dir; search path configurable via
  `Library([...])` / `AGENTKIT_LIBRARY_PATH`.

## Skills mounting

Requirement: an agent sees **only its declared skills, read-only**. Builder's choice of mechanism —
likely a `CompositeBackend` route `/skills/` to a read-only view over the selected skill dirs, with
`skills=["/skills/"]` and a `FilesystemPermission` deny on writes. Must be proven by a contract test
(the report notes passing the wrong directory level "fails silently").

## Research agent conversion (first deliverable)

- `apps/research_agent/agent.yaml`, `libraries/prompts/research/{orchestrator,researcher}.md`,
  `libraries/subagents/researcher.yaml`. `prompts.py` and most of `agent.py` deleted.
- `cli.py`/`eval_cli.py` take `--agent apps/research_agent/agent.yaml` (default) and `--model`.
- Equivalence test: the YAML-built agent has the same tool names, subagent names/tools, system prompt
  text and middleware types as the current Python build. Existing tests keep passing.
- README "Test it manually" and Makefile updated; T9 runs through the YAML.

## Sequencing against other work (user's decision)

1. T9 finishes on the current Python build first. This spec does not block it.
2. This spec is built next. Afterwards T9 is re-run through `agent.yaml` as an equivalence check.
3. Phase 0b follows. Its plan gets updated first: the skills mount becomes one more route inside 0b's
   `memory_backend()`, and 0b's regression lanes use `--model` instead of the deleted config files.

## Order of work

1. `agentkit-config` spec models + errors + registry base + file pools (pure, no LangChain).
2. Code pools + tool/middleware factories; validate; resolve; `load_agent`; skills mounting.
3. Research agent conversion + equivalence test + `agentkit validate` in `make lint`/CI.
4. Flow spec + compiler + proof flow.

## Decisions settled after review (Claude's calls — user may override)

- **Equivalence baseline.** Before deleting anything, capture a snapshot from the current Python build
  (tool names, subagent names and tool lists, system prompt texts, middleware types) into a test fixture.
  The YAML build must match it. Then port `tests/test_agent.py` to the YAML path. "Keep passing" means
  the same behaviours, not the same files. The "exactly 6 config files" test is replaced by a test that
  `--model` accepts every registry entry.
- **Test seams.** `load_agent(path, *, library=None, overrides=None, model=None)`. Tests pass a
  `Library` whose code pools are replaced (fake `web_search`/`fetch_url` factories) and an optional
  `BaseChatModel` instance. `overrides` stays string-only (`model`, `tier`, `selection`). The flow
  compiler takes the same `library`/`model` and passes them to agent nodes.
- **Validate imports code.** `agentkit validate` loads the entry points, so it imports the tool and
  middleware packages. CI already installs the workspace. Only `spec/` stays free of LangChain imports,
  because that keeps it unit-testable, not because lint must be import-free.
- **Proof flow is test-only.** It runs offline with a fake model, `critique` and `needs_rework` are
  deterministic functions, and an in-memory checkpointer is used. There is no CLI. Agent-node `input`
  accepts one field or a list of fields. With a list, the user message is built from the fields as
  labelled sections (`## question`, `## critique`), so the rework loop sees the critique.
- **Context objects.** `BuildContext` is build-time (settings, model spec, agent name). When Phase 0b
  lands, it gains a `platform: PlatformContext | None` field. It never duplicates tenant fields.

## Left to the builder

Exact pydantic field types, error message wording, entry-point vs decorator mechanics (see above),
how `--model` overrides are plumbed, the skills-mount implementation (within the requirement), and
test layout — as long as the SRP rule and load-time validation hold.
