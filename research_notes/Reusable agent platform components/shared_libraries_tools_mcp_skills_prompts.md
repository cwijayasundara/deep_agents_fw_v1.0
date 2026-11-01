# Shared, Reusable Libraries for an Enterprise Agent Platform (Tools, MCP, Skills, Prompts, Subagents, Connectors) on LangChain v1 / LangGraph / Deep Agents

Research date: 2026-11-01. Scope: self-hosted only. Every claim below has a source except items in "Inferences" (my design reasoning) and "Gaps".

Version snapshot (as found):
- MCP spec: **2026-07-28** (released Jul 28, 2026; stateless core), previous **2025-11-25**.
- FastMCP: **4.1.4** (Oct 26, 2026); 4.0.0 stable Aug 31, 2026; 3.0.0 Feb 18, 2026.
- LangChain MCP: new **`langchain.mcp.MCPAdapter`** in `langchain[mcp]>=1.4.0` (beta), which replaces `langchain-mcp-adapters`.
- Deep Agents: skills `metadata.include_tools` needs `deepagents>=0.7.22`; subagent `response_format` needs `deepagents>=0.5.3`.
- A2A: v1.0 (March 2026, per secondary sources).
- Langfuse: core MIT, all product features open-sourced under MIT on Jun 4, 2025.

---

## 1. Tools library: design, packaging, metadata, permissions, testing

### Takeaway
LangChain v1 tools should be typed `@tool` functions (or `args_schema` Pydantic models) whose docstring is the model-facing contract. Per-run identity and state come in through `runtime: ToolRuntime[Context]`, not through model-visible arguments. Errors become `ToolMessage`s via `@wrap_tool_call` middleware. A shared library should ship pure tool functions plus a registry. Allowlisting, auth and error policy then live in middleware that is assembled per agent.

### Cited Findings
- **Docstring = description; type hints are required** because they define the input schema. You can set a custom name (snake_case, since some providers reject spaces), `description=`, `args_schema=` (Pydantic or JSON schema) and `return_direct=True` — [LangChain Tools docs](https://docs.langchain.com/oss/python/langchain/tools)
- `return_direct` ends the loop only if *every* tool called in that model step has the flag — [LangChain Tools docs](https://docs.langchain.com/oss/python/langchain/tools)
- **`ToolRuntime`**: add a `runtime: ToolRuntime` param (hidden from the model schema). It exposes `runtime.state`, `runtime.context` (immutable per-run data such as user_id), `runtime.store` (long-term store), `runtime.stream_writer`, `runtime.execution_info` (thread/run IDs, attempt number), `runtime.server_info` (assistant/graph/user on LangGraph Server) and `runtime.tool_call_id`. It is generic over the context type, e.g. `ToolRuntime[UserContext]`. `config` and `runtime` are reserved argument names — [LangChain Tools docs](https://docs.langchain.com/oss/python/langchain/tools)
- `ToolRuntime` replaces the older `InjectedState`, `InjectedStore`, `get_runtime()` and `InjectedToolCallId` patterns, so migrate away from them — [LangChain Tools docs](https://docs.langchain.com/oss/python/langchain/tools)
- **Error handling recommendation**: `@wrap_tool_call` middleware catches exceptions and returns `ToolMessage(content=..., tool_call_id=request.tool_call["id"])` so the model can self-correct — [LangChain Tools docs](https://docs.langchain.com/oss/python/langchain/tools)
- **State updates from tools**: return `langgraph.types.Command(update={..., "messages":[ToolMessage(..., tool_call_id=runtime.tool_call_id)]})`. `ToolNode` raises `ValueError` if the ToolMessage is missing. Use reducers for keys that parallel tool calls touch. `graph=Command.PARENT` writes to the parent graph — [LangChain Tools docs](https://docs.langchain.com/oss/python/langchain/tools)
- MCP spec 2025-11-25 added **tool-name guidance (SEP-986)** and says input-validation errors should be returned as *tool execution errors*, not protocol errors, so the model can self-correct (SEP-1303). This is a good norm for native tools too — [MCP 2025-11-25 changelog](https://modelcontextprotocol.io/specification/2025-11-25/changelog)
- MCP provenance metadata on adapted tools lives at `request.tool.metadata["mcp"]` (annotations, server identity). This shows the `BaseTool.metadata` dict is the hook for discovery/governance tags — [LangChain MCP migration guide](https://docs.langchain.com/oss/python/migrate/langchain-mcp-adapters)

### Inferences
- **Recommended tool-authoring contract for the shared library**:
  1. Pure, typed function with a Pydantic `args_schema` using `Field(description=...)` on every field and `Literal` enums where possible.
  2. A docstring that says *when to use* and *when not to use* the tool.
  3. Identity and tenant (portfolio company, user, entitlements) come only through `ToolRuntime[PlatformContext].context`, never as LLM-filled arguments. This is key for cross-portco isolation.
  4. Return concise strings, or `Command` for state.
  5. Raise typed exceptions and let shared `@wrap_tool_call` middleware convert them.
  6. Provide `async def` implementations for I/O tools.
- **Metadata for discovery**: populate `BaseTool.tags` and `BaseTool.metadata`, for example `{"owner_team", "portco": ["A","B","shared"], "data_classification", "side_effects": "read|write|destructive", "version", "requires_scopes"}`. Mirror MCP tool annotations such as readOnly/destructive hints.
- **Permission/allowlist per agent**: a central `ToolRegistry.resolve(agent_spec.tools, ctx)` filters by tags, scopes and portco. A `@wrap_tool_call` guard re-checks at call time (defense in depth). Deep Agents subagents' `tools` field *replaces* inherited tools, which enables least-privilege subagents (see §5).
- **Packaging (not verified via sources this session; standard Python practice)**:
  - Use a uv workspace monorepo `platform-libs/` with members such as `platform-core` (context types, registry, middleware), `platform-tools-<domain>`, `platform-connectors`, `platform-prompts` and `platform-agents`.
  - Use PEP 420 namespace packages, e.g. `acme_agents.tools.finance`, so teams own sub-distributions.
  - Use Python entry points (`[project.entry-points."acme_agents.tools"]`) so the registry discovers installed tool packs via `importlib.metadata.entry_points(group=...)`.
  - Use SemVer per package. A tool schema change (renamed or required arg) is a MAJOR bump, because prompts and evals depend on it.
  - Publish to a private index (Artifactory, Nexus, AWS CodeArtifact or GitLab PyPI).
- **Testing**:
  - Unit-test the underlying function.
  - Use schema-snapshot tests on `tool.tool_call_schema.model_json_schema()` to catch breaking changes.
  - Invoke with a fake `ToolRuntime`/context.
  - Run trajectory evals with the agent using a fake chat model.
  - Run contract tests for MCP-wrapped tools against an in-memory FastMCP server, which `MCPAdapter` supports as a target (see §2).

### Gaps
- The LangChain Tools page didn't cover `ToolException`/`handle_tool_error`, `response_format="content_and_artifact"` or `parse_docstring` in the fetched content. Those APIs existed in langchain-core historically, but I did not verify their current status in v1.x.
- I found no official LangChain guidance on packaging tools libraries, entry-point plugin registries or tool versioning.

---

## 2. MCP: spec, LangChain adapters, FastMCP, registries/gateways, security

### Takeaway
MCP's latest spec is **2026-07-28**. It is a breaking, *stateless* redesign: no initialize handshake or session id, Multi Round-Trip Requests replace server-initiated elicitation/sampling/roots, routing headers serve gateways, list responses are cacheable, there is an extensions framework (Tasks, MCP Apps, Enterprise Managed Authorization), and CIMD replaces DCR. On the Python side:
- LangChain now ships `langchain.mcp.MCPAdapter` (FastMCP-based, beta) in place of `langchain-mcp-adapters`. Interceptors move to `@wrap_tool_call` middleware, and elicitation becomes LangGraph interrupts.
- FastMCP 4.x implements the new protocol. For servers, its 3.x "providers + transforms + component versioning + granular auth" model fits a shared multi-team MCP estate well.
- For self-hosted discovery, run a private registry/gateway (e.g. IBM ContextForge, Apache-2.0). The official MCP Registry doesn't host private servers.

### Cited Findings
**Spec 2025-11-25 (previous version)**
- Major changes:
  - OpenID Connect Discovery for authorization servers.
  - Icons on tools/resources/prompts (SEP-973).
  - Incremental scope consent via `WWW-Authenticate` (SEP-835).
  - Tool-name guidance (SEP-986).
  - Standards-based elicitation enums (SEP-1330).
  - **URL-mode elicitation** (SEP-1036).
  - **Tool calling in sampling** (`tools`/`toolChoice`, SEP-1577).
  - **OAuth Client ID Metadata Documents (CIMD)** as recommended registration (SEP-991).
  - **Experimental Tasks** for durable requests with polling and deferred results (SEP-1686).
  - Source: [MCP 2025-11-25 changelog](https://modelcontextprotocol.io/specification/2025-11-25/changelog)
- Minor changes:
  - 403 for invalid Origin on Streamable HTTP.
  - RFC 9728 protected resource metadata, with `.well-known` fallback.
  - JSON Schema 2020-12 as the default dialect.
  - SSE polling and resumption (SEP-1699).
  - Optional `description` on `Implementation`, to align with registry `server.json`.
  - Updated security best practices.
  - Formalized governance and an SDK tiering system (SEP-1730).
  - Source: [MCP 2025-11-25 changelog](https://modelcontextprotocol.io/specification/2025-11-25/changelog)

**Spec 2026-07-28 (latest, released Jul 28, 2026)** — [MCP blog 2026-07-28](https://blog.modelcontextprotocol.io/posts/2026-07-28/)
- **Stateless protocol**:
  - The `initialize`/`initialized` handshake and the `Mcp-Session-Id` header are retired. Each request carries protocol version, client identity and capabilities in `_meta`.
  - An optional `server/discover` RPC lets clients fetch capabilities up front.
  - Requests can hit any instance behind a round-robin load balancer.
  - Servers that need state issue explicit handles that the model passes back as arguments.
- **Multi Round-Trip Requests (MRTR)** replace server-initiated `elicitation/create`, `sampling/createMessage` and `roots/list`. The server returns `resultType: "input_required"` and the client retries with `inputResponses`.
- **Header routing**: Streamable HTTP requests must carry `Mcp-Method` and `Mcp-Name` headers, so gateways can route and meter without parsing bodies.
- **Cacheable lists**: `tools/list`, `prompts/list`, `resources/list` and `resources/read` return `ttlMs` and `cacheScope`, in deterministic order.
- **Auth**:
  - Authorization servers return the RFC 9207 `iss` parameter, which clients validate.
  - `application_type` in DCR.
  - Client credentials are bound to the issuer that minted them.
  - **DCR is deprecated in favor of CIMD**.
  - MCP servers are formally OAuth 2.1 resource servers ([Composio summary](https://composio.dev/blog/mcp-2026-07-28-update-statelessness-apps-auth)).
- **Extensions framework**:
  - Tasks becomes the `io.modelcontextprotocol/tasks` extension, with `tasks/get` polling and a new `tasks/update`.
  - MCP Apps and Enterprise Managed Authorization (EMA) are named extensions.
  - Notifications move to a single `subscriptions/listen` stream.
- **Deprecations**: Roots, Sampling and Logging are deprecated (they keep working for ≥12 months). Legacy HTTP+SSE is deprecated with a one-year offramp. A formal 12-month minimum deprecation policy now applies.
- **SDKs**: TypeScript, Python, Go and C# (Tier 1) support 2026-07-28 at release. Rust is in beta.
- Note: some secondary coverage from before Jul 28 still called it an RC. The official blog announces the final release — [dev.to](https://dev.to/rabinarayanpatra/why-mcp-2026-07-28-spec-drops-sessions-and-goes-stateless-1gd), [flaviocopes](https://flaviocopes.com/mcp-2026-07-28-stateless/)

**LangChain integration: `langchain.mcp` (new) vs `langchain-mcp-adapters` (legacy)** — [Migration guide](https://docs.langchain.com/oss/python/migrate/langchain-mcp-adapters), [LangChain MCP docs](https://docs.langchain.com/oss/python/langchain/mcp)
- Install `langchain[mcp]>=1.4.0` (built on FastMCP). Uninstall `langchain-mcp-adapters` first. Importing raises `LangChainBetaWarning`, so the API may change. No sunset date is given for the old package.
- Mapping:
  - `MultiServerMCPClient` → `MCPAdapter`, an async context manager.
  - `get_tools()` → `await adapter.list_tools()`.
  - `load_mcp_tools` → `list_tools()`.
  - `convert_mcp_tool_to_langchain_tool` → `as_langchain_tool` (now a coroutine).
  - `MCPToolArtifact` is kept, as `langchain.mcp.MCPToolArtifact`.
- **Targets**: an http(s) URL (Streamable HTTP), a `Path` (stdio), a `StreamableTransport`, an in-process `FastMCP` instance (in-memory, useful for tests), an `MCPConfig` dict `{"mcpServers": {...}}`, a prebuilt `fastmcp.Client`, or a `ClientGroup`. String targets must be http(s) URLs, because otherwise FastMCP could execute a local .py/.js file. This is a security guard.
- **Tool name prefixing** is automatic for multi-server configs: `{server}_{tool}`.
- `handle_tool_errors` is removed. `isError=True` becomes `ToolMessage(status="error")`, and transport failures raise.
- **Interceptors**: `tool_interceptors` / `ToolCallInterceptor` are gone. Use `@wrap_tool_call` middleware, which applies to all tools. MCP provenance is in `request.tool.metadata["mcp"]`.
- **Callbacks**: `on_progress` and `on_logging_message` become `fastmcp.Client(progress_handler=..., log_handler=...)`. **Elicitation** is on by default via LangGraph interrupts; resume with `Command(resume={"responses": {key: answer}})`.
- **Auth**: set it on `fastmcp.Client(auth=<bearer token> | "oauth" | httpx.Auth)`. Per-server and per-user auth are supported, documented on the separate Authentication page.
- **Not yet supported**: prompts/resources wrappers (call `client.get_prompt`/`read_resource` directly), sampling/roots (raise `NotImplementedError`) and `to_fastmcp`. SSE works via `SSETransport` but is deprecated. There is no WebSocket transport.
- Each tool opens its own session per call. `session(...)` isn't exposed.

**FastMCP (server framework)** — [FastMCP updates](https://gofastmcp.com/updates.md), [search summary](https://www.jlowin.dev/blog/fastmcp-3-whats-new)
- **3.0.0 (Feb 18, 2026)**:
  - **Providers**: FileSystem, OpenAPI, Proxy and Skills. Components come from decorators, filesystems, OpenAPI specs or remote servers. One provider can be shared across servers, and a server can have many providers.
  - **Transforms**: rename, namespace, filter, version, secure. You can hide components by tag.
  - **Component versioning** with highest-version selection.
  - Granular authorization, CIMD, Azure OBO, background tasks, and per-session enable/disable.
  - ResourcesAsTools and PromptsAsTools.
- **3.1.0 (Mar 3, 2026)**: CodeMode (search, inspect, then run Python in a sandbox), search transforms and MultiAuth.
- **3.2.0 (Mar 30, 2026)**: Apps (FastMCPApp), OAuth scope enforcement and JWT algorithm restrictions.
- 3.2.4: tasks scoped to the authorization context, plus a Keycloak provider.
- 3.3.0: OAuth proxy hardening.
- 3.4.3: SSRF and Host/Origin validation.
- **4.0.0 (Aug 31, 2026)**: the new sessionless protocol, a `fastmcp-tasks` package, `add_extension()`, dependency injection, `ClientGroup`, identity assertion, `require_roles` and scope step-up. **Server-initiated sampling and roots are removed (breaking).**
- **Latest 4.1.4 (Oct 26, 2026)**:
  - 4.1.0 added Python 3.15 and tighter input validation.
  - 4.1.1 added skill-folder symlink discovery.
  - 4.1.2 applies component authorization *after* transforms and binds OAuth client credentials to the issuer.
  - 4.1.4 OAuth wrappers accept identity assertions, and there is a Redis credential provider for tasks.

**Registries and gateways (self-hosted)**
- The official MCP Registry preview launched Sep 8, 2025 — [MCP blog](https://blog.modelcontextprotocol.io/posts/2025-09-08-mcp-registry-preview/).
  - It does not accept private servers. Its codebase is "not designed for self-hosting", and maintainers suggest running your own private registry — [Atlan](https://atlan.com/know/ai-agent/public-vs-private-mcp-server-registry/) (secondary).
  - The Registry WG charter lists "sub-registry" spec work at the ideation stage, targeted for Q3 2026 — [WG charter](https://modelcontextprotocol.net/community/registry/charter).
- Common enterprise pattern: use the public registry as an upstream feed, filter it against security policy, and republish approved subsets to a private gateway — [Composio](https://composio.dev/blog/mcp-marketplaces-directories-compared-2026) (vendor).
- Copilot policies can point at an internal registry URL, self-hosted to the v0.1 registry spec — [NeuralTrust](https://neuraltrust.ai/blog/mcp-registry-allowlist-enterprise) (vendor).
- **IBM ContextForge** (`mcp-contextforge-gateway`, Apache-2.0) — [GitHub](https://github.com/IBM/mcp-context-forge):
  - Registries for tools, prompts (Jinja2, versioned) and resources.
  - **Virtual servers**, which bundle selected tools behind one endpoint.
  - Multi-cluster federation (Redis).
  - REST/gRPC-to-MCP adaptation.
  - A2A agent integration.
  - JWT/SSO (Google, GitHub, Entra ID), user-scoped OAuth, RBAC and 40+ plugins/guardrails.
  - OpenTelemetry.
  - Deploys via PyPI/uvx, Docker/Podman, Compose (Postgres + Redis + Nginx), Helm, or airgapped.
  - The README references 1.0.0-RC-3 and no release date was found.
- **Docker MCP Gateway** (MIT): each MCP server runs in an isolated container, with secrets held outside env vars. Strongest local-dev story. **Kong**: AI MCP Proxy plugin in Gateway ≥3.12, enterprise tier. ContextForge is broadest for federation — [Maxim comparison](https://www.getmaxim.ai/articles/mcp-gateway-comparison-2026-bifrost-docker-microsoft-kong-cloudflare.md) (vendor-authored; treat rankings cautiously).
- **agentregistry** (open source; v0.4.0 on pkg.go.dev): one catalog to find, manage and run MCP servers, agents *and skills*. Platform teams publish approved artifacts, and developers discover them via a web UI or CLI — [pkg.go.dev](https://pkg.go.dev/github.com/agentregistry-dev/agentregistry@v0.4.0)
- Registry entry design: a server record with auth metadata, access policy, transport and a cached tool schema. Discovery is per-caller and RBAC-filtered — [TrueFoundry](https://truefoundry.com/blog/centralized-mcp-registry-architecture) (vendor, May 2026).

**Security**
- Spec-level controls: 403 on bad Origin, incremental scope consent, issuer binding, RFC 9207 `iss` validation, CIMD over DCR — [2025-11-25 changelog](https://modelcontextprotocol.io/specification/2025-11-25/changelog); [2026-07-28 blog](https://blog.modelcontextprotocol.io/posts/2026-07-28/)
- FastMCP hardening releases: SSRF checks, Host/Origin validation, redirect-URI validation (3.4.3); proxies stop forwarding cookies (4.0.0b4); component auth applied after transforms (4.1.2) — [FastMCP updates](https://gofastmcp.com/updates.md)
- LangChain rejects non-URL string targets to avoid accidental subprocess execution — [LangChain MCP docs](https://docs.langchain.com/oss/python/langchain/mcp)

### Inferences
- **Recommended MCP topology for two portcos**:
  - Teams build servers with FastMCP 4.x (stateless, horizontally scalable) and register them in a self-hosted gateway/registry (ContextForge or agentregistry).
  - The gateway exposes **virtual servers per portco/agent persona**, which handles allowlisting at the network edge, and uses `Mcp-Method`/`Mcp-Name` headers for metering.
  - Agents connect with `MCPAdapter(MCPConfig)` pointing only at gateway URLs, with per-user OAuth (on-behalf-of) via `fastmcp.Client(auth=...)`.
- **Tool poisoning mitigation**:
  - Pin server versions in the registry.
  - Snapshot and diff tool descriptions/schemas on every registry update, and require review when descriptions change.
  - Use FastMCP transforms to rename/namespace and hide tools.
  - Never allow ad-hoc stdio servers in production agents.
  - Mark destructive tools for HITL via Deep Agents `interrupt_on`.
- Because `langchain.mcp` is beta and lacks prompts/resources, a shared platform package should wrap MCP loading behind its own `load_mcp_tools(spec, ctx)` function so the underlying API can change without touching teams' code.

### Gaps
- I didn't fetch the official "MCP Apps" or "Enterprise Managed Authorization" extension specs, so I have no field-level detail.
- I found no primary-source, explicit treatment of "tool poisoning" in the spec's security best practices page this session (not fetched).
- I found no current ContextForge GA version or date, and no Docker MCP Gateway version.
- I didn't fetch the LangChain MCP Authentication page (per-user auth code).

---

## 3. Agent Skills: standard, Deep Agents loading, internal marketplace

### Takeaway
Agent Skills (agentskills.io) is a simple folder standard: `SKILL.md` with YAML frontmatter (`name`, `description` required), plus optional `scripts/`, `references/` and `assets/`, loaded via three-level progressive disclosure. Deep Agents' `SkillsMiddleware` implements it with layered sources ("last one wins") on State, Store or Filesystem backends. That makes a git-based, reviewed internal skills repo layered as `org-base → portco → team → project` a natural design.

### Cited Findings
- **Directory**: `skill-name/SKILL.md` (required), plus optional `scripts/`, `references/` and `assets/` — [Agent Skills spec](https://agentskills.io/specification)
- **Frontmatter**:
  - `name` (required): 1–64 chars, lowercase a-z/0-9/hyphens, no leading/trailing/double hyphens, **must match the directory name**.
  - `description` (required): 1–1024 chars, says what it does *and when to use it*, with keywords.
  - Optional fields:
    - `license`.
    - `compatibility` (≤500 chars, for environment requirements).
    - `metadata` (string→string map; the spec example uses `author`, `version: "1.0"`).
    - `allowed-tools` (space-separated, **experimental**, e.g. `Bash(git:*) Read`).
  - Source: [Agent Skills spec](https://agentskills.io/specification)
- **Progressive disclosure**: metadata (~100 tokens) loads at startup, the SKILL.md body (<5000 tokens recommended, <500 lines) loads on activation, and resources load on demand. Keep file references one level deep and use relative paths — [Agent Skills spec](https://agentskills.io/specification)
- **Validation**: `skills-ref validate ./my-skill` (the reference library in github.com/agentskills/agentskills) — [Agent Skills spec](https://agentskills.io/specification)
- **Deep Agents**: `create_deep_agent(skills=["/skills/base/", "/skills/project/"], backend=...)`. Each path is a *parent directory containing skill dirs*. Passing a skill dir itself fails silently — [Deep Agents Skills docs](https://docs.langchain.com/oss/python/deepagents/skills)
- Backends: `StateBackend` (default; pass `files=` via `create_file_data()`), `StoreBackend` (durable, cross-thread; `upload_files()`), `FilesystemBackend(root_dir, virtual_mode=True)` — [Deep Agents Skills docs](https://docs.langchain.com/oss/python/deepagents/skills)
- **Override semantics**: later sources win on name clashes ("last one wins"). A stale or empty later skill with the same name can shadow the real one — [Deep Agents Skills docs](https://docs.langchain.com/oss/python/deepagents/skills)
- **Subagents**: the general-purpose subagent inherits the main agent's skills. Custom subagents inherit none and need their own `skills` list. Skill state is isolated — [Deep Agents Skills docs](https://docs.langchain.com/oss/python/deepagents/skills)
- Deep Agents extensions:
  - `metadata.include_tools` attaches tools once a skill is read (`deepagents>=0.7.22`).
  - SKILL.md >10 MB is skipped.
  - `pinned_skills` injects a skill without waiting for the agent to choose it.
  - Skills load once per thread. Reset `skills_metadata` to `None` to reload.
  - Source: [Deep Agents Skills docs](https://docs.langchain.com/oss/python/deepagents/skills)
- FastMCP 3.0 includes a **Skills provider**, and 4.1.1 added skill-folder symlink discovery. Skills can therefore also be *served* over MCP from a central server — [FastMCP updates](https://gofastmcp.com/updates.md)
- agentregistry catalogs skills alongside MCP servers and agents — [pkg.go.dev agentregistry](https://pkg.go.dev/github.com/agentregistry-dev/agentregistry@v0.4.0)

### Inferences
- **Internal skills repo design**:
  - Use a git monorepo `skills/` with `org/`, `portco-a/`, `portco-b/` and `teams/<team>/` roots. Each skill is a directory with `metadata: {owner, version, portco, data_classification, reviewed_by}`.
  - CI runs `skills-ref validate`, a name/dir match check, a token-size budget, a secret scan, and a static review of `scripts/`.
  - CODEOWNERS-based review, and semver tags per skill (e.g. `skills/finance-close@1.3.0`) or per release bundle.
  - A sync job publishes approved versions into a LangGraph `StoreBackend` namespace (or a read-only FilesystemBackend volume/image).
  - Agents load `skills=["/skills/org/", "/skills/portco-a/", "/skills/team-x/"]` so the more specific layer overrides.
- `metadata.include_tools` lets a skill declare which registry tools it needs, linking the skills library to the tools registry (lazy tool exposure keeps context small).
- Keep `allowed-tools` advisory only (it's experimental). Enforce permissions in the tool registry and middleware instead.

### Gaps
- I found no official "marketplace" or registry protocol for Agent Skills (no versioned distribution standard in the spec beyond `metadata.version`).
- I didn't fetch Anthropic's own skills/plugin-marketplace docs this session.

---

## 4. Prompt library: LangSmith Hub vs self-hosted (Langfuse, git), composition

### Takeaway
For self-hosted prompt management with versions and labels, Langfuse (MIT core) gives you versioned prompts, `production` labels, client-side caching, LangChain conversion and text-prompt composition via reference tags. A git-based YAML/Jinja registry is the simplest fully-owned alternative and fits CI review well. Compose system prompts from shared fragments either way.

### Cited Findings
- Langfuse:
  - Creating a prompt with an existing name adds a new version.
  - Type (text or chat) is fixed at creation.
  - Labels such as `production` choose the served version. `get_prompt(name)` defaults to production, and the API accepts `?label=` or `?version=`.
  - Source: [Langfuse prompt mgmt](https://langfuse.com/docs/prompt-management/get-started)
- SDKs cache prompts client-side, so there is no latency after the first fetch and the cached copy keeps working if Langfuse is down — [Langfuse prompt mgmt](https://langfuse.com/docs/prompt-management/get-started)
- Variables use `{{var}}` and compile with `prompt.compile(...)`. `get_langchain_prompt()` converts to LangChain `{var}` syntax for `ChatPromptTemplate.from_template`/`from_messages` and allows partial pre-fill — [Langfuse prompt mgmt](https://langfuse.com/docs/prompt-management/get-started)
- **Composability**: `@@@langfusePrompt:name=X|version=1@@@` (pinned) or `|label=production@@@` (dynamic, so dependents auto-update). **Text prompts only** — [Langfuse composability](https://langfuse.com/docs/prompt-management/features/composability)
- Licensing:
  - Langfuse core is MIT and can be self-hosted on every tier with no usage fee. All product features were open-sourced under MIT on Jun 4, 2025.
  - An optional Enterprise license adds project-level RBAC, audit logs and retention — [Langfuse clarifications](https://langfuse.com/resources/engineering/clarifications.md)
  - Protected prompt labels (stopping non-admins promoting to production) are reportedly Enterprise-only when self-hosted — [Railway guide](https://railway.com/deploy/langfuse) (secondary)
- Telemetry conflict: one source says self-hosted Langfuse sends no telemetry, while a README mirror says it sends basic usage stats to PostHog by default. Verify with the official docs — [Railway](https://railway.com/deploy/langfuse); [GitHub mirror](https://github.com/umeshshetty/langfuse)
- ContextForge also offers a prompts registry (Jinja2, versioned) exposed over MCP prompts — [ContextForge GitHub](https://github.com/IBM/mcp-context-forge)

### Inferences
- The LangSmith Prompt Hub is a LangSmith (SaaS or self-hosted LangSmith Enterprise) feature. It fits "self-hosted only" only if you license self-hosted LangSmith. I didn't verify this this session.
- **Git prompt registry pattern**:
  - `prompts/<domain>/<name>/v<semver>.yaml` holding `{id, version, description, model_hints, input_variables, template_format: jinja2|f-string, messages: [...], fragments: [...], owner, eval_suite}`.
  - A loader builds `ChatPromptTemplate`/`SystemMessage` objects.
  - Labels (`prod`, `staging`) go in a `labels.yaml` mapping changed only by PR.
  - Evals run in CI on prompt changes.
  - Optionally sync git → Langfuse, so git stays the source of truth and Langfuse serves runtime and labels.
- **Fragment composition**: system prompt = `org/safety.md` + `portco/<x>/compliance.md` + `role/<agent>.md` + `skills/tools usage notes`, assembled by Jinja `{% include %}` with a resolved-prompt hash logged to traces for reproducibility.

### Gaps
- I didn't fetch LangSmith Prompt Hub docs or langchain-core `PromptTemplate` docs (template formats such as mustache/jinja2) this session.
- Langfuse cache TTL defaults weren't on the fetched page.

---

## 5. Subagent / agent definition library: declarative specs and factories

### Takeaway
Deep Agents subagents are plain dicts (`SubAgent`) or `CompiledSubAgent`, with no native YAML loader. That makes them easy to serialize: store YAML specs that reference tool, skill and prompt IDs, and resolve them in a factory. Oracle's Open Agent Spec (with a LangGraph adapter) and A2A v1.0 Agent Cards are the cross-framework standards worth aligning metadata to.

### Cited Findings
- **`SubAgent` fields**:
  - `name` (required).
  - `description` (required; drives delegation).
  - `system_prompt` (required in isolated mode).
  - `mode` (`"isolated"` default or `"fork"`, which inherits the parent conversation).
  - `tools` (inherits by default; setting it **replaces** them).
  - `model` (`provider:model` string or object).
  - `middleware`.
  - `interrupt_on` (HITL per tool; needs a checkpointer).
  - `skills` (not inherited).
  - `response_format` (`deepagents>=0.5.3`).
  - `permissions` (filesystem rules; replace the parent's).
  - Source: [Deep Agents Subagents](https://docs.langchain.com/oss/python/deepagents/subagents)
- **`CompiledSubAgent`**: `name`, `description`, `runnable` (a compiled LangGraph graph with a `messages` key) and `mode` — [Deep Agents Subagents](https://docs.langchain.com/oss/python/deepagents/subagents)
- The general-purpose subagent is auto-added unless you define one named `general-purpose`. Customize it via `GeneralPurposeSubagentProfile(...)` and disable it with `enabled=False`. The page doesn't mention YAML or any declarative format — [Deep Agents Subagents](https://docs.langchain.com/oss/python/deepagents/subagents)
- **Oracle Open Agent Spec**: `pip install "pyagentspec[langgraph]"`. `AgentSpecLoader` loads JSON/YAML specs into runnable LangGraph agents and maps declared tools to Python functions through a tool registry. `AgentSpecExporter().to_json(graph)` exports — [Agent Spec LangGraph adapter](https://oracle.github.io/agent-spec/development/adapters/langgraph.html); a LangChain provider page exists — [LangChain docs](https://docs.langchain.com/oss/python/integrations/providers/open_agent_spec)
- **A2A Agent Card v1.0** (reportedly March 2026, Linux Foundation):
  - Top-level fields: name, description, version, provider, `supportedInterfaces[]` (which replaced url/preferredTransport), capabilities, default input/output modes, `skills[]` (each with id, name, description and **required non-empty tags**), securitySchemes, security and signatures.
  - Sources: [AAIF blog](https://aaif.io/blog/a2a-v1-0-a-builder-s-guide-part-1-discovery-tasks-and-clients); [aigrowthagent](https://aigrowthagent.co/articles/a2a-agent-card-examples/) (secondary; verify against a2a-protocol.org). A ServiceNow doc still cites 0.3.0 — [ServiceNow](https://www.servicenow.com/docs/r/order-management/cpq-agentcard-specification.html)
- ContextForge can register A2A agents alongside MCP tools — [ContextForge GitHub](https://github.com/IBM/mcp-context-forge)

### Inferences
- **Spec format** (an internal `agents/<name>/agent.yaml`):
  ```yaml
  apiVersion: acme.ai/v1
  kind: SubAgent
  metadata: {name: credit-memo-analyst, version: 2.1.0, owner: portco-a/risk, portco: [a], tags: [finance]}
  spec:
    description: "Use for drafting credit memos from deal data..."
    mode: isolated
    model: anthropic:claude-sonnet-4-6
    prompt: {ref: prompts/risk/credit-memo@^2, fragments: [org/safety, portco-a/compliance]}
    tools: [connectors.postgres.query_readonly@1, finance.dcf_calc@^1, mcp://gateway/portco-a-data/*]
    skills: [/skills/org/, /skills/portco-a/risk/]
    interrupt_on: {send_email: true}
    response_format: {ref: schemas/credit_memo.json}
  ```
  The factory validates the spec with Pydantic, resolves refs through the tool/prompt/skill registries (enforcing the portco allowlist from `ToolRuntime` context), builds a `SubAgent` dict, and passes it to `create_deep_agent(subagents=[...])`. It can also emit an A2A Agent Card from the same metadata for cross-portco discovery.
- Treat Open Agent Spec as an import/export interop format rather than the internal source of truth, since its adapter may lag Deep Agents features (fork mode, skills, permissions).

### Gaps
- I didn't read the Deep Agents async subagents page.
- I didn't verify the official A2A v1.0 spec page directly.
- No Agent Spec version or date was confirmed.

---

## 6. Reusable data connectors: Postgres, vector DBs, embeddings, pooling, secrets

### Takeaway
Build a `connectors` package around a small set of config-driven factories:
- `PGEngine` (a shared pool) for `PGVectorStore`.
- A psycopg pool for LangGraph checkpointer/store.
- `init_embeddings` for provider-agnostic embeddings.
- Thin adapters for Qdrant, Weaviate, Pinecone and Elastic behind the LangChain `VectorStore` interface.
Secrets should come from a secret manager at factory time, never from tool args.

### Cited Findings
- **`PGVectorStore`** (langchain-postgres, `v2` API path):
  - `PGEngine.from_connection_string(url="postgresql+asyncpg://...")` or `PGEngine.from_engine(create_async_engine(...))` configures a **shared connection pool**. It supports asyncpg and psycopg3 (`postgresql+psycopg://`).
  - Create tables with `await pg_engine.ainit_vectorstore_table(table_name, vector_size, schema_name=...)` and the store with `await PGVectorStore.create(engine, table_name, embedding_service)`. All async methods have sync counterparts.
  - Source: [PGVectorStore docs](https://docs.langchain.com/oss/python/integrations/vectorstores/pgvectorstore)
- More PGVectorStore features:
  - Custom metadata columns via `Column("len","INTEGER")`.
  - Filters `$eq/$in/$between/$like/$and/$or`.
  - Map existing tables via `id_column`, `content_column`, `embedding_column`, `metadata_columns` and `metadata_json_column`.
  - Hybrid search (vector + Postgres full-text) via `HybridSearchConfig`.
  - Indexes `HNSWIndex`, `IVFFlatIndex` with `aapply_vector_index`/`areindex`.
  - Source: [PGVectorStore docs](https://docs.langchain.com/oss/python/integrations/vectorstores/pgvectorstore)
- Deep Agents `StoreBackend` stores files (e.g. skills) in a LangGraph store for durable cross-thread use. A Postgres-backed LangGraph store can therefore hold the shared skills library — [Deep Agents Skills docs](https://docs.langchain.com/oss/python/deepagents/skills)

### Inferences
- Package layout: `acme_connectors/{config.py (Pydantic settings per connector), secrets.py (Vault/AWS SM/Azure KV provider interface), postgres.py, vectorstores/{pgvector,qdrant,weaviate,pinecone,elastic}.py, embeddings.py, sql_tools.py, registry.py}`.
- `get_vectorstore("kb-portco-a")` reads YAML (`backend: pgvector, table: ..., embeddings: openai:text-embedding-3-large, secret_ref: vault://...`) and returns a cached, pooled instance. One pool per DSN per process.
- Expose connectors to agents only through curated tools, e.g. read-only SQL tools bound to a read-only DB role with schema allowlists. Don't hand the raw `SQLDatabaseToolkit` to cross-portco agents.
- Isolate tenants with separate schemas or databases per portco. Pass the tenant via `ToolRuntime.context`.

### Gaps
- The fetch of the LangGraph Postgres checkpointer/store page (`langgraph-checkpoint-postgres`, `PostgresSaver`/`AsyncPostgresSaver`, `PostgresStore` with `index={"embed":..., "dims":...}`, psycopg_pool kwargs `autocommit=True`, `prepare_threshold=0`, `row_factory=dict_row`) **timed out**. These are well-known from prior knowledge but unverified for Nov 2026.
- The deprecation status of the legacy `PGVector` class relative to `PGVectorStore` wasn't confirmed on the fetched page.
- I didn't research `init_embeddings`, `SQLDatabase` toolkit, Qdrant/Weaviate/Pinecone/Elastic integration package versions, or secrets-manager integrations this session.

---

## 7. Examples of companies/projects building internal agent component registries

### Takeaway
LangChain's "company harness" post (Oct 24, 2026) describes shared *runtime* primitives, not a component registry. Public engineering write-ups from Uber, LinkedIn, Shopify and similar companies on shared tool/skill registries were not found this session. Open-source and vendor registries (ContextForge, agentregistry, TrueFoundry, MintMCP, Archestra, Stacklok) are the concrete reference designs.

### Cited Findings
- LangChain, "The five components of building a 'company harness'" (Harrison Chase and Caspar Broekhuizen, **Oct 24, 2026**) — [LangChain blog](https://www.langchain.com/blog/components-building-company-harness):
  - The five shared primitives:
    1. Channel placement (Slack apps, "breakout" threads).
    2. Identity (on-behalf-of vs fixed credentials or service accounts).
    3. Memory (global vs user tiers).
    4. Code execution (LangSmith Sandboxes with a secret proxy; per-agent base images).
    5. Scheduled/event-driven runs.
  - The three internal agents are GTM Agent, OpenSWE and Content Studio, all on Managed Deep Agents over the open-source Deep Agents harness.
  - The post does **not** cover sharing tools, skills or prompts, registries, packaging or versioning.
- **agentregistry**: an open-source catalog for MCP servers, agents and skills, with a publish/discover workflow (web UI and CLI) — [pkg.go.dev](https://pkg.go.dev/github.com/agentregistry-dev/agentregistry@v0.4.0)
- Stacklok recommends fully self-hosted registries inside the VPC or on-prem for regulated industries — [Stacklok](https://stacklok.com/resources/building-a-local-mcp-registry/)
- Archestra private registry: admins curate an approved catalog, and each user or team connects with their own credentials — [Archestra docs](https://www.archestra.ai/docs/platform-private-registry)
- InfoWorld guide to building an enterprise-grade MCP registry — [InfoWorld](https://www.infoworld.com/article/4145014/how-to-build-an-enterprise-grade-mcp-registry.html) (not read in full)

### Inferences
- The LangChain harness post suggests that identity (OBO vs service account) and secret proxying are platform concerns that shared tools must respect. Shared tools should therefore declare their identity mode in metadata (`identity: obo|service`).
- Since it is self-hosted only, replicate the harness primitives with open-source Deep Agents plus your own LangGraph deployment rather than Managed Deep Agents.

### Gaps
- I found no first-party engineering blogs from Uber, LinkedIn, Shopify, Block or others on internal agent tool/skill registries. One search returned only vendor content, so a targeted follow-up per company is needed.
- I found no evidence of PE-portfolio-specific (multi-company) agent platform case studies.
