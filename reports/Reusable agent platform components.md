# Standardize the harness before teams build agents

A self-hosted platform team serving two private-equity companies should build **one thin, opinionated "agentkit" monorepo**. Its centre is a pinned `create_deep_agent` factory (`deepagents==0.7.32`, `langchain==1.4.7`, `langgraph==1.2.19`). A sibling `StateGraph` builder shares its context, persistence and telemetry layers, and registries for tools, MCP servers, skills, prompts, subagent specs and connectors resolve declarative references at build time. A backend-neutral eval package gates every change. LangChain's own "company harness" post says the hard part is not the agent loop. It is five pieces of infrastructure around it: **channels, identity, two-tier memory, sandboxed code execution with a secret proxy, and scheduled runs**. LangChain gets all five from Managed Deep Agents, which you have ruled out, so the integration glue is exactly what your platform team must own ([Blog](https://www.langchain.com/blog/components-building-company-harness); [MDA](https://docs.langchain.com/langsmith/python/managed-deep-agents-overview)). The stack is moving fast. deepagents shipped about 15 patch releases in a month, langchain-core 1.7 broke tool-call streaming, planning became opt-in in deepagents 0.7, and MCP went stateless on 2026-07-28. That makes version pinning plus contract tests a first-class component rather than housekeeping. For agent design, the evidence (including your own `sub_agents_to_main_loop_v1.0` A/B) points to the same default: a **single folded loop with skills and an adaptive tool surface**, with subagents reserved for parallel, read-only fan-out under a typed completion contract. Your `deep_agents_utils_v1.0` middleware is worth lifting into the platform after fixing a handful of concrete bugs. Tenant isolation between the two firms should be hard (separate databases, keys, gateways and trace projects) while code is shared. Isolation within a firm can be soft, through namespaces and policy middleware.

## The company-harness blog describes infrastructure, and self-hosting means rebuilding its glue

Harrison Chase and Caspar Broekhuizen's 24 October 2026 post says three internal LangChain agents — a GTM agent, OpenSWE and Content Studio — "are all built in the same way," and offers that as "a general recipe for building company harnesses." Its five components are these ([Blog](https://www.langchain.com/blog/components-building-company-harness)):

- **Location**: Slack apps with "breakout threads", plus custom UIs where Slack falls short.
- **Identity**: called "the thorniest and trickiest problem". It mixes on-behalf-of (OBO) and fixed credentials per agent and per tool. The GTM agent's OBO email tools are available only in DMs, and Content Studio keeps an operation whitelist.
- **Memory**: global and per-user tiers, where the agent decides which tier a fact belongs in.
- **Code execution**: the harness runs outside the sandbox, uses a per-agent base image, and reaches external services through a secret proxy, so sandboxed code never sees credentials.
- **Scheduled and event-driven runs**: "a large share of runs are scheduled," including cron jobs that the agent creates for itself.

The post contains no code and says nothing about sharing tools, skills or prompts across teams. It describes runtime primitives, not a component library ([Blog](https://www.langchain.com/blog/components-building-company-harness)).

The architectural fact that matters for you is the layering. Managed Deep Agents "runs the open source Deep Agents harness rather than a second framework." The loop, filesystem tools, subagents and skills are identical. Channels, identity, connections (OAuth), memory, schedules and sandboxes are "declarations in a project file rather than services you build and operate," and there is **no self-hosted Managed Deep Agents** ([MDA](https://docs.langchain.com/langsmith/python/managed-deep-agents-overview)). The open-source SDK therefore gives you the harness, and your platform supplies the declarations' implementations. The closest open-source reference is `deepagents-talon` 0.1.0 (22 October 2026). It is a single event loop hosting Slack, Discord, Telegram and WhatsApp adapters, a persistent cron scheduler with agent-facing cron tools, MCP loading and pluggable checkpoint URIs. It requires Python 3.14, and its README says it is "not intended for production or enterprise use", lacking HITL policy, channel admin controls and multi-tenant boundaries ([Talon](https://pypi.org/project/deepagents-talon/)). Read it as a design reference, not a dependency.

| Blog component | What the OSS SDK already gives you | What the platform team must build |
|---|---|---|
| Location | LangGraph v2 streaming; Talon adapters as reference | Slack Bolt (or Teams) adapter mapping a channel thread to `thread_id`; review UIs on the event stream |
| Identity | `context_schema` run context; `wrap_model_call` + `request.override(tools=...)` for per-caller tool filtering ([Docs-MW](https://docs.langchain.com/oss/python/langchain/middleware/custom)) | OAuth token vault, per-tool identity policy (`obo` vs `service`), DM-only gating, operation allowlists |
| Memory | `MemoryMiddleware` (AGENTS.md) plus `CompositeBackend` routing to `StoreBackend` namespaces ([Docs-Backends](https://docs.langchain.com/oss/python/deepagents/backends)) | Namespace conventions, write protection on global memory, retention jobs |
| Code execution | `BaseSandbox` (implement `execute`, `upload_files`, `download_files`); partner packages `langchain-daytona` 0.0.9, `langchain-modal` 0.0.7, `langchain-runloop` 0.0.7 ([PyPI-DA](https://pypi.org/project/deepagents/0.7.32/)) | Self-hosted container sandbox subclass, base-image catalogue, credential-injecting egress proxy (no first-party OSS proxy exists) |
| Scheduled runs | Graph invocation by any caller; Talon cron tools as reference | Scheduler service (cron, Temporal or Celery beat), webhook listeners, an agent-facing `schedule_run` tool |

Two runtime decisions follow. The official Agent Server (`langgraph-api`) needs Postgres, Redis, a `LANGGRAPH_CLOUD_LICENSE_KEY` and egress to `beacon.langchain.com` unless air-gapped, so it is a licensed dependency rather than pure OSS ([Standalone server](https://docs.langchain.com/langsmith/deploy-standalone-server.md)). The default host should be **your own FastAPI service** running `AsyncPostgresSaver`, `AsyncPostgresStore`, SSE streaming, a run queue and your own auth. Self-hosted deployments have no default auth in any case ([Auth](https://docs.langchain.com/langsmith/auth.md)). Keep a `langgraph.json` in every app so `langgraph dev`, Studio and an optional licensed Agent Server profile keep working. The Apache-2.0 Aegra server is a third-party, SDK-compatible alternative worth evaluating ([Aegra mirror](https://github.com/fork-archive-hub/aegra-langgraph)).

## A fast-moving stack makes pinning and contract tests the first component

The release cadence is the platform's biggest operational risk. Between 2026-09-23 and 2026-10-23 deepagents went from 0.7.18 to 0.7.32. The last two releases removed the `handoff` mode alias and stopped importing `langchain_anthropic` and `langchain_openai` at import time ([Releases](https://github.com/langchain-ai/deepagents/releases); [PyPI-DA](https://pypi.org/project/deepagents/0.7.32/)). langchain-core 1.7.0 (22 October 2026) changed tool-call arguments to stream as `tool-call-delta` events. Streaming clients must upgrade first (core 1.6.13+), then servers ([Changelog](https://docs.langchain.com/oss/python/releases/changelog.md)). langgraph 1.2.18 changed `DeltaChannel` snapshots from every 1,000 updates to every 100, and langgraph-checkpoint 4.3.1 started rejecting NUL bytes in namespace labels ([LangGraph releases](https://github.com/langchain-ai/langgraph/releases)). Teams that each pin their own versions will drift within weeks. The platform should publish **one constraints file** and run a canary contract suite on every bump.

### Pinned versions as of 1 November 2026

| Package | Pin | Notes |
|---|---|---|
| Python | 3.12 (floor 3.11) | deepagents needs ≥3.11; 3.11+ avoids async context-propagation caveats in streaming ([Streaming](https://docs.langchain.com/oss/python/langgraph/streaming.md)); Talon alone needs 3.14 |
| `deepagents` | `==0.7.32` (2026-10-23) | requires `langchain>=1.4.7,<2`, `langchain-core>=1.7.0,<2`, `langchain-anthropic>=1.7.6`, `langchain-google-genai>=4.4.2`, `langsmith>=0.14.12` ([PyPI-DA](https://pypi.org/project/deepagents/0.7.32/)) |
| `langchain` | `==1.4.7` | requires `langgraph>=1.2.12,<1.3`; `mcp` extra pulls `fastmcp>=4.0.11` ([PyPI langchain](https://pypi.org/project/langchain/1.4.7/)) |
| `langchain-core` | `==1.7.3` | tool-call delta streaming change ([PyPI](https://pypi.org/pypi/langchain-core/json)) |
| `langgraph` | `==1.2.19` (2026-10-30) | node timeouts, error handlers, drain, v2/v3 streaming ([PyPI](https://pypi.org/pypi/langgraph/json)) |
| `langgraph-checkpoint` / `-postgres` / `-sqlite` | `4.3.1` / `3.2.0` / `3.1.3` | sqlite for dev only ([Checkpointers](https://docs.langchain.com/oss/python/langgraph/checkpointers.md)) |
| `langgraph-sdk` | `0.4.11` | resumable reconnects, thread priority ([LangGraph releases](https://github.com/langchain-ai/langgraph/releases)) |
| `langchain-anthropic` / `langchain-openai` | `1.7.7` / `1.7.3` | ([PyPI](https://pypi.org/project/langchain-anthropic/)) |
| `langchain[mcp]` + `fastmcp` | `1.4.7` + `4.1.4` | `MCPAdapter` is beta and supersedes `langchain-mcp-adapters` 0.3.2 ([MCP migration](https://docs.langchain.com/oss/python/migrate/langchain-mcp-adapters); [FastMCP](https://gofastmcp.com/updates.md)) |
| `openevals` | `>=0.2.2` | live; `agentevals` 0.0.9 is stale since July 2025 ([PyPI openevals](https://pypi.org/project/openevals/); [PyPI agentevals](https://pypi.org/project/agentevals/)) |
| `langsmith` | `0.14.16` | hard dep of deepagents; use as OTel emitter ([PyPI](https://pypi.org/project/langsmith/)) |
| `langfuse` | `5.1.0` | needs `langchain-core>=1` ([PyPI](https://pypi.org/project/langfuse/)) |
| Optional eval adapters | `deepeval 4.3.2`, `ragas 0.4.3`, `inspect-ai 0.3.287`, `mlflow 3.17.2` | ([PyPI deepeval](https://pypi.org/project/deepeval/); [PyPI ragas](https://pypi.org/project/ragas/)) |

Several deprecations should be encoded as lint rules, not tribal knowledge:

- `model=None` is deprecated and will be removed in deepagents 1.0.
- `BASE_AGENT_PROMPT` was deprecated in 0.7. With no profile and no `system_prompt`, the model receives an **empty** authored system prompt.
- Backend factories (`backend=lambda rt: ...`) have been deprecated since 0.5.0.
- `create_react_agent` is replaced by `langchain.agents.create_agent`.
- `langgraph-supervisor` is no longer maintained.
- `deepagents-cli` is deprecated in favour of the managed `mda` CLI.
- `TodoListMiddleware` is opt-in since v0.7.

Sources: ([PyPI-DA](https://pypi.org/project/deepagents/0.7.32/); [Docs-Overview](https://docs.langchain.com/oss/python/deepagents/overview); [LangGraph v1](https://docs.langchain.com/oss/python/releases/langgraph-v1); [Supervisor migration](https://docs.langchain.com/oss/python/migrate/langgraph-supervisor); [PyPI deepagents-cli](https://pypi.org/project/deepagents-cli/)).

### Recommended monorepo and package layout

No official LangChain guidance exists on uv workspaces or tool-plugin packaging, so the layout below is design inference. It does respect a verified constraint: the DeepAgents factory and the LangGraph builder must share context, persistence and telemetry ([LangGraph notes, Q9](https://docs.langchain.com/oss/python/langgraph/stores.md)).

```
agentkit/                              # uv workspace, one constraints.txt, private index
  packages/
    agentkit-core/        # PlatformContext, ids, errors, settings, version-contract tests
    agentkit-persistence/ # saver/store factories, EncryptedSerializer, pruning jobs, namespace helpers
    agentkit-telemetry/   # OTel bootstrap, Langfuse handler, TracePolicy presets, cost ledger
    agentkit-middleware/  # identity/tool policy, tenant guard, tool surface, limits, PII presets
    agentkit-deep/        # build_deep_agent() factory, backend composer, sandbox providers
    agentkit-graph/       # PlatformGraph builder, make_agent() around create_agent, run helpers
    agentkit-tools/       # registry, @platform_tool, schema-snapshot tooling (no domain tools)
    agentkit-mcp/         # load_mcp_tools() wrapper over langchain.mcp, gateway config
    agentkit-connectors/  # postgres, pgvector, qdrant/…, embeddings, secrets providers
    agentkit-prompts/     # git prompt registry loader, fragment composer, prompt hash
    agentkit-specs/       # AgentSpec/SubAgentSpec pydantic models, YAML loader, resolvers, linters
    agentkit-evals/       # metric protocol, runners, datasets, judges, sinks, pytest plugin
    agentkit-server/      # FastAPI host: auth, runs, SSE, queue, drain, scheduler hooks, Slack adapter
  libraries/              # content, owned by domain teams via CODEOWNERS
    tools/<domain>/       # separate distributions, discovered via entry points
    skills/{org,pe-a,pe-b,products/<p>,teams/<t>}/<skill>/SKILL.md
    prompts/{fragments,agents}/<name>/v<semver>.yaml
    agents/<name>/agent.yaml   subagents/<name>/subagent.yaml
    evals/<agent>/{cases.jsonl,rubrics/,cassettes/}
  templates/app/          # copier template: langgraph.json, Dockerfile, FastAPI entrypoint, evals
```

Code (packages) and content (libraries) have different change velocities and owners, so they are split. Content is versioned by semver per item. Tool packs publish under `[project.entry-points."agentkit.tools"]` so the registry discovers installed packs through `importlib.metadata.entry_points` ([Shared-libraries notes, §1](https://docs.langchain.com/oss/python/langchain/tools)).

## The DeepAgents factory owns ordering, identity, memory tiers and defaults

The factory's purpose is to make the right way the only easy way. Every team calls `build_deep_agent(spec, runtime)` and never calls `create_deep_agent` directly. The verified 0.7.32 signature takes `model`, `tools`, `system_prompt`, `middleware`, `subagents`, `skills`, `memory`, `permissions`, `backend`, `interrupt_on`, `response_format`, `state_schema`, `context_schema`, `checkpointer`, `store`, `debug`, `name` and `cache` ([PyPI-DA source](https://pypi.org/project/deepagents/0.7.32/)). The factory fills each one from a validated spec plus platform policy.

**System prompt injection.** The final prompt is assembled as USER → BASE → SUFFIX, with BASE and SUFFIX taken from the active `HarnessProfile`. Passing a `SystemMessage` preserves `cache_control` markers ([PyPI-DA](https://pypi.org/project/deepagents/0.7.32/)). `register_harness_profile` is module-global, which is inference from its signature. So keep **org policy in the factory's own prompt composer**: org safety fragment, then tenant compliance fragment, then agent role prompt, then tool-usage notes. Emit it as one `SystemMessage` with a cache breakpoint after the stable prefix, and log a hash of the resolved prompt to traces. Reserve harness profiles for per-model tuning such as `tool_description_overrides`. Anthropic reports that Claude Code's system prompt was cut by over 80% for advanced models, and its fold guidance assigns the system prompt to a central team ([Anthropic fold doctrine](https://claude.com/resources/articles/building-agents-when-to-fold-subagents-into-your-main-agent-loop)). Treat the base prompt as a thin map that points into skills and tools, not a manual.

**Middleware ordering.** DeepAgents wraps user middleware in a fixed stack. The base stack is Filesystem → SubAgent → Summarization → PatchToolCalls → AsyncSubAgent. Then come your middlewares. The tail is profile extras → Skills → Anthropic, Bedrock and Fireworks prompt caching → Memory → HITL → UnsupportedContent → ToolExclusion ([PyPI-DA source](https://pypi.org/project/deepagents/0.7.32/)). The `before_*` hooks run first to last, `wrap_model_call` nests with the first middleware outermost, and `after_*` hooks run in reverse ([Docs-MW](https://docs.langchain.com/oss/python/langchain/middleware/custom)). The factory should therefore insert one canonical ordered list:

1. Tenant guard (`before_agent`): validates `runtime.context`.
2. Identity and tool policy (`wrap_model_call`): strips OBO tools outside DMs and enforces entitlements.
3. Tool surface strategy.
4. `ModelFallbackMiddleware`, then `ModelRetryMiddleware`.
5. `ToolErrorMiddleware` and `ToolRetryMiddleware`.
6. `ModelCallLimitMiddleware` and `ToolCallLimitMiddleware`.
7. `PIIMiddleware`.
8. `TodoListMiddleware`, added explicitly because planning is opt-in since v0.7.

This lands fallback and routing before Skills, which is the position the Skills docstring expects. Use `HumanInTheLoopMiddleware(interrupt_mode="per_call")` (langchain 1.4.6+) through `interrupt_on`, so each interrupt carries a validated `response_schema` ([Changelog](https://docs.langchain.com/oss/python/releases/changelog.md)). Apply `TracePolicy(process_inputs=omit_payload)` to platform middleware that touches deal data, mirroring what `MemoryMiddleware` already does ([PyPI-DA](https://pypi.org/project/deepagents/0.7.32/)).

**Memory tiers.** Define three tiers explicitly. Ephemeral memory is per-run scratch that should not outlive the task. It covers `StateBackend` files such as `/large_tool_results/` and `/conversation_history/`, isolated subagent contexts, and summarization offloads. Short-term memory is the thread: messages and state persisted by `AsyncPostgresSaver`, pruned by a retention job because checkpoints accumulate ([Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)). Long-term memory is cross-thread: `StoreBackend` routes inside a `CompositeBackend`, where the longest prefix wins and the store is passed to `create_deep_agent`, not to the backend ([Docs-Backends](https://docs.langchain.com/oss/python/deepagents/backends)). The blog's global and per-user tiers become two AGENTS.md sources on two namespaces, loaded by `MemoryMiddleware` into an `<agent_memory>` block. That block already instructs the model to treat memory "as reference material, not as hidden system instructions" ([PyPI-DA](https://pypi.org/project/deepagents/0.7.32/)). Gate writes to global memory with `FilesystemPermission(mode="interrupt")` to stop one user poisoning a team's memory. For semantic recall beyond AGENTS.md, use `PostgresStore` with `index={"embed", "dims", "fields"}` and `store.search`. Remember that its default `limit` of 10 truncates silently ([Stores](https://docs.langchain.com/oss/python/langgraph/stores.md)). Skip `langmem`, whose last release was 0.0.30 in October 2025 ([PyPI langmem](https://pypi.org/project/langmem/)).

One trap matters. The documented namespace examples use `rt.server_info.user.identity`, which the Agent Server's auth populates. On a plain FastAPI host `server_info` may be absent, so derive every namespace from `runtime.context` instead ([Docs-Backends](https://docs.langchain.com/oss/python/deepagents/backends)).

**Tools, skills and subagents.** `tools=` is additive and "never removes a built-in." Hiding a built-in requires `HarnessProfile(excluded_tools=...)` ([PyPI-DA](https://pypi.org/project/deepagents/0.7.32/)). Skills load from directories containing skill directories, with the last source winning, so layer them org → tenant → product → team. Custom subagents do not inherit skills ([Docs-Skills](https://docs.langchain.com/oss/python/deepagents/skills)). A `general-purpose` subagent is auto-added unless a profile disables it. Disable it by default: it is the main route to subagent sprawl, and the folded default does not need it ([PyPI-DA](https://pypi.org/project/deepagents/0.7.32/)).

**Concurrency and multi-threading.** Graphs are stateless once compiled. Run one compiled graph per spec per process, with an async psycopg pool behind the saver and store, and cap concurrent runs per tenant with a semaphore or a Redis/Arq queue ([LangGraph notes, Q5](https://docs.langchain.com/oss/python/langgraph/streaming.md)). No documentation guarantees safe concurrent runs on the **same** `thread_id` outside Agent Server, so serialize per thread with an advisory lock (inference). Within a run, parallelism comes from parallel tool calls, `Send` fan-out and subagents. Any custom `state_schema` field that parallel subagents write needs a reducer, or the step fails with `InvalidUpdateError` ([PyPI-DA](https://pypi.org/project/deepagents/0.7.32/)). Long jobs belong in `AsyncSubAgent`, which is beta. It runs on any Agent Protocol server, accepts self-hosted auth via `headers`, and returns task IDs that survive compaction. Omitting `url` uses in-process ASGI, which works only with `ainvoke` ([PyPI-DA source](https://pypi.org/project/deepagents/0.7.32/); [Running subagents in the background](https://www.langchain.com/blog/running-subagents-in-the-background)).

**Telemetry.** Set `LANGSMITH_OTEL_ENABLED=true` and `LANGSMITH_OTEL_ONLY=true`. LangChain and LangGraph then emit OpenTelemetry spans with no code change, exported through standard `OTEL_EXPORTER_OTLP_*` variables to a collector that fans out per tenant ([LangSmith OTel](https://docs.langchain.com/langsmith/trace-with-opentelemetry.md)). Langfuse's `CallbackHandler` adds per-run `langfuse_user_id`, `langfuse_session_id` and `langfuse_tags` ([Langfuse](https://langfuse.com/integrations/frameworks/langchain)). Stamp `tenant`, `product`, `team`, `user_id`, `thread_id`, `agent_name`, `agent_version` and `prompt_hash` on every run's metadata.

### Factory sketch

The sketch uses APIs verified against the 0.7.32 and 1.4.7 sources. Where it relies on unverified behaviour, comments say so: built-in middleware constructor arguments, `request.runtime` inside `wrap_model_call`, and the `PostgresStore` import path.

```python
# agentkit_deep/factory.py — pins: deepagents==0.7.32, langchain==1.4.7, langgraph==1.2.19
from dataclasses import dataclass
from typing import Literal
from deepagents import create_deep_agent, FilesystemPermission, HarnessProfile, GeneralPurposeSubagentProfile
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
from langchain.agents.middleware import (
    TodoListMiddleware, ModelFallbackMiddleware, ModelRetryMiddleware, ToolRetryMiddleware,
    ToolErrorMiddleware, ModelCallLimitMiddleware, ToolCallLimitMiddleware, PIIMiddleware,
)
from agentkit_middleware import tenant_guard, identity_tool_policy, ToolSurfaceMiddleware
from agentkit_specs import AgentSpec, resolve_subagents
from agentkit_prompts import compose_system_message

@dataclass(frozen=True)
class PlatformContext:                       # context_schema: immutable, never model-visible
    tenant: Literal["pe_a", "pe_b"]
    product: str
    team: str
    user_id: str
    channel: Literal["dm", "channel", "cron", "api"]
    entitlements: frozenset[str]

def ns(*tail):                               # namespaces from context, NOT server_info
    return lambda rt: (rt.context.tenant, rt.context.product, *[
        getattr(rt.context, t) if t in ("team", "user_id") else t for t in tail])

def compose_backend(spec, sandbox=None):
    return CompositeBackend(
        default=sandbox or StateBackend(),    # sandbox => `execute` works; else returns error
        routes={
            "/memories/user/":   StoreBackend(namespace=ns("team", "user_id", "memories")),
            "/memories/global/": StoreBackend(namespace=ns("team", "global", "memories")),
            "/skills/":          StoreBackend(namespace=ns("skills")),   # synced, read-only
        },
    )

def build_deep_agent(spec: AgentSpec, rt: "PlatformRuntime"):
    tools = rt.tools.resolve(spec.tools, tenant=rt.tenant)          # registry + tenant allowlist
    tools += rt.mcp.tools_for(spec.mcp_servers)                      # gateway-only MCP
    middleware = [
        tenant_guard(rt.tenant),                                     # before_agent: ctx.tenant == deployment tenant
        identity_tool_policy(rt.tools.policy),                       # wrap_model_call: OBO only in DMs, entitlements
        ToolSurfaceMiddleware.from_spec(spec.tool_surface, rt),      # all | provider_native | typed | llm | retrieval
        ModelFallbackMiddleware(*spec.fallback_models),              # ctor args: verify vs 1.4.7 source
        ModelRetryMiddleware(), ToolErrorMiddleware(), ToolRetryMiddleware(),
        ModelCallLimitMiddleware(**spec.limits.model), ToolCallLimitMiddleware(**spec.limits.tools),
        PIIMiddleware(**rt.policy.pii),                              # per-tenant redaction rules
    ]
    if spec.planning:
        middleware.append(TodoListMiddleware())                      # opt-in since 0.7
    return create_deep_agent(
        model=spec.model,                                            # always explicit
        tools=tools,
        system_prompt=compose_system_message(spec.prompt, tenant=rt.tenant),  # SystemMessage w/ cache_control
        middleware=middleware,
        subagents=resolve_subagents(spec.subagents, rt),             # typed, response_format mandatory
        skills=[f"/skills/{layer}/" for layer in spec.skill_layers],  # org → tenant → product → team
        memory=["/memories/global/AGENTS.md", "/memories/user/AGENTS.md"],
        permissions=[
            FilesystemPermission(operations=["write"], paths=["/skills/**"], mode="deny"),
            FilesystemPermission(operations=["write"], paths=["/memories/global/**"], mode="interrupt"),
        ],
        backend=compose_backend(spec, rt.sandboxes.for_spec(spec)),
        interrupt_on=spec.interrupt_on,                              # destructive tools => HITL
        response_format=spec.response_format,
        context_schema=PlatformContext,
        checkpointer=rt.checkpointer,                                # AsyncPostgresSaver(serde=EncryptedSerializer)
        store=rt.store,                                              # AsyncPostgresStore (import path unverified)
        name=f"{spec.name}@{spec.version}",
    )
```

Disable the general-purpose subagent by registering a platform profile, for example `HarnessProfile(general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False))`. Register it once at import time inside `agentkit-deep`, so it applies uniformly and no team re-registers profiles ad hoc.

## A parallel LangGraph builder encodes the same policies for deterministic workflows

Not every product feature is an open-ended agent. Deal-document intake, covenant checks and nightly portfolio roll-ups are workflows with agentic steps. LangChain's own multi-agent taxonomy lists "custom workflow" next to subagents, handoffs, skills and router, and recommends checking whether a single agent suffices before reaching for orchestration ([Multi-agent](https://docs.langchain.com/oss/python/langchain/multi-agent)). The Graph API is the right base. It has explicit state schemas, reducers, `Command` and `Send` routing, per-node `RetryPolicy`, `CachePolicy`, `timeout` and `error_handler`, and graph-wide `set_node_defaults`. One trap again: **subgraphs do not inherit node defaults** ([Fault tolerance](https://docs.langchain.com/oss/python/langgraph/fault-tolerance.md)).

The builder has four jobs. It applies org defaults: `RetryPolicy` with `max_attempts=3` and exponential jitter, a `TimeoutPolicy`, and a logging `error_handler` that can return `Command` to a compensation node. It re-applies those defaults to every subgraph it builds. It rejects sync nodes, because timeouts only work on async nodes and a sync node with `timeout=` fails at compile time. And it chooses durability by profile: `"sync"` for financial and approval workflows, `"async"` for chat ([Fault tolerance](https://docs.langchain.com/oss/python/langgraph/fault-tolerance.md); [Checkpointers](https://docs.langchain.com/oss/python/langgraph/checkpointers.md)).

The run helper standardizes on `version="v2"`. That gives typed `StreamPart` chunks, and `invoke` returns `GraphOutput` with `.value` and `.interrupts`. It also wires SIGTERM to `RunControl.request_drain()`, so a rolling deploy stops at a superstep boundary with a resumable checkpoint ([Changelog](https://docs.langchain.com/oss/python/releases/changelog.md)). `recursion_limit` is a top-level config key with a default of 10,007. Graphs should use `RemainingSteps` to wind down gracefully ([Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api.md)).

The builder ships three templates:

- **`make_agent()`** wraps `create_agent` with the same middleware presets as the DeepAgents factory. It is for single-purpose agents that do not need the filesystem harness.
- **A router/fan-out template** built on `Send` and a synthesis node.
- **A subagent-as-tool helper**, the documented replacement for `langgraph-supervisor` ([Supervisor migration](https://docs.langchain.com/oss/python/migrate/langgraph-supervisor)).

```python
# agentkit_graph/builder.py — langgraph==1.2.19
import inspect, signal
from langgraph.graph import StateGraph
from langgraph.types import RetryPolicy, TimeoutPolicy, RunControl   # import paths: verify
from agentkit_core import PlatformContext
from agentkit_telemetry import log_node_error

ORG_RETRY = RetryPolicy(max_attempts=3, initial_interval=0.5, backoff_factor=2.0, jitter=True)
PROFILES = {"chat": dict(durability="async", timeout=TimeoutPolicy(run_timeout=120)),
            "transactional": dict(durability="sync", timeout=TimeoutPolicy(run_timeout=600, idle_timeout=60))}

class PlatformGraph:
    def __init__(self, state_schema, *, profile="chat", input_schema=None, output_schema=None):
        self.profile = PROFILES[profile]
        self.g = StateGraph(state_schema, context_schema=PlatformContext,
                            input_schema=input_schema, output_schema=output_schema)
        self.g.set_node_defaults(retry_policy=ORG_RETRY, timeout=self.profile["timeout"],
                                 error_handler=log_node_error)   # NOT inherited by subgraphs

    def node(self, name, fn, **kw):
        if not inspect.iscoroutinefunction(fn):
            raise TypeError(f"{name}: platform nodes must be async (timeouts require it)")
        self.g.add_node(name, fn, **kw); return self

    def subgraph(self, state_schema, **kw) -> "PlatformGraph":
        return PlatformGraph(state_schema, profile=self._profile_name(), **kw)  # re-applies defaults

    def compile(self, rt):
        return self.g.compile(checkpointer=rt.checkpointer, store=rt.store, cache=rt.node_cache)

async def run(graph, inputs, *, ctx: PlatformContext, thread_id: str, profile: dict):
    control = RunControl()
    signal.signal(signal.SIGTERM, lambda *_: control.request_drain())   # graceful drain on deploy
    cfg = {"configurable": {"thread_id": thread_id}, "recursion_limit": 200,
           "metadata": {"tenant": ctx.tenant, "product": ctx.product, "user_id": ctx.user_id}}
    async for part in graph.astream(inputs, cfg, context=ctx, version="v2",
                                    stream_mode=["updates", "messages", "custom"],
                                    durability=profile["durability"], control=control):
        yield part   # StreamPart(type, ns, data) -> SSE
```

Short-term memory in graphs is the same checkpointer. Long-term memory is the same `AsyncPostgresStore` with tuple namespaces such as `(tenant, product, user_id, "memories")`, read through `runtime.store`. Thread IDs should stay under 255 characters, and checkpoints should be encrypted with `EncryptedSerializer.from_pycryptodome_aes()`. The agent factory and the graph builder share `agentkit-persistence`, so a graph that embeds a deep agent as a node, or a deep agent that uses a compiled graph as a `CompiledSubAgent`, sees one consistent persistence and tenancy model ([Persistence](https://docs.langchain.com/oss/python/langgraph/persistence); [Checkpointers](https://docs.langchain.com/oss/python/langgraph/checkpointers.md)).

## Six shared libraries turn declarative references into governed capabilities

The registries share one design rule. **Agent specs reference capabilities by ID and version, and the factory resolves them under tenant policy at build time.** Teams compose; they do not copy-paste.

### Tools library: typed contracts, identity from runtime, metadata for governance

LangChain v1 tools treat the docstring as the model-facing description and the type hints as the schema. Per-run identity arrives through a hidden `runtime: ToolRuntime[Context]` parameter, which exposes `context`, `state`, `store`, `stream_writer`, `execution_info` and `tool_call_id`. It replaces `InjectedState`, `InjectedStore` and `InjectedToolCallId`. The recommended error pattern is `@wrap_tool_call` middleware that turns exceptions into `ToolMessage`s so the model can self-correct ([LangChain Tools](https://docs.langchain.com/oss/python/langchain/tools)). MCP's 2025-11-25 spec sets the same norm for validation errors (SEP-1303) ([MCP changelog](https://modelcontextprotocol.io/specification/2025-11-25/changelog)).

Anthropic's tool-design guidance adds the content rules:

- Prefer fewer, workflow-level tools and namespace them by service and resource.
- Return high-signal names rather than UUIDs.
- Offer a `response_format` enum; in Anthropic's example a concise response cost 72 tokens against 206 for a detailed one.
- Paginate and truncate.
- Write descriptions "as to a new hire."

([Writing tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents)). Adding one to five usage examples per tool raised complex-parameter accuracy from 72% to 90% ([Advanced tool use](https://www.anthropic.com/engineering/advanced-tool-use)).

The platform contract therefore requires:

- a Pydantic `args_schema` with a described field for every argument;
- a docstring that states when to use the tool and when not to;
- tenant and identity read only from `ToolRuntime.context`, **never** as LLM-filled arguments, which is the single most important cross-firm isolation rule;
- async I/O;
- typed exceptions.

Governance metadata goes on `BaseTool.metadata`. It mirrors MCP annotations and declares the blog's identity split:

```python
# libraries/tools/deals/agentkit_tools_deals/lookup.py
from typing import Literal
from pydantic import BaseModel, Field
from langchain.tools import tool, ToolRuntime
from agentkit_tools import platform_tool
from agentkit_core import PlatformContext

class DealLookupArgs(BaseModel):
    deal_name: str = Field(description="Deal code name as written in the CRM, e.g. 'Project Falcon'.")
    view: Literal["concise", "detailed"] = Field("concise", description="Use 'detailed' only when the user asks for terms.")

@platform_tool(owner="pe-a/deal-team", tenants={"pe_a"}, side_effects="read",
               identity="service", classification="confidential", version="1.3.0",
               examples=[{"deal_name": "Project Falcon", "view": "concise"}])
@tool("deals_lookup", args_schema=DealLookupArgs)
async def deals_lookup(deal_name: str, view: str, runtime: ToolRuntime[PlatformContext]) -> str:
    """Look up one deal's stage, owner and key dates. Use when the user names a specific deal.
    Do NOT use for portfolio-wide questions; use portfolio_search instead."""
    db = get_tenant_db(runtime.context.tenant)   # tenant from context only, never an LLM argument
    ...
```

The registry's `resolve(ids, tenant)` filters on tenant, scopes and classification. The identity middleware re-checks at call time as defence in depth. CI snapshots `tool.tool_call_schema.model_json_schema()` and fails a PR that changes the schema without a major version bump, because prompts and evals depend on the schema ([Shared-libraries notes](https://docs.langchain.com/oss/python/langchain/tools)).

### MCP as a common capability: gateway-only, stateless, wrapped

MCP's 2026-07-28 spec is a breaking, stateless redesign ([MCP blog](https://blog.modelcontextprotocol.io/posts/2026-07-28/)):

- The initialize handshake and `Mcp-Session-Id` are gone, so requests can hit any instance behind a load balancer.
- Multi Round-Trip Requests replace server-initiated elicitation and sampling.
- `Mcp-Method` and `Mcp-Name` headers let gateways route and meter without parsing bodies.
- List responses carry `ttlMs` and `cacheScope`.
- DCR is deprecated in favour of CIMD.
- Tasks, MCP Apps and Enterprise Managed Authorization become extensions.

FastMCP 4.x implements it. Version 4.0.0 removed server-initiated sampling and roots, and 4.1.2 applies component authorization after transforms. FastMCP 3.x's providers, transforms, component versioning and `require_roles` suit a shared server estate ([FastMCP updates](https://gofastmcp.com/updates.md)).

On the client side, `langchain.mcp.MCPAdapter` (`langchain[mcp]>=1.4.0`, beta) supersedes `MultiServerMCPClient`. It prefixes tool names as `{server}_{tool}` and maps `isError` to `ToolMessage(status="error")`. Interceptors move into `@wrap_tool_call`, and elicitation becomes LangGraph interrupts. String targets must be http(s) URLs, which guards against FastMCP executing a local file. Prompts and resources are not wrapped yet, and each tool opens its own session per call ([MCP migration](https://docs.langchain.com/oss/python/migrate/langchain-mcp-adapters); [LangChain MCP](https://docs.langchain.com/oss/python/langchain/mcp)).

The official MCP Registry does not accept private servers ([MCP registry preview](https://blog.modelcontextprotocol.io/posts/2025-09-08-mcp-registry-preview/)). Run a self-hosted gateway instead. IBM ContextForge (Apache-2.0) offers virtual servers, RBAC, user-scoped OAuth, OpenTelemetry and air-gapped deploys, though its README still references 1.0.0-RC-3 ([ContextForge](https://github.com/IBM/mcp-context-forge)). agentregistry catalogues MCP servers, agents and skills together ([agentregistry](https://pkg.go.dev/github.com/agentregistry-dev/agentregistry@v0.4.0)).

The topology is three rules:

1. Teams build servers on FastMCP 4.x.
2. The gateway exposes **one virtual server per tenant and persona**.
3. Agents connect only to gateway URLs, with per-user OAuth for OBO tools.

Because the adapter is beta, teams never import it directly:

```python
# agentkit_mcp/loader.py — wraps a beta API so teams never import langchain.mcp directly
from langchain.mcp import MCPAdapter          # beta; LangChainBetaWarning on import
from agentkit_core import PlatformContext

async def load_mcp_tools(server_ids: list[str], *, tenant: str, registry) -> list:
    entries = [registry.get(sid, tenant=tenant) for sid in server_ids]          # pinned versions only
    cfg = {"mcpServers": {e.id: {"url": e.gateway_url} for e in entries}}       # https gateway URLs only
    async with MCPAdapter(cfg) as adapter:
        tools = await adapter.list_tools()
    for t in tools:
        registry.assert_schema_unchanged(t)    # description/schema diff => block until reviewed
        t.metadata = {**(t.metadata or {}), **registry.governance_tags(t)}
    return tools
```

Tool poisoning is the dominant MCP risk. Pin server versions, diff descriptions and schemas on every registry update, ban ad-hoc stdio servers in production, and route destructive tools through `interrupt_on`. Note that Talon's sandboxing "does not cover MCP tools," a reminder that MCP sits outside your code-execution boundary ([Talon](https://pypi.org/project/deepagents-talon/)). Whether tools listed inside the `async with` block stay callable after it exits is not verified, given the per-call session model. Test this before relying on the sketch.

### Skills library: layered sources, CI validation, tool-linked disclosure

Agent Skills is a folder standard. A `SKILL.md` carries a `name` (1–64 lowercase characters, matching the directory) and a `description` (1–1,024 characters saying what the skill does *and when to use it*), plus optional `scripts/`, `references/` and `assets/`. Disclosure is progressive: about 100 tokens of metadata, then a body under 5,000 tokens, then resources ([Agent Skills spec](https://agentskills.io/specification)). DeepAgents adds three pieces:

- **pinned skills**, injected without waiting for the model to choose them;
- **`metadata.include_tools`**, which exposes named tools only after the skill is read (deepagents ≥0.7.22);
- per-thread caching, reset by setting `skills_metadata` to `None`.

Two failure modes need guarding. Passing a skill directory instead of its parent "fails silently," and a stale later-layer skill with the same name shadows the real one ([Docs-Skills](https://docs.langchain.com/oss/python/deepagents/skills)).

The library lives under `libraries/skills/{org,pe-a,pe-b,products,teams}`. CI runs:

- `skills-ref validate`;
- a name-and-directory match check;
- a token budget;
- a secret scan;
- a static review of `scripts/`;
- a **shadowing check** that flags same-name skills across layers;
- a **skills-to-tools lint** that fails when a skill names a tool missing from the consuming agent's surface.

The lint exists because of a bug in your A/B (see below). A sync job publishes approved versions into a read-only `StoreBackend` namespace, protected by a `deny` write permission. Keep `allowed-tools` advisory, because it is experimental, and enforce permissions in the registry and middleware.

### Prompt library: git as source of truth, fragments composed and hashed

Langfuse offers self-hostable versioned prompts under an MIT core:

- labels such as `production`;
- client-side caching that survives an outage;
- `get_langchain_prompt()` conversion;
- composition via `@@@langfusePrompt:name=X|label=production@@@`, for text prompts only.

Protected labels are an Enterprise feature when self-hosted ([Langfuse prompts](https://langfuse.com/docs/prompt-management/get-started); [Langfuse composability](https://langfuse.com/docs/prompt-management/features/composability); [Langfuse license](https://langfuse.com/self-hosting/license-key)). The LangSmith Prompt Hub is only self-hostable with a self-hosted LangSmith Enterprise licence ([LangChain KB](https://support.langchain.com/articles/7011309930-how-do-i-obtain-a-self-hosted-langsmith-license-key)).

Make git the source of truth. Store prompts as `prompts/<domain>/<name>/v<semver>.yaml`, with `{id, version, input_variables, template_format, messages, fragments, owner, eval_suite}` and a PR-only `labels.yaml`. Optionally sync to Langfuse for runtime serving and label flips. The composer assembles org safety, tenant compliance, role and tool notes with Jinja includes. It emits a `SystemMessage` with cache control and logs the resolved hash to every trace, so any output can be traced to an exact prompt.

### Subagent and agent definition library: YAML specs, mandatory contracts

DeepAgents `SubAgent` is a plain TypedDict. Setting `tools` **replaces** the parent's tools, which enables least privilege. `skills` are not inherited, `response_format` needs deepagents ≥0.5.3, and `mode="fork"` is experimental ([Deep Agents Subagents](https://docs.langchain.com/oss/python/deepagents/subagents)). There is no native YAML loader. Oracle's Open Agent Spec has a LangGraph adapter ([Agent Spec](https://oracle.github.io/agent-spec/development/adapters/langgraph.html)), and A2A v1.0 Agent Cards are a discovery standard (per secondary sources) ([AAIF](https://aaif.io/blog/a2a-v1-0-a-builder-s-guide-part-1-discovery-tasks-and-clients)). Both are useful as export formats, not as the internal source of truth, because they lag DeepAgents features.

The platform spec makes the safe path mandatory. It requires a `response_format`, defaults to read-only tools, and forbids write-side tools unless an approval gate is declared:

```yaml
# libraries/subagents/credit-memo-analyst/subagent.yaml
apiVersion: agentkit/v1
kind: SubAgent
metadata: {name: credit-memo-analyst, version: 2.1.0, owner: pe-a/risk, tenants: [pe_a], tags: [finance]}
spec:
  description: "Use to draft a credit memo from one deal's data room. Not for portfolio-wide questions."
  mode: isolated
  model: anthropic:claude-sonnet-4-6
  prompt: {ref: prompts/risk/credit-memo@^2, fragments: [org/safety, pe-a/compliance]}
  tools: [connectors.postgres.query_readonly@1, finance.dcf_calc@^1]   # replaces parent tools
  skills: [/skills/org/, /skills/pe-a/risk/]                          # not inherited; declare
  response_format: {ref: schemas/credit_memo.json}                    # REQUIRED completion contract
  side_effects: read                                                  # write requires approval_gate
```

### Connectors: pooled, config-driven, exposed only through curated tools

`PGVectorStore` from langchain-postgres uses a shared `PGEngine` pool (asyncpg or psycopg3). It supports custom metadata columns, `$eq`/`$in`/`$between` filters, mapping onto existing tables, `HybridSearchConfig`, and HNSW/IVFFlat indexes ([PGVectorStore](https://docs.langchain.com/oss/python/integrations/vectorstores/pgvectorstore)). `agentkit-connectors` should expose `get_vectorstore("kb-portfolio")` and `get_sql(...)` factories that read YAML holding a backend, a table, an embeddings ID and a `secret_ref: vault://…`. They return cached instances with one pool per DSN per process, and resolve secrets at factory time from a `SecretsProvider` interface (Vault or a cloud secret manager). Agents never touch connectors directly. They reach them through curated tools bound to read-only database roles and schema allowlists. The raw SQL toolkit should never be exposed to agents that serve both firms. Qdrant, Weaviate, Pinecone and Elastic adapters sit behind the same `VectorStore` interface. Their package versions were not researched.

## Evals gate every component change, from single steps to trajectories

LangChain's guidance on evaluating deep agents comes from shipping four of them:

- Write bespoke success logic per test.
- Make about half the cases **single-step**: interrupt before the tools node and assert on the pending tool call, because "regressions often occur at individual decision points."
- Make the rest full runs that assert on trajectory, final response and state or files.
- Gate multi-turn tests turn by turn, so they fail early.
- Give every test a fresh environment, and replay HTTP with VCR.

([Evaluating Deep Agents](https://www.langchain.com/blog/evaluating-deep-agents-our-learnings)). Their 2026 follow-up adds category tags such as `file_operations`, `retrieval`, `tool_use` and `memory`. It also adds efficiency metrics against an ideal trajectory: step ratio, tool-call ratio, latency ratio, and a solve rate that is 0 when the task is unsolved. A run of 6 steps against an ideal of 4 scores 1.5 ([How we build evals](https://www.langchain.com/blog/how-we-build-evals-for-deep-agents)).

`openevals` 0.2.2 supplies most primitives without a server:

- `create_llm_as_judge`, with prebuilt correctness, hallucination, RAG groundedness, plan-adherence, PII-leakage and prompt-injection prompts;
- JSON and exact-match evaluators;
- `create_trajectory_match_evaluator`, with `strict`, `unordered`, `subset` and `superset` modes and per-tool argument overrides;
- `create_trajectory_llm_as_judge`;
- `run_multiturn_simulation` with simulated users.

([openevals README](https://raw.githubusercontent.com/langchain-ai/openevals/main/README.md)). The LangGraph graph-trajectory extractor lives only in the stale `agentevals`, so vendor that small piece ([agentevals](https://github.com/langchain-ai/agentevals)).

### Rubrics, calibration and golden datasets

Rubric judges should be binary pass/fail with critiques, one judge per criterion, and an "unknown" option. Calibrate them against a single domain expert's labels split roughly 10–20% train and 40–45% each dev and test, with 30–50 passes and 30–50 fails. Report TPR and TNR rather than raw agreement, because an always-pass judge reaches 95% agreement at a 5% failure rate while catching nothing ([Hamel Husain](https://hamel.dev/blog/posts/llm-judge/); [Anthropic evals](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)). Golden datasets start at 10–50 real-failure tasks, grow from negative-feedback traces and annotation queues, are versioned immutably, and are pinned in CI ([LangSmith concepts](https://docs.langchain.com/langsmith/evaluation-concepts)). For non-deterministic agents, report pass^k alongside pass@k. At a 75% per-trial rate, pass^3 is only about 42% ([Anthropic evals](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)).

### Choosing a system of record

Self-hosted LangSmith needs an Enterprise licence, Kubernetes, ClickHouse and beacon egress ([LangSmith k8s](https://docs.langchain.com/langsmith/kubernetes)). Langfuse's MIT core includes evaluators, datasets, experiments, annotation queues and a CI action that fails a PR on `RegressionError` ([Langfuse evaluation](https://langfuse.com/docs/evaluation/overview)). MLflow 3.17 offers judge alignment via DSPy and versioned scorers ([MLflow scorers](https://mlflow.org/docs/latest/genai/eval-monitor/scorers/)). DeepEval 4.3 has the richest agentic metric set, including Tool Correctness, Argument Correctness, Step Efficiency and Plan Adherence, plus G-Eval and DAG metrics ([DeepEval](https://deepeval.com/docs/metrics-introduction)). Ragas covers RAG metrics and tool-call F1 ([Ragas](https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/)).

The recommendation: **openevals primitives behind a backend-neutral protocol, Langfuse as the default self-hosted system of record, and DeepEval/Ragas metrics as optional adapters.**

```python
# agentkit_evals/core.py
from dataclasses import dataclass, field
from typing import Protocol, Literal, Any

@dataclass
class AgentRun:                     # built from a live run OR a stored OTel trace (online == offline code)
    trajectory: list                # BaseMessages incl. tool calls
    final: Any
    state: dict
    files: dict[str, str]           # DeepAgents virtual FS snapshot
    node_path: list[str]            # LangGraph nodes visited
    tool_selections: list[dict]     # from RecordingToolSelector: routing accuracy
    usage: dict; latency_s: float

@dataclass
class Score:
    key: str; value: float; passed: bool | None; comment: str = ""
    metadata: dict = field(default_factory=dict)   # judge_version, calibration TPR/TNR

class Metric(Protocol):             # openevals-compatible: inputs/outputs/reference_outputs (+ run)
    key: str; kind: Literal["deterministic", "llm_judge", "human"]; version: str
    def __call__(self, *, inputs, outputs, reference_outputs=None, run: AgentRun) -> Score | list[Score]: ...

@dataclass
class EvalCase:
    id: str; inputs: dict; reference_outputs: dict | None
    mode: Literal["single_step", "full_run", "multi_turn_scripted", "multi_turn_simulated"]
    tags: list[str]; split: Literal["smoke", "regression", "capability", "holdout"]
    rubric_id: str | None = None; ideal: dict | None = None    # ideal steps/tool_calls/latency
    env_fixture: str = "fresh_state"; tenant: str = "synthetic"

# runners: run_case(target, case, rt) -> AgentRun
#   single_step: compile with interrupt_before=["tools"], assert pending tool_calls
#   full_run:    capture trajectory + final + state + files; efficiency ratios vs case.ideal
#   multi_turn:  openevals.run_multiturn_simulation or gated scripted turns
# compare(baseline, candidate) -> flip report; any pass->fail on regression split exits non-zero
```

The CI tiers are cheap deterministic and single-step smoke tests on every PR with VCR on, calibrated judges on merge, and nightly capability runs with k trials across candidate models. Judge results are cached on a key of (judge version, input hash, output hash). A judge without calibration metadata is not allowed to gate a merge.

## Fold by default, size the tool surface by catalog, and fix the two repos before lifting them

The convergent 2025–2026 position favours **one main loop with progressive disclosure**. Anthropic's 22 October 2026 fold doctrine lists the failure modes of multi-team subagent designs:

- lossy handoffs;
- subagent sprawl;
- the "Frankenprompt";
- overly local evals;
- latency, with one customer about 2× faster on a single loop.

It puts procedure in skills, actions and live data in tools, and reference material in knowledge bases. It warns that tool choice "tends to degrade once there are more than roughly 30–50 tool definitions." Its migration path starts with about 10 golden examples and calls subagents as tools with a shared response schema first. Then it folds one subagent at a time, checks which tasks flip, and runs each task several times ([Anthropic fold doctrine](https://claude.com/resources/articles/building-agents-when-to-fold-subagents-into-your-main-agent-loop)). Cognition's 2026 follow-up agrees that read-only subagents and clean-context review loops work, while "writes stay single-threaded" ([Cognition](https://cognition.com/blog/multi-agents-working)). Anthropic's research system is the steelman for subagents. A multi-agent setup beat single-agent Opus 4 by 90.2% on breadth-first research, at about 15× chat tokens. It was a poor fit for shared-context, tightly coupled work ([Anthropic multi-agent](https://www.anthropic.com/engineering/multi-agent-research-system)). The platform default is therefore a folded loop. Subagents are allowed only for parallel, read-mostly fan-out or measured context bloat, always with a mandatory response schema, and always with writes routed through the parent's approval gate.

### What your two repos show, and what they get wrong

`sub_agents_to_main_loop_v1.0` is an eval-first replication of LangChain's Paid Media Agent. Folding there means no `task` tool: one `create_deep_agent` loop with intent-grouped tools, per-entry-point capability profiles (Slack gets writes, scheduled runs get reads only), skills read on demand, and a proposal-only write path whose approve and apply steps live outside the agent, so "prompt injection cannot cross the gate." The Stage 5 A/B measured folded at **15/15, 17.5 s, about 19K tokens** against hierarchical at **12/15, 31.7 s, about 35K tokens**. Two failures were "skill/ability mismatch" and one was an empty synthesis. At 50 tools, all-visible passed 14/15 at 2.2× input tokens. A same-model per-turn `LLMToolSelectorMiddleware` cut tokens to 9.2K but scored 13/15 plus an error at 2.2× latency, with the selector's own tokens uncounted ([SA results](https://github.com/cwijayasundara/sub_agents_to_main_loop_v1.0)). The direction matches external evidence. As evidence in its own right, though, the experiment is weaker than it looks:

- The hierarchical parent never receives a `system_prompt`.
- Subagent tools are renamed (`check_performance` against the skills' `check_platform_performance`), so part of the "mismatch" is self-inflicted.
- Each scenario ran once.
- Live Decisions routing was never exercised, because without a `DECISIONS_API_KEY` every selection degraded to keep-all ([SA results/fw-baseline.md](https://github.com/cwijayasundara/sub_agents_to_main_loop_v1.0)).

`deep_agents_utils_v1.0` (`decision_harness`) turns model and tool decisions into typed predicate questions. It includes a 5 s timeout, retry that honours `Retry-After`, a three-failure circuit breaker, keep-all degradation, sticky per-thread model routing that keeps the prompt cache warm, and a cost ledger ([DH](https://github.com/cwijayasundara/deep_agents_utils_v1.0)). It is the best candidate to lift into `agentkit-middleware`. The review found concrete defects:

| # | Repo | Finding | Recommendation |
|---|---|---|---|
| 1 | DH `decisions.py` | `_sleep_for` computes `backoff_s * 2**max(0,0)`: constant ~0.25 s, attempt never passed | Pass attempt number; `min(cap, base * 2**attempt) + jitter`; unit-test the schedule |
| 2 | DH `tools.py` | `ToolSelector` has no cache, while `ModelSelector` does; with `per_call=True` every loop step re-asks with the same human text | LRU/TTL cache keyed on (intent hash, tool-catalog hash); default to select-once-per-intent |
| 3 | DH `middleware/tool_selection.py` | async path runs sync `_select` in an executor; async client unused | Call `selector.aselect` in `awrap_model_call` |
| 4 | DH | Selection sees only the last HumanMessage, missing tool results and plan state | Optional context window (last N messages + todo list) behind a flag; measure in the A/B harness |
| 5 | DH | Filters deepagents built-ins (`ls`, `read_file`, `task`, `write_todos`, …) unless listed | Default `always_include` = harness built-ins, so skills disclosed via `read_file` cannot vanish |
| 6 | DH `model_selection.py` | `_record` hard-codes `session=None` though `_thread_id()` exists | Attribute ledger entries to thread, tenant and agent version; emit as OTel span attributes |
| 7 | DH `selector.py` | Uses private `client._parse_classify` across modules | Make parsing a public, versioned API |
| 8 | DH design | Per-call tool filtering changes the cached prefix, which conflicts with sticky model routing; Manus warns against mid-task tool changes ([Manus](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus)) | Select per thread or per intent change; prefer masking or provider-native deferral where available |
| 9 | DH design | Hard-wired to one "Decisions API" (the SPEC excludes other backends) | Introduce a `ToolSelectorBackend` protocol: decisions, LLM, embeddings/BM25, provider-native |
| 10 | DH claims | "~83× cost cut" and "350 ms over 10 tools" come from another repo; catalog prices are placeholders | Reproduce them in the SA harness before quoting; label placeholders in code |
| 11 | SA `pyproject.toml` | `dependencies = []`; `pmf_agent` not packaged | Declare deepagents, langchain-openai and decision_harness; package both modules |
| 12 | SA A/B | Parent missing `system_prompt`; tool renames; one run per scenario; Decisions never live; selector tokens uncounted | Equalize prompts and tool names, k≥3 trials with pass^k, live Decisions arm, count selector tokens |
| 13 | SA Stage 6 | Only three arms | Add `ProviderToolSearchMiddleware` (Anthropic/OpenAI only; not Fireworks GLM) and a retrieval arm |
| 14 | Both | Pins at deepagents ≥0.7.22 | Move to the platform constraints (0.7.32 / 1.4.7 / 1.2.19 / openai 1.7.3) |

Two verification flags apply to the table. The existence of the "OpenAI Decisions API" (`/v1/decisions`, `gpt-6-luna`) and of the catalog's model names could not be confirmed outside the repo. The `ExtendedModelResponse` plus `Command(update=...)` persistence path was not checked against the langchain 1.4.7 reference ([DH notes](https://github.com/cwijayasundara/deep_agents_utils_v1.0)).

### The ToolSurface layer: one contract, strategies chosen by catalog size

The repos' decision table matches vendor guidance. Show all tools at 10 or fewer. Use intent filtering from 10 to 50. Beyond that, use deferred loading or constrained per-subagent sets. Anthropic's Tool Search cut a 58-tool, five-server setup from about 77K to 8.7K tokens (85%) and raised Opus 4.5 MCP accuracy from 79.5% to 88.1%. It recommends search for 10+ tools or definitions over 10K tokens, and keeping the 3–5 most-used tools non-deferred ([Advanced tool use](https://www.anthropic.com/engineering/advanced-tool-use)). Code-mode MCP took one workflow from about 150K to 2K tokens, at the cost of a secure sandbox ([Code execution with MCP](https://www.anthropic.com/engineering/code-execution-with-mcp)). Retrieval remains the hard part. ToolRet's best retriever reaches only nDCG@10 of 33.83, and on LiveMCPBench retrieval errors cause nearly half of all failures ([ToolRet](https://arxiv.org/pdf/2503.01763); [LiveMCPBench](https://arxiv.org/html/2508.01780v1)). `langgraph-bigtool` has not been released since June 2025 ([PyPI](https://pypi.org/pypi/langgraph-bigtool/json)).

The platform therefore exposes one middleware with pluggable strategies, a shared keep-all degradation contract and a shared routing-accuracy metric:

```python
# agentkit_middleware/tool_surface.py
from typing import Protocol, Literal
from langchain.agents.middleware import AgentMiddleware, ProviderToolSearchMiddleware, LLMToolSelectorMiddleware

HARNESS_BUILTINS = {"ls", "read_file", "write_file", "edit_file", "glob", "grep", "execute", "task", "write_todos"}

class ToolSelectorBackend(Protocol):          # decision_harness.ToolSelector becomes one implementation
    async def aselect(self, intent: str, cards: list[tuple[str, str]], *, k: int) -> list[str]: ...
    # raise SelectorUnavailable => middleware keeps all tools (degradation contract)

Strategy = Literal["all", "provider_native", "typed_selector", "llm_selector", "retrieval", "code_mode"]

class ToolSurfaceMiddleware(AgentMiddleware):
    """Select once per thread / intent change (cache-aware); always keep harness built-ins;
    record every selection for routing-accuracy evals."""
    @classmethod
    def from_spec(cls, cfg, rt) -> AgentMiddleware:
        n = rt.tools.count(cfg.tool_ids)
        strategy: Strategy = cfg.strategy or ("all" if n <= 10 else
                              "provider_native" if rt.models.supports_tool_search(cfg.model) else
                              "typed_selector")
        if strategy == "all":             return _Noop()
        if strategy == "provider_native": return ProviderToolSearchMiddleware(searchable_tools=cfg.deferred)
        if strategy == "llm_selector":    return LLMToolSelectorMiddleware(model=cfg.cheap_model,
                                              always_include=sorted(HARNESS_BUILTINS | set(cfg.pinned)),
                                              max_tools=cfg.max_tools)
        return cls(backend=rt.selectors[strategy], pinned=HARNESS_BUILTINS | set(cfg.pinned),
                   recorder=rt.telemetry.selection_recorder, cache_scope="intent")
```

## Hard walls between the two firms, soft walls within each

The two private-equity companies are separate legal and data domains. **Share code and content artifacts, never data planes.** Each firm gets its own deployment of the same images, with:

- its own Postgres database for checkpoints, store and pgvector;
- its own `LANGGRAPH_AES_KEY` for `EncryptedSerializer`;
- its own MCP gateway virtual servers;
- its own secret paths and OAuth vault;
- its own model-gateway keys and budgets;
- its own OTel collector route and Langfuse project;
- its own eval datasets, because golden sets built from traces contain confidential deal data.

The `tenant_guard` middleware asserts that `runtime.context.tenant` matches the deployment tenant. This catches misrouted requests rather than providing the isolation itself. Tool and MCP registries filter on `tenants` metadata at build time, so a firm A tool never appears in a firm B graph.

Within a firm, isolation is namespace-based. Store namespaces follow `(tenant, product, team, user_id | "global", kind)`. Threads carry `owner`, `tenant` and `product` metadata. The FastAPI host reimplements the semantics of `langgraph_sdk.Auth`: authenticate every request, stamp owner metadata on create, filter reads, and rewrite store namespaces. Self-hosted deployments have no default auth, and these handlers only run inside Agent Server ([Auth](https://docs.langchain.com/langsmith/auth.md)).

Identity follows the blog's split. Each tool declares `identity: obo | service`. OBO tools appear only in DM or API contexts with a user token. Service-credential tools carry operation allowlists such as read and draft but not send ([Blog](https://www.langchain.com/blog/components-building-company-harness)). Sandboxes never hold credentials: the egress proxy injects them. Skills and prompts layer org → tenant → product → team, so firm-specific compliance fragments override org defaults without forking them.

## A contribution model with a central core and federated content

Anthropic's fold guidance gives the governance split: "a central team owns the system prompt and end-to-end evals; domain teams own skills" ([Anthropic fold doctrine](https://claude.com/resources/articles/building-agents-when-to-fold-subagents-into-your-main-agent-loop)). Applied here, the platform team owns:

- `packages/*`;
- the constraints file;
- middleware ordering;
- the base prompt fragments;
- the eval core and the end-to-end suites for each shared agent.

Domain teams in each firm own `libraries/tools/<domain>`, skills, prompts, subagent specs and their agents' eval cases, enforced by CODEOWNERS.

Every content PR must:

- pass schema-snapshot and lint checks (tool schemas, skills-to-tools references, skill shadowing, prompt token budget);
- include or update eval cases;
- clear the smoke split with no pass-to-fail flips on the regression split, the same blocking rule your SA harness already applies to architecture changes.

New middleware or new capability types go through a short RFC. Everything is semver-versioned, and a tool schema change is a major bump. Removals follow a deprecation window. MCP's own 12-month minimum policy is a reasonable ceiling to mirror ([MCP blog](https://blog.modelcontextprotocol.io/posts/2026-07-28/)).

A weekly dependency-bump job runs the contract suite against the newest deepagents, langchain and langgraph patches. That suite covers `create_deep_agent` kwargs, middleware order, `StoreBackend` namespace behaviour, streaming chunk shapes and HITL resume. The job opens a PR only when the suite is green, which turns the 15-patches-a-month cadence into a controlled pipeline.

## Phased roadmap from foundations to ambient agents

The phase durations are planning estimates for a team of about four to six engineers, not sourced figures.

| Phase | Weeks | Deliverables | Exit criterion |
|---|---|---|---|
| 0. Foundations | 0–3 | uv monorepo, constraints file, `agentkit-core` context, persistence (AsyncPostgresSaver/Store, encryption, pruning), OTel + Langfuse telemetry, contract-test suite, per-firm infra stamps | Both firms' empty deployments pass contract tests; traces land in separate projects |
| 1. Factory v0 + eval core | 3–8 | `build_deep_agent` with fixed middleware order, memory tiers, permissions; tools registry with `@platform_tool`; Postgres/pgvector connectors; git prompt registry; eval core with single-step, full-run, deterministic and trajectory metrics; pytest plugin | One pilot folded agent per firm in production behind HITL, gated by a 20–50-case golden set |
| 2. Libraries | 8–14 | MCP gateway (ContextForge or equivalent) + `load_mcp_tools`; skills library with CI and Store sync; subagent YAML specs with mandatory response schemas; `PlatformGraph` builder and `make_agent`; calibrated rubric judges | Second team per firm ships using only library references; judges have TPR/TNR cards |
| 3. Tool surface + repo uplift | 12–18 | Lift fixed `decision_harness` into `ToolSurfaceMiddleware`; repaired SA harness as the platform's architecture A/B tool with k-trial pass^k, provider-native and retrieval arms; tool-ceiling stress test | Strategy defaults chosen from measured data, not vendor claims |
| 4. Company-harness glue | 16–24 | Slack adapter with breakout threads; OAuth vault + OBO policy; self-hosted sandbox + egress secret proxy; scheduler + `schedule_run` tool; async subagents on a self-hosted Agent Protocol server | First scheduled ("ambient") agent per firm; security review passed |
| 5. Online evals + 1.0 | 24+ | Online sampler with reference-free judges, trace-to-golden mining, dashboards per tenant, governance automation | Platform 1.0 tagged; deprecation policy published |

## Risks and unverified items that need a decision or a test

| Risk or unverified item | Why it matters | Mitigation |
|---|---|---|
| deepagents patch cadence (~15 releases/month) and pre-1.0 status; 1.0 will remove `model=None` | Silent behaviour changes across teams | Single constraints file, weekly canary contract suite |
| langchain-core 1.7 tool-call delta streaming | Breaks older stream clients | Upgrade UIs (core ≥1.6.13) before servers |
| `langchain.mcp` is beta; prompts/resources unsupported; post-`async with` tool lifetime unverified | API churn, runtime failures | Hide behind `agentkit-mcp`; integration-test against in-memory FastMCP |
| Agent Server licence/free-tier terms unverified; older docs conflict on custom auth | Accidental licensed dependency | Default to FastAPI host; review LangChain licensing before adopting |
| `server_info` absent outside Agent Server (unverified) | Namespaces collapse or error | Derive all namespaces from `runtime.context` |
| Constructor args of `ModelFallbackMiddleware`, `ModelCallLimitMiddleware`, `ToolRetryMiddleware`, `PIIMiddleware`; `request.runtime` in `wrap_model_call`; `PostgresStore` import path; `set_node_defaults` and `RunControl` import paths | Sketches may not run as written | Verify against installed sources in Phase 0 |
| Concurrent runs on one `thread_id` outside Agent Server undocumented | State corruption | Per-thread advisory lock |
| Store/checkpointer TTL config undocumented on fetched pages | Unbounded growth, retention non-compliance | Platform pruning job (`aprune`/SQL cron) |
| Async subagents are beta/preview; docs show a version label conflict ("1.9.0") | Long-running jobs fragile | Restrict to read-only jobs with synthesis contracts |
| Talon is experimental and requires Python 3.14 | Tempting shortcut for channels and cron | Use as reference only |
| No first-party OSS secret proxy | Credentials leak into sandboxes | Build an egress proxy; never mount secrets in sandboxes |
| "OpenAI Decisions API" and catalog model names unverified; DH benchmark claims not reproduced | Platform may depend on a non-existent or changing endpoint | Backend protocol; reproduce claims in the SA harness |
| SA A/B confounded and single-run | Over-confident architecture policy | Re-run with fixes and k trials before codifying |
| A2A v1.0 details from secondary sources; ContextForge still RC; Langfuse self-host telemetry claims conflict; protected prompt labels Enterprise-only | Standards and vendor drift | Verify primary sources before committing; keep git as prompt source of truth |
| Judge bias (position, verbosity, self-preference) not researched from primary sources | Miscalibrated gates | Use a different model family for judges; require TPR/TNR cards |
| Eval tool licences (DeepEval, Ragas, Inspect, Phoenix, MLflow) unverified | Compliance surprises | Legal review before adopting adapters |

## Conclusion

The platform is neither a framework on top of DeepAgents nor a fork of it. It is a **policy layer**: a fixed middleware order, context-derived namespaces, identity-tagged tools, layered skills, and contract tests that absorb upstream churn. All of it is expressed through extension points the SDK already exposes (`context_schema`, the user-middleware slot, `CompositeBackend` routes, `FilesystemPermission`, `HarnessProfile`). The managed product proves the shape. The self-hosted version differs mainly in the five glue services you must operate, so roadmap risk concentrates in Phase 4 (identity, sandbox secret proxy, scheduling), not in the agent code.

Two less obvious implications follow. First, folding changes what you measure. Once subagents disappear, **tool-routing accuracy and skills-to-tools consistency become the core quality metrics**. Your SA harness already measures the first and exposed the need for the second, which makes it a more valuable platform asset than any single agent built on it. Second, cache economics now shape architecture. Sticky model routing, select-once tool surfaces, a stable system-prompt prefix and deferred loading all serve the same goal of keeping the prompt prefix stable. A platform that standardizes those choices for every team across both firms will see cost and latency gains that no individual team could capture alone.
