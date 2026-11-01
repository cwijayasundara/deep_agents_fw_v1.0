# LangGraph Base Framework and Cross-Cutting Platform Concerns (as of 2026-11-01)

## Q1. Latest versions of langgraph, langchain, langchain-core and notable v1.x changes

### Takeaway
As of 1 Nov 2026 the current releases are langgraph 1.2.19 (30 Oct 2026), langchain 1.4.7 and langchain-core 1.7.3, all on Python >=3.10. Since 1.0 (20 Oct 2025) the line has added v2/v3 streaming, `GraphOutput`, `DeltaChannel`, node timeouts, error handlers and graceful drain in LangGraph 1.2, plus first-party MCP in LangChain 1.4. langchain-core 1.7 also changed how tool-call streaming works, which breaks some clients.

### Cited Findings
- langgraph latest = **1.2.19**, `requires_python >=3.10` — [PyPI langgraph JSON](https://pypi.org/pypi/langgraph/json)
- langchain latest = **1.4.7**, `requires_python >=3.10,<4.0` — [PyPI langchain JSON](https://pypi.org/pypi/langchain/json)
- langchain-core latest = **1.7.3** — [PyPI langchain-core JSON](https://pypi.org/pypi/langchain-core/json)
- Sibling packages released in late October: langgraph-sdk 0.4.11 (30 Oct), langgraph-checkpoint-sqlite 3.1.3 (30 Oct), langgraph-checkpoint 4.3.1 (26 Oct), langgraph-cli 0.4.40 (26 Oct). The 1.2.17 to 1.2.19 releases were Oct 24 to 30 — [GitHub langgraph releases](https://github.com/langchain-ai/langgraph/releases)
- langgraph 1.2.19 is mostly streaming fixes. Messages and tool events now carry their graph's namespace, `RemoteGraph.stream` respects `subgraphs=False`, and `ToolNode` tool names appear in node metadata — [GitHub releases](https://github.com/langchain-ai/langgraph/releases)
- langgraph 1.2.18 is a **behavior change**: `DeltaChannel` now takes a full snapshot every 100 updates instead of every 1000. Pass `snapshot_frequency=1000` to keep the old behavior. It also fixes error-handler recovery and streaming of the last checkpoint at an interrupt or the recursion limit — [GitHub releases](https://github.com/langchain-ai/langgraph/releases)
- langgraph-checkpoint 4.3.1 rejects NUL bytes in namespace labels, which is a validation break — [GitHub releases](https://github.com/langchain-ai/langgraph/releases)
- langgraph-sdk 0.4.9 adds a thread `Priority`. 0.4.10 accepts `durability`, `stream_resumable` and `context` in the runs overloads. 0.4.11 reconnects with backoff and keeps the Last-Event-ID cursor — [GitHub releases](https://github.com/langchain-ai/langgraph/releases)
- **langchain and langgraph 1.0.0 shipped on 20 Oct 2025** — [Changelog](https://docs.langchain.com/oss/python/releases/changelog.md)
- LangGraph v1 is a "stability-focused release". The core graph APIs did not change. The **`create_react_agent` prebuilt is deprecated in favor of `langchain.agents.create_agent`**, which adds middleware — [LangGraph v1 release notes](https://docs.langchain.com/oss/python/releases/langgraph-v1)
- langchain 1.1.0 (25 Nov 2025) added these — [Changelog](https://docs.langchain.com/oss/python/releases/changelog.md):
  - a model `.profile` attribute with capability data from models.dev
  - profile-aware summarization middleware
  - `SystemMessage` accepted as `system_prompt`, which enables cache control
  - model retry middleware
  - OpenAI moderation middleware
- langchain 1.2.0 (15 Dec 2025) added a tool `extras` attribute for provider-specific features such as Anthropic programmatic tool calling and tool search, and `ProviderStrategy` for strict structured output — [Changelog](https://docs.langchain.com/oss/python/releases/changelog.md)
- langgraph 1.1.0 (10 Mar 2026) added two opt-in v2 formats, and also fixed time travel with interrupts and subgraphs. Dict-style access on `GraphOutput` is deprecated — [Changelog](https://docs.langchain.com/oss/python/releases/changelog.md):
  - `stream(..., version="v2")` returns unified `StreamPart` chunks (`type`, `ns`, `data`)
  - `invoke(..., version="v2")` returns `GraphOutput` with `.value` and `.interrupts`, and coerces output to the declared Pydantic or dataclass types
- langchain 1.3.0 (12 May 2026) added `version="v3"` for `stream_events` and `astream_events` — [Changelog](https://docs.langchain.com/oss/python/releases/changelog.md)
- langgraph 1.2.0 (12 May 2026) added the following. Timeouts and error handlers are Python only — [Changelog](https://docs.langchain.com/oss/python/releases/changelog.md):
  - `DeltaChannel` (beta)
  - per-node `timeout=` with `TimeoutPolicy`
  - node `error_handler=` for saga-style compensation
  - `RunControl.request_drain()` and `GraphDrained` for graceful shutdown
  - event streaming v3 (beta), with projections such as `run.values`, `run.messages` and `run.lifecycle`
- langchain 1.4.0 (1 Sep 2026) moved MCP support into **`langchain.mcp`** (beta, built on FastMCP, installed with the `mcp` extra) — [Changelog](https://docs.langchain.com/oss/python/releases/changelog.md):
  - `MCPAdapter` **supersedes `langchain-mcp-adapters` / `MultiServerMCPClient`**
  - adds elicitation and OAuth 2.1 / bearer authentication
- langchain 1.4.6 (14 Oct 2026) added `HumanInTheLoopMiddleware(interrupt_mode="per_call")`. Each interrupt carries a `response_schema`, and answers are validated. Per-call mode is planned to become the default in the next major release — [Changelog](https://docs.langchain.com/oss/python/releases/changelog.md)
- **Breaking change in langchain-core 1.7.0 (22 Oct 2026):** tool-call arguments now stream as `tool-call-delta` events. From 1.6.13, iterating `message.tool_calls` yields only new fragments, so use `message.tool_calls.get()` for parsed calls. Upgrade the stream clients first (core 1.6.13+, JS packages 1.2.6+), then the server (core 1.7.0+, langchain 1.4.7+). Pin `langchain-core<1.7.0` to defer the change — [Changelog](https://docs.langchain.com/oss/python/releases/changelog.md)

### Inferences
- A shared framework should pin these minimums: `langgraph>=1.2.19,<2`, `langchain>=1.4.7,<2`, `langchain-core>=1.7,<2`. Upgrade any streaming UIs in step with core 1.7, because the tool-call delta change breaks older clients.
- Make `version="v2"` the standard for `stream` and `invoke` in the scaffold. It gives one typed chunk shape (`StreamPart`) and the `GraphOutput.interrupts` field for HITL. Treat v3 event streaming as beta.
- If teams use `DeltaChannel`, re-check snapshot cost after 1.2.18.

### Gaps
- I could not see exact PyPI upload dates for langchain 1.4.7 and langchain-core 1.7.3, because the JSON pages were truncated. The changelog only implies that 1.4.7 shipped around 22 Oct 2026.
- The LangGraph v1 release notes page does not list removed APIs or the `config_schema` to `context_schema` change. That change is my recollection and is not verified here.

## Q2. Graph API vs Functional API, StateGraph patterns, reducers, Command, Send, subgraphs, interrupt(), durability, caching, retries, context_schema, recursion limits

### Takeaway
The Graph API (`StateGraph`) is the right base for a platform. It gives explicit state schemas, reducers, `Command` / `Send` routing, and per-node policies (`RetryPolicy`, `CachePolicy`, `timeout`, `error_handler`) that can be set once with `set_node_defaults`. The Functional API (`@entrypoint` / `@task`) accepts the same timeout and retry options, which makes it a lighter option for imperative workflows.

### Cited Findings
- **Execution model.** `StateGraph` must be `.compile()`d. Execution runs in super-steps, and nodes that run in parallel share a super-step — [Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api.md)
- **State schemas** can be `TypedDict`, a dataclass (for defaults), or Pydantic (validated but slower). You can also pass `input_schema` / `output_schema`, and nodes can write private channels — [Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api.md)
- **Reducers** have the signature `reducer(left, right)`. The default replaces the value — [Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api.md):
  - `Annotated[list, operator.add]` appends
  - `add_messages` upserts by message ID
  - `MessagesState` is the prebuilt message state
  - `Overwrite([])` bypasses a reducer to clear a field
- **`Command`** takes `update`, `goto`, `graph` and `resume` — [Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api.md):
  - `goto` adds dynamic edges, but static edges from the same node still run
  - `graph=Command.PARENT` routes to a node in the parent graph, and shared keys need a parent reducer
  - `Command(resume=...)` is the only form meant as `invoke` input, and its value becomes the return value of `interrupt()`
  - annotate return types as `Command[Literal[...]]` so the graph renders
- **`Send("node", state)`** is returned from conditional edges for map-reduce or dynamic fan-out, where each task gets its own input — [Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api.md)
- `Send(..., timeout=...)` overrides the target node's timeout for that one push — [Fault tolerance](https://docs.langchain.com/oss/python/langgraph/fault-tolerance.md)
- **Runtime context.** `context_schema` (for example a dataclass) carries non-state dependencies. Nodes read them as `runtime: Runtime[Ctx]` → `runtime.context`, and also get `runtime.store` — [Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api.md); [Stores](https://docs.langchain.com/oss/python/langgraph/stores.md)
- **Recursion limit** — [Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api.md):
  - `recursion_limit` is a top-level config key, not inside `configurable`
  - the default is **10,007** from 1.1.4, and was 10,000 in 1.0.6 to 1.1.3
  - `RemainingSteps` (from `langgraph.managed`) lets a graph wind down before hitting the limit
  - otherwise catch `GraphRecursionError`
  - `config["metadata"]["langgraph_step"]` holds the step counter
- **Node caching** needs a compile-time cache (for example `InMemoryCache`) plus `CachePolicy(key_func=..., ttl=seconds)` on the node — [Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api.md)
- **`RetryPolicy`** — [Fault tolerance](https://docs.langchain.com/oss/python/langgraph/fault-tolerance.md):
  - defaults: `max_attempts=3`, `initial_interval=0.5`, `backoff_factor=2.0`, `max_interval=128.0`, `jitter=True`
  - `retry_on` defaults to `default_retry_on`, which skips `ValueError`, `TypeError`, `RuntimeError`, `OSError` and similar
  - for `requests` and `httpx` errors it retries only 5xx responses
  - `NodeTimeoutError` is retryable
  - `runtime.execution_info.node_attempt` gives the attempt number
- **Error handlers (langgraph>=1.2)** — [Fault tolerance](https://docs.langchain.com/oss/python/langgraph/fault-tolerance.md):
  - signature is `error_handler(state, error: NodeError)`, and the handler can return `Command` to reroute
  - it runs only after retries are exhausted
  - subgraph exceptions surface to the parent node's handler
  - failure context is checkpointed
  - `interrupt()` (`GraphBubbleUp`) bypasses both retries and handlers
- **Node timeouts (langgraph>=1.2)** — [Fault tolerance](https://docs.langchain.com/oss/python/langgraph/fault-tolerance.md):
  - async nodes only; a sync node with `timeout=` is rejected at compile time
  - accepts seconds, a `timedelta`, or `TimeoutPolicy(run_timeout, idle_timeout, refresh_on="auto"|"heartbeat")`
  - `runtime.heartbeat()` resets the idle timer
  - a timeout raises `NodeTimeoutError` and clears that attempt's writes
- **`set_node_defaults(retry_policy=, error_handler=, timeout=, cache_policy=)`** sets graph-wide defaults. Per-node values override them, and subgraphs **do not** inherit them — [Fault tolerance](https://docs.langchain.com/oss/python/langgraph/fault-tolerance.md)
- **Graceful drain.** Pass `invoke(..., control=RunControl())`. Calling `request_drain()` stops the run at the next superstep boundary, raises `GraphDrained`, and saves a resumable checkpoint. Resume with `invoke(None, config)`. Drain does not cancel asyncio tasks — [Fault tolerance](https://docs.langchain.com/oss/python/langgraph/fault-tolerance.md)
- **Functional API.** `@task` accepts `timeout=` and `retry_policy=`, and `@entrypoint` accepts `timeout=`. Both behave like `add_node` — [Fault tolerance](https://docs.langchain.com/oss/python/langgraph/fault-tolerance.md)
- **Durability modes** are set with the `durability` argument — [Checkpointers](https://docs.langchain.com/oss/python/langgraph/checkpointers.md):
  - `"exit"` persists only when the run exits, including on error or interrupt, so a crash mid-run is not recoverable
  - `"async"` persists while the next step runs, so a crash can lose checkpoints
  - `"sync"` persists before the next step starts
- **Pending writes.** If a node fails mid-super-step, writes from nodes that succeeded in that step are kept and are not re-run on resume — [Checkpointers](https://docs.langchain.com/oss/python/langgraph/checkpointers.md)
- **Subgraphs.** Each subgraph has its own checkpoint namespace (`checkpoint_ns = "node:uuid"`), so the parent may not see subgraph state changes immediately — [Checkpointers](https://docs.langchain.com/oss/python/langgraph/checkpointers.md); [Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- **HITL in agents.** `HumanInTheLoopMiddleware` supports batched or `per_call` interrupts, each with a `response_schema` — [Changelog](https://docs.langchain.com/oss/python/releases/changelog.md)

### Inferences
- The scaffold should ship a `BaseGraphBuilder` that does three things:
  - applies `set_node_defaults` (org-standard `RetryPolicy`, `TimeoutPolicy` and logging `error_handler`), re-applying them inside subgraphs because they are not inherited
  - enforces async nodes, so that timeouts work
  - sets `durability="sync"` for financial or approval workflows, and `"async"` for chat
- Wire SIGTERM handling into `RunControl.request_drain()` for rolling deploys.

### Gaps
- I did not fetch the dedicated interrupts, Functional API and subgraph docs pages. The finer semantics of `interrupt()`, such as re-running a node from the top on resume and matching multiple interrupts by ID, come from my prior knowledge and are not verified here.

## Q3. Persistence: checkpointers, Store, TTLs, thread model, memory tiers

### Takeaway
Use `PostgresSaver` / `AsyncPostgresSaver` (`langgraph-checkpoint-postgres`) for thread-scoped short-term memory. Use `PostgresStore` with an `index={embed, dims, fields}` config for long-term semantic memory, keyed by namespace tuples. Encrypt checkpoints with `EncryptedSerializer`, and prune old checkpoints yourself.

### Cited Findings
- **Checkpointer packages** — [Checkpointers](https://docs.langchain.com/oss/python/langgraph/checkpointers.md):
  - `langgraph-checkpoint`: base interface plus `InMemorySaver`
  - `langgraph-checkpoint-sqlite`: `SqliteSaver` / `AsyncSqliteSaver`, for development only
  - `langgraph-checkpoint-postgres`: `PostgresSaver` / `AsyncPostgresSaver`, for production
  - `langgraph-checkpoint-mongodb`
  - `langchain-azure-cosmosdb`, with Entra ID support
  - `langgraph-checkpoint-conformance`, a test suite for custom savers
- `PostgresSaver.from_conn_string(...)` followed by `.setup()` creates the tables. Keep `thread_id` under 255 characters (UUID recommended). In-memory savers lose data on restart. Checkpoints accumulate over long threads, so prune them with a retention cron job — [Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- **Checkpoint model** — [Checkpointers](https://docs.langchain.com/oss/python/langgraph/checkpointers.md):
  - a checkpoint (`StateSnapshot`) is saved at each super-step
  - `get_state(config)` returns the latest snapshot, and `get_state_history` lists them newest first
  - `update_state(..., as_node=)` writes a new checkpoint and applies reducers
  - replaying from a `checkpoint_id` re-runs the later nodes
  - `delete_thread` / `adelete_thread` remove a thread
- Optional extended saver methods are `adelete_for_runs`, `acopy_thread`, `aprune` and `aget_delta_channel_history` — [Checkpointers](https://docs.langchain.com/oss/python/langgraph/checkpointers.md)
- **Serialization** — [Checkpointers](https://docs.langchain.com/oss/python/langgraph/checkpointers.md):
  - the default is `JsonPlusSerializer` (ormsgpack plus JSON)
  - `pickle_fallback=True` handles types such as DataFrames
  - `EncryptedSerializer.from_pycryptodome_aes()` uses `LANGGRAPH_AES_KEY` and is passed as `serde=`
  - custom ciphers implement `CipherProtocol`
- **`DeltaChannel` (beta, langgraph>=1.2)** stores only deltas, which helps append-heavy channels. Custom savers need delta-history support — [Checkpointers](https://docs.langchain.com/oss/python/langgraph/checkpointers.md)
- **Store backends** — [Stores](https://docs.langchain.com/oss/python/langgraph/stores.md):
  - `InMemoryStore` for development
  - production: `PostgresStore` / `AsyncPostgresStore`, `MongoDBStore`, `RedisStore`, `UpstashStore`
  - all extend `BaseStore`, and a custom store needs `aput`, `aget`, `adelete`, `asearch` and `alist_namespaces`
- **Semantic index** — [Stores](https://docs.langchain.com/oss/python/langgraph/stores.md):
  - configure with `index={"embed": init_embeddings("openai:text-embedding-3-small"), "dims": 1536, "fields": [...]}`
  - `put(..., index=[fields])` overrides the embedded fields per item, and `index=False` stores without embedding
  - `store.search(ns, query=..., limit=)` ranks by cosine similarity
  - `list_namespaces(prefix=, max_depth=)` discovers namespaces
  - the default `limit` is 10 and extra results are truncated silently
  - Postgres sorts by `updated_at` descending
- **Namespaces** are string tuples such as `(user_id, "memories")`, and search matches by prefix. The recommended pattern is: threads keyed by `thread_id`, memories keyed by `user_id` taken from `runtime.context`, and the top-k memories retrieved and injected before each model call — [Stores](https://docs.langchain.com/oss/python/langgraph/stores.md)

### Inferences
- Use these namespace conventions:
  - Store: `(tenant_id, app_id, user_id, "memories" | "profile" | "episodes")`
  - threads: a deterministic `f"{tenant}:{uuid7}"` that stays under 255 characters
- Memory tiers:
  - short-term: checkpointer state
  - long-term: `PostgresStore` with pgvector index
  - ephemeral: private state channels, or `index=False` items
- Storage TTL and pruning need a platform job (`aprune` or a SQL cron), because the docs pages I read did not document TTL.

### Gaps
- **Redis checkpointer and TTL config.** The checkpointer page does not list `langgraph-checkpoint-redis`, although `RedisStore` is named on the stores page. I did not find documentation for Store/checkpointer TTL keys (`default_ttl`, `refresh_on_read`, sweep), so they remain unverified.

## Q4. Multi-agent patterns: create_agent, supervisor, swarm, handoffs, subagents-as-tools

### Takeaway
The LangChain v1 docs define five patterns: Subagents (subagents as tools), Handoffs, Skills, Router, and Custom workflow. `langgraph-supervisor` is no longer maintained, and its replacement is `create_agent` with subagents wrapped as tools. `create_agent` middleware is the main extension point.

### Cited Findings
- **The five patterns** — [Multi-agent](https://docs.langchain.com/oss/python/langchain/multi-agent):
  - Subagents: a main agent calls subagents as tools
  - Handoffs: tool calls update state to switch the active agent, prompt or tools
  - Skills: one agent loads prompts and knowledge on demand
  - Router: classify the input, fan out to specialists, then synthesize
  - Custom workflow: a LangGraph graph mixing deterministic and agentic steps
- **Pattern selection.** Use Subagents or Router for parallelism and large-context domains. Use Handoffs or Skills when the same conversation makes repeat requests. Check first whether a single agent is enough — [Multi-agent](https://docs.langchain.com/oss/python/langchain/multi-agent)
- **`langgraph-supervisor` is no longer actively maintained.** Migrate from `create_supervisor` to `create_agent` with subagent tools. For hierarchies, wrap a mid-tier `create_agent` as a tool — [Supervisor migration](https://docs.langchain.com/oss/python/migrate/langgraph-supervisor)
- `create_react_agent` is deprecated in favor of `langchain.agents.create_agent` — [LangGraph v1](https://docs.langchain.com/oss/python/releases/langgraph-v1)
- **Built-in middleware**, which lets the framework standardize guardrails and cost limits without custom graph code — [Built-in middleware](https://docs.langchain.com/oss/python/langchain/middleware/built-in.md):
  - resilience: `ToolErrorMiddleware`, `ToolRetryMiddleware`, `ModelRetryMiddleware`, `ModelFallbackMiddleware`
  - context: `SummarizationMiddleware`, `ContextEditingMiddleware` (`ClearToolUsesEdit`)
  - human-in-the-loop: `HumanInTheLoopMiddleware`
  - cost limits: `ModelCallLimitMiddleware`, `ToolCallLimitMiddleware`
  - guardrails: `PIIMiddleware`
  - tools: `TodoListMiddleware`, `LLMToolSelectorMiddleware`, `ProviderToolSearchMiddleware`, `ShellToolMiddleware`, `FilesystemFileSearchMiddleware`
  - testing: `LLMToolEmulator`
  - Deep Agents: `FilesystemMiddleware`, `SubAgentMiddleware`, `RubricMiddleware` (beta)
- The multi-agent page points to Managed Deep Agents and LangSmith Deployment for built-in hosting. Those are managed options, which this effort excludes — [Multi-agent](https://docs.langchain.com/oss/python/langchain/multi-agent)

### Inferences
- The framework should ship a `make_agent()` factory around `create_agent`. It would apply standard middleware (retry, fallback, call limits, PII and HITL with `per_call`), add a "subagent-as-tool" helper, and expose a Router/fan-out graph template built on `Send`. That template would mirror the DeepAgents scaffold's `SubAgentMiddleware`.

### Gaps
- I found no official statement on whether `langgraph-swarm` is maintained or deprecated. The Handoffs pattern in the docs appears to be its successor, but that is unconfirmed.
- I did not document the middleware hook names (`before_model`, `wrap_model_call` and so on), because the built-in page does not cover them.

## Q5. Streaming modes, async and concurrency

### Takeaway
LangGraph streams in seven modes: `values`, `updates`, `messages`, `custom`, `checkpoints`, `tasks` and `debug`. `version="v2"` (langgraph>=1.1) gives one typed `StreamPart` format for all of them. Parallelism inside a run comes from super-steps and `Send`. Across threads, scale by running independent `thread_id`s concurrently with `ainvoke` / `astream` on async checkpointers.

### Cited Findings
- **Modes** — [Streaming](https://docs.langchain.com/oss/python/langgraph/streaming.md):
  - `values`: full state after each step
  - `updates`: per-step deltas
  - `messages`: (token, metadata) pairs from LLM calls
  - `custom`: data emitted with `get_stream_writer()`
  - `checkpoints` and `tasks`: require a checkpointer
  - `debug`: combines the two above with extra metadata
- **v2 format.** Each chunk is a `StreamPart` with `type`, `ns` and `data`. The root graph's `ns` is `()`. `subgraphs=True` surfaces subgraph and nested-agent tokens. Pass several modes as a list and filter on `chunk["type"]` — [Streaming](https://docs.langchain.com/oss/python/langgraph/streaming.md)
- **Filtering `messages`.** Filter by `metadata["tags"]` or `metadata["langgraph_node"]`. The `nostream` tag hides a model's tokens — [Streaming](https://docs.langchain.com/oss/python/langgraph/streaming.md)
- **Async on Python <3.11.** Pass `RunnableConfig` explicitly to `ainvoke`. `get_stream_writer` does not work in async nodes, so take a `writer: StreamWriter` parameter instead — [Streaming](https://docs.langchain.com/oss/python/langgraph/streaming.md)
- **Agent Server background runs.** Redis is the pub/sub broker for streaming background-run output, and Postgres holds the queue. Scaling settings are `numberOfJobsPerWorker`, `api.replicas` and `queue.replicas`. Non-Kubernetes deployments must build their own queue autoscaling and draining — [Standalone server](https://docs.langchain.com/langsmith/deploy-standalone-server.md)
- langgraph-sdk 0.4.11 adds resumable stream reconnects (Last-Event-ID, backoff), and 0.4.9 adds a thread `Priority` — [GitHub releases](https://github.com/langchain-ai/langgraph/releases)

### Inferences
- Running requirements on Python 3.11+ avoids the async context-propagation caveats.
- In a FastAPI host, serve one compiled graph per process (graphs are stateless, and state lives in the checkpointer). Use an `AsyncConnectionPool` for Postgres, and cap concurrent runs per tenant with an `asyncio.Semaphore` or a queue such as Redis or Celery/Arq.
- Use SSE to relay `StreamPart`s to clients.

### Gaps
- I found no documentation of thread-safety guarantees, such as two concurrent runs on the same `thread_id` outside Agent Server. The Agent Server's multitask strategies (reject, interrupt, rollback, enqueue) were not verified this session.

## Q6. Self-hosting: Agent Server / LangGraph Server vs FastAPI plus checkpointer, Agent Protocol

### Takeaway
Self-hosting the official Agent Server (the `langgraph-api` image, built with `langgraph build`, Helm chart `langgraph-cloud`) needs Postgres, Redis, a LangSmith license key, and outbound access to `beacon.langchain.com` unless air-gapped. That makes it a licensed, semi-managed dependency. Fully open self-hosting means FastAPI plus a checkpointer and Store, or the third-party Apache-2.0 Aegra server.

### Cited Findings
- **Standalone server requirements** — [Standalone server](https://docs.langchain.com/langsmith/deploy-standalone-server.md):
  - env vars: `DATABASE_URI` (Postgres for assistants, threads, runs, state and queue), `REDIS_URI` (pub/sub), `LANGSMITH_API_KEY`, `LANGGRAPH_CLOUD_LICENSE_KEY` (checked once at startup), and optional `LANGSMITH_ENDPOINT` for self-hosted LangSmith
  - license checks and usage reporting go to `beacon.langchain.com` unless air-gapped
  - build the image with `langgraph build`; the Compose example uses `postgres:16` and `redis:6`
  - Helm chart `langgraph-cloud` (MongoDB checkpointing from chart 0.2.6+)
- **Older LangGraph Server tiers.** A "Lite" self-hosted tier was capped at 1M nodes executed per year. Enterprise needs a license key, and custom auth and cron jobs were Enterprise-only — [LangGraph Server concept (older docs)](https://langchain-ai.github.io/langgraph/concepts/langgraph_server). **This conflicts with** the newer auth page, which says custom auth is "supported for all LangSmith plans" — [Auth](https://docs.langchain.com/langsmith/auth.md)
- **Aegra** is an open-source, Apache-2.0, LangGraph-SDK-compatible backend, separate from LangChain — [Aegra (fork mirror)](https://github.com/fork-archive-hub/aegra-langgraph)
- langgraph-cli 0.4.39 and 0.4.40 add control-plane deploy features (`deploy list --json`, upload headers), which shows the CLI is oriented toward LangSmith Deployment — [GitHub releases](https://github.com/langchain-ai/langgraph/releases)

### Inferences
- For the stated constraint of no managed or hosted runtime, the default should be a **FastAPI service** with these parts:
  - compiled graphs
  - `AsyncPostgresSaver` plus `AsyncPostgresStore`
  - SSE streaming
  - a run queue (Redis or Arq)
  - your own auth
- Offer the licensed Agent Server, which keeps Studio and SDK compatibility, as an optional profile. Keep `langgraph.json` in every repo so either runtime works and so `langgraph dev` and Studio work locally.

### Gaps
- I found no current, authoritative statement of the license terms, free-tier limits, or whether the `langgraph-api` image can run without a license key. I did not verify Agent Protocol (the open REST spec for agents) or the current `langgraph dev` / in-memory server licensing. Check the LangChain pricing and licensing pages before deciding.

## Q7. Observability: LangSmith (self-hosted or OTel), Langfuse, Phoenix, OpenLLMetry, cost tracking

### Takeaway
LangChain and LangGraph can emit OpenTelemetry natively via `langsmith[otel]` with `LANGSMITH_OTEL_ENABLED=true` and `LANGSMITH_OTEL_ONLY=true`, exporting OTLP to any backend. Langfuse's `CallbackHandler` is a drop-in alternative that supports per-run user, session and tag attribution.

### Cited Findings
- **LangSmith OTel** — [LangSmith OTel docs](https://docs.langchain.com/langsmith/trace-with-opentelemetry.md):
  - set `LANGSMITH_OTEL_ENABLED`, usually with `LANGSMITH_TRACING`, and LangChain/LangGraph emit OTel spans with no code changes
  - first available in langsmith 0.4.1; 0.4.25+ recommended
  - point it elsewhere with standard `OTEL_EXPORTER_OTLP_*` variables
  - `LANGSMITH_OTEL_ONLY=true` turns off native LangSmith export
  - a sample Collector config fans traces out to several backends
  - for self-hosted LangSmith, append `/api/v1` to the endpoint
- **Langfuse** — [Langfuse LangChain integration](https://langfuse.com/integrations/frameworks/langchain):
  - attach `from langfuse.langchain import CallbackHandler` via `config={"callbacks": [handler]}`
  - Python SDK v5 requires `langchain-core>=1`
  - per-run attribution through metadata keys `langfuse_user_id`, `langfuse_session_id` and `langfuse_tags`, or `propagate_attributes(user_id=, session_id=)`
- Self-hosted Agent Server can send traces to a self-hosted LangSmith via `LANGSMITH_ENDPOINT` — [Standalone server](https://docs.langchain.com/langsmith/deploy-standalone-server.md)

### Inferences
- Standardize on OTel as the transport, sending to an OTel Collector. From there, fan out to Langfuse (self-hosted), Phoenix, or LangSmith per company.
- Stamp `tenant_id`, `app_id`, `user_id` and `thread_id` as span or trace attributes and in LangChain `metadata`, so cost and tokens can be split per tenant.
- Emit structured JSON logs that carry the same IDs plus the `trace_id`.

### Gaps
- I did not fetch these, so I have no verified details on:
  - Arize Phoenix and OpenLLMetry instrumentation for LangGraph
  - the current status of the OTel GenAI semantic conventions (`gen_ai.*` attributes)
  - Langfuse self-host components and license
  - LangSmith token and cost tracking specifics

## Q8. Multi-tenancy, governance, model gateway, rate limiting, guardrails

### Takeaway
Tenant isolation rests on three things: namespace-scoped Store keys, ownership-filtered threads, and (on Agent Server) `langgraph_sdk.Auth` handlers. On a FastAPI host the same pattern has to be rebuilt by hand. Guardrails and limits are available as LangChain middleware (`PIIMiddleware`, call limits, moderation, fallback).

### Cited Findings
- **`langgraph_sdk.Auth`** — [Auth](https://docs.langchain.com/langsmith/auth.md):
  - `@auth.authenticate` runs on every request and returns a `MinimalUserDict` (`identity` plus custom fields such as `org_id` and `role`)
  - the user is exposed to graphs as `config["configuration"]["langgraph_auth_user"]`
  - `@auth.on` handlers exist at global, resource (`threads`, `assistants`, `crons`, `store`) and action (for example `threads.create`) levels
  - a handler can stamp `value["metadata"]["owner"]` and return a filter dict (`$eq`, `$contains`, ANDed)
  - **store handlers rewrite `namespace`** instead of filtering
  - runs inherit the thread's access control except `create_run`
  - **self-hosted deployments have no default auth**
- `PIIMiddleware`, `ModelCallLimitMiddleware` / `ToolCallLimitMiddleware` and `ModelFallbackMiddleware` provide guardrails, cost caps and provider failover — [Built-in middleware](https://docs.langchain.com/oss/python/langchain/middleware/built-in.md)
- An OpenAI moderation middleware arrived in langchain 1.1. Model `.profile` exposes capability data, which helps with provider-agnostic model selection — [Changelog](https://docs.langchain.com/oss/python/releases/changelog.md)
- Checkpoint encryption at rest is available through `EncryptedSerializer` / `LANGGRAPH_AES_KEY` — [Checkpointers](https://docs.langchain.com/oss/python/langgraph/checkpointers.md)

### Inferences
- Between tenants, prefer separate Postgres databases or schemas per tenant, which is hard isolation. Within a tenant, use namespace prefixes and `owner` / `tenant_id` thread metadata, which is soft isolation.
- Use `init_chat_model("provider:model")` or a LiteLLM proxy as the single model gateway, so keys, budgets and per-tenant rate limits sit outside agent code.

### Gaps
- I did not verify LiteLLM proxy features (virtual keys, budgets, rate limits) or `init_chat_model` details this session. Rate limiting via langchain-core `InMemoryRateLimiter` is also unverified.

## Q9. Project templates and packaging for a shared framework

### Takeaway
The verified anchor is `langgraph.json`, which configures graphs, store index and auth for the Agent Server and `langgraph dev`. The case for a uv workspace monorepo is inference only.

### Cited Findings
- `langgraph.json` takes a `"store": {"index": {...}}` block for semantic search. Note a docs inconsistency in the embedding model name (`text-embeddings-3-small` vs `text-embedding-3-small`) — [Stores](https://docs.langchain.com/oss/python/langgraph/stores.md)
- `langgraph.json` `auth.allow_langsmith_api_keys` is available in Agent Server v0.14.0rc2+ — [Auth](https://docs.langchain.com/langsmith/auth.md)
- `langgraph build` packages the agent as a Docker image for the standalone server — [Standalone server](https://docs.langchain.com/langsmith/deploy-standalone-server.md)
- `langgraph-checkpoint-conformance` exists for validating custom savers, which is useful when the platform wraps savers with tenancy or encryption — [Checkpointers](https://docs.langchain.com/oss/python/langgraph/checkpointers.md)

### Inferences
- **Proposed layout:** a uv workspace with these packages, plus a cookiecutter or copier template that generates a team app with `langgraph.json`, a Dockerfile and a FastAPI entrypoint:
  - `platform-core`: state base classes, `BaseGraphBuilder` defaults, context schema with `tenant_id` / `user_id`
  - `platform-persistence`: saver and store factories, encryption, pruning
  - `platform-agents`: the `create_agent` factory and middleware presets
  - `platform-observability`: OTel setup, logging
  - `platform-server`: FastAPI runtime plus an auth adapter that mirrors the `Auth` semantics
- The Graph API base and the DeepAgents scaffold can share `platform-core`, `platform-persistence` and `platform-observability`.

### Gaps
- I found no official LangChain template or guidance on uv workspaces, and did not verify the full `langgraph.json` schema keys (`dependencies`, `graphs`, `env`, `http.app`, `auth.path`, `checkpointer.ttl`, `store.ttl`) this session.
