# agentkit — architecture in diagrams

One common DeepAgents harness + one set of shared capabilities + a declarative layer that
assembles them into apps. This file is the **why**, as pictures; the decision IDs `[D#]` match
the rationale in git history and the specs; [`docs/architecture.md`](docs/architecture.md) is the
code-level **what/how**.

Status: Phase 0/0b, 1, 1b, 2a **done and live-verified** · Phase 2 (MCP, skills lib, HITL) **next**.

---

## 1. The platform thesis [D1 D3 D4]

```
            +-----------------------------------------------------+
            |                        APPS                         |
            |   apps/research_agent      apps/kb_agent  (next...) |
            |   agent.yaml + flows/*.yaml    (YAML only: goal)    |
            +------------------------+----------------------------+
                                     |  references capabilities
                                     |  by ID + version
            +------------------------v----------------------------+
            |                 CAPABILITY POOLS                    |
            |  libraries/:  prompts   skills  subagents  connectors|
            |  entry pts.:  tools     middleware  nodes  schemas  |
            +------------------------+----------------------------+
                                     |  resolved under tenant policy
                                     |  at BUILD time
            +------------------------v----------------------------+
            |              HARNESS POLICY  (packages/)            |
            |  middleware order | guards | tenancy | persistence  |
            |  telemetry | cost ledger | evals | model registry   |
            +------------------------+----------------------------+
                                     |  SDK extension points ONLY
                                     |  (context_schema, middleware slot,
            +------------------------v--------- CompositeBackend)|
            |        DeepAgents 0.7.32 / LangChain 1.4.7 /        |
            |        LangGraph 1.2.19     pinned in constraints   |
            +-----------------------------------------------------+
```

- Never fork deepagents — policy only, through extension points `[D1]`.
- Apps are YAML; Python only when a pool lacks a capability `[D3]`.
- Ownership split: `packages/` platform team · `libraries/` domain teams · `apps/` product teams `[D4]`.

## 2. Assembling an app [D3]

```
 (1) PICK/ADD CAPABILITY   tools+middleware: entry points | content: libraries/
 (2) DECLARE APP           apps/<app>/agent.yaml  (+ flows/*.yaml)
 (3) VALIDATE OFFLINE      agentkit validate   (no keys, no network, ALL errors at once)
 (4) STAMP TENANT          make stamp TENANT=<t>
 (5) RUN                   research "..." --agent apps/<app>/agent.yaml --persist
 (6) GATE                  research-eval --gate gates.yaml  (CI blocks regressions)
```

```
  agent.yaml          validate             resolve                  build
 +-----------+   +----------------+   +----------------+   +-------------------+
 | kind Agent|---> names exist?   |---> render prompt  |---> build_deep_agent|
 | model     |   | params fit?    |   | build tools    |   | (**kwargs)        |
 | prompt    |   | tenant policy? |   | build mw       |   | = the ONLY        |
 | tools[]   |   | skills->tools? |   | build subagents|   |   create_deep_    |
 | mw[]      |   | subagent schema|   | skills routes  |   |   agent call      |
 | output    |   | (every error,  |   +----------------+   | + prompt_hash on  |
 +-----------+   |  file + path)  |                        |   graph metadata  |
                 +----------------+                        +-------------------+
```

## 3. The middleware stack [D7 D8]

`build_deep_agent` ALWAYS yields this stack; YAML file order is irrelevant:

```
 outer  + TenantGuardMiddleware   run tenant == deployment tenant (CLI pre-checks too)
        + GuardMiddleware         deny-only guards -- YAML cannot name/drop/reorder [D9]
        + selection               Decisions picks tools + tier (once per thread) [D10]
        + model_fallback          primary -> <strong> model on failure
        + model_retry             retries per model
        + tool_retry
        + require_output          nudge until output file exists (max 2 nudges)
        + call_limit              hard model-call budget
        + tool_call_limit         per-tool budgets (write_file NEVER budgeted)
 inner  + pii                     redact email / mask card numbers

        DeepAgents wraps its own stack around this user-middleware slot.
```

Each tool call passes the guard tier first `[D9]`:

```
   model emits tool call
          |
          v
   +----------------------------------------------+
   | GuardMiddleware (wrap_tool_call)             |
   |   tenant_tool_policy: @platform_tool         |
   |      metadata present? tenants allow?        |
   |   side_effects: class allowed by             |
   |      AGENTKIT_ALLOWED_SIDE_EFFECTS?          |
   |      (tenant stamp; default read,external)   |
   |   deny-only, fail closed (raise == deny)     |
   +------+--------------------------------+------+
          | deny                           | allow
          v                                v
   ToolMessage "refused by..."         tool body runs
   + counts against tool_call_limit
   + never retried by tool_retry

   installed on main agent AND first in EVERY subagent
   (incl. general-purpose) -- no bypass via `task`
```

## 4. Selection: one Decisions call per thread [D10]

```
 first model call of a thread
   |
   | ONE batched request -> OpenAI Decisions API (gpt-6-luna)
   |   <system> + <tool_catalog> + <request>
   |   1 predicate question per tool + 1 tier choice
   v
 keep tool if P >= 0.5 (unanswered keeps it); DeepAgents built-ins always kept
 tier swap only if confidence >= 0.5
   |
   +-- stored in state (agentkit_selection): sticky per thread,
   |     survives restarts under a checkpointer
   +-- ANY selector failure -> keep ALL tools + default tier (cached for thread)
        never breaks the run; circuit breaker + shared across the process

   RISK (fixture-proven): vague prompt -> P(search)=0.03 -> tools hidden.
   Agents with selection must NAME their tools in the prompt.
```

## 5. Shared tools [D12 D13 D14]

Governance is on the factory, checked at load, enforced per call:

```
 @platform_tool(owner, version, tenants, side_effects, identity, classification)
      |                              |
      | load time                     | call time
      v                              v
 agentkit validate refuses       GuardMiddleware denies
 disallowed tenants;             (unregistered / wrong tenant /
 make tool-schemas snapshot      side-effect class not allowed)
 fails CI on schema change
 without a MAJOR version bump
```

Web search: a fallback chain, order owned by the platform `[D14]`:

```
 web_search(query, k)
   |  backend: auto
   v
 +---------------------------------------------------------+
 | parallel ---> brave ---> tavily ---> duckduckgo (keyless)|
 |   ^fail       ^fail       ^fail                         |
 +---------------------------------------------------------+
   fail = ToolError -> next backend
   auth/quota status (401,402,403,432) -> backend DISABLED for the run
   brave quirk: bad key = HTTP 422 SUBSCRIPTION_TOKEN_INVALID
                -> mapped to 401 -> disabled after ONE failure
   empty result -> "No results." (not an error)
   cache on (normalised query, k)
   third-party backends: agentkit.search_backends seam, by name only
```

Data access: curated tools, never raw connectors `[D13]`:

```
 libraries/connectors/*.yaml (pgvector | postgres)
      |
      v
 kb_search(query,k)          sql_query(sql)
 pgvector similarity,        ONE statement, READ ONLY txn (rolled back),
 cites [n] source_url        kb_reader role, schema allowlist, row/cell caps,
                             refuses privileged login at call time
                             ^ the DB ROLE is the real wall; checks = defence
```

## 6. Models [D11]

```
 models.yaml: logical entry -> provider id per tier (fast | default | strong)
   fireworks-glm:  glm-5p3-flash          glm-5p3 (strong)
 --model ENTRY  /  model: in YAML   ==  provider switch is CONFIG, never code.
 Live testing standardized on fireworks-glm; other providers: 1 live call + offline.
```

## 7. Tenancy [D5 D19]

```
        HARD WALLS between tenants: separate deployments, shared code only

   make stamp TENANT=acme                 make stamp TENANT=globex
     deploy/tenants/acme.env                deploy/tenants/globex.env
     (own AES key, db pw, 2 ports)          (own AES key, own ports)
             |                                      |
     +-------v---------+                    +-------v---------+
     | compose project |                    | compose project |
     | agentkit-acme   |                    | agentkit-globex |
     |   postgres (key A)                   |   postgres (key B)
     |   otel collector :A                  |   otel collector :B
     +-----------------+                    +-----------------+

     `make phase0-exit` proves it: no shared port/key/span/row.

   WITHIN a tenant: soft walls -- namespaces from PlatformContext
   (tenant, product, team, USER_ID | "global", kind)
   labels ^[a-z0-9][a-z0-9_-]{0,62}$, no dots; "global" reserved user id
```

## 8. Memory tiers [D21]

Agent file tools hit one `CompositeBackend`, routed by path prefix:

```
   path                          backend                      scope / writable
   ----------------------------  ---------------------------  ----------------------
   /memories/                    StoreBackend(...,USER,...)   one user, all threads, YES
   /org/                         StoreBackend(...,"global",)  whole tenant, NO (denied)
   /skills/<owner>/...           read-only FS per skill       one owner, NO
   anything else                 StateBackend                 this thread only, YES
     (/report.md, /large_tool_results/...)

   /org/AGENTS.md + /memories/AGENTS.md load into the prompt (org first).
   Skills mount is owner-scoped; writes denied twice (permission + backend). [D15]
```

## 9. Persistence [D20]

```
 open_persistence(DATABASE_URL + LANGGRAPH_AES_KEY)
   |
   +-- AsyncPostgresSaver(serde=AES)     checkpoint blobs + writes ENCRYPTED
   +-- AsyncPostgresStore->EncryptedStore    store VALUES encrypted
   +-- lock pool: pg_advisory_lock(thread_id) held for the WHOLE turn
   |        (2 concurrent runs on 1 thread would fork the checkpoint chain)
   +-- agentkit-prune --older-than 30d   deletes whole threads

   PLAINTEXT  (so user content is BANNED from these):
     checkpoints.metadata (run identifiers ONLY), primitive top-level
     state channels, store namespaces/keys, agentkit_usage (token counts)
```

## 10. Telemetry and cost [D22 D23]

```
 run_config(ctx, prompt_hash, ledger)
   metadata = tenant/product/team/user/thread/agent/prompt_hash   (IDENTIFIERS ONLY)

   spans  own TracerProvider --> tenant collector --> file (+ Langfuse)
          masked BY DEFAULT: prompt/completion text, error strings removed
          AGENTKIT_TRACE_PAYLOADS=1 to keep (dev only)
          LANGSMITH_TRACING deliberately never set (no masking hook)

   usage  CostLedger (async callback) --> 1 agentkit_usage row per run
          input/output/cached/decisions tokens (no prices yet)

   PRINCIPLE  "model-visible means logged" [D23]:
   every middleware that changes what the model sees must log what it decided.
   audit done; per-call recording + reconstruct() still open.
```

## 11. Eval gates [D24 D25]

```
 datasets (JSONL, versioned)
   research/evals/golden.jsonl  25 full cases  --+
   research/evals/steps.jsonl   12 single-step   +--> run --> per-case scores
   kb_agent/evals/golden.jsonl  20 full cases  --+            citation_validity,
                                                             groundedness, completeness,
                                                             tool_recall, step_pass ...
                         single-step = interrupt before the tools node,
                         assert the NEXT tool call -- 1 model call per case
                                       |
                                       v
                     compare vs committed baseline.json, bounds from gates.yaml
                                       |
        FAIL on: pass->fail flip | missing metric | dropped case |
                 bound breach | dataset/model mismatch (re-record instead)
```

Testing shape: offline by default (scripted models), `pg` marker for Postgres, `live` marker for
one call per provider, `contracts/` pins upstream behaviour, weekly canary against new releases `[D25]`.

## 12. Deployment [D26]

```
 dev:     compose.dev.yaml (throwaway pg + optional collector)
 tenant:  make stamp / unstamp; env file deploy/tenants/<t>.env is the ONLY
          copy of the AES key -- back it up
 CLI:     research | research-eval | agentkit validate | agentkit tools ...
 CI:      lint + offline tests + pg tests per PR; canary Mondays
```

## 13. Roadmap [D26 roadmap]

```
 done   Phase 0/0b   factory, context, encrypted persistence, memory tiers,
                     telemetry + ledger, tenant stamps, declarative YAML
 done   Phase 1      middleware stack, eval gates, tool governance,
                     prompt registry, connectors, single-step evals, KB pilot
 done   Phase 2a     guard tier, seams (search_backends, secrets), model-visible audit
 next   Phase 2      MCP gateway (tool_sources provider, behind guards [D17]),
                     skills library CI, PlatformGraph, calibrated judges, HITL
 then   Phase 3      tool-surface strategies (catalog size drives: <=10 all,
                     10-50 intent filter, >50 defer), A/B tooling
 then   Phase 4      channels (Slack), OAuth/OBO identity, sandbox + secret proxy [D18],
                     scheduler -- the "company-harness glue"
 last   Phase 5      online evals, trace-to-golden mining, platform 1.0
```

## 14. Open items (decision debt)

```
 thread-to-user binding (P10)     |  HITL approval for write tools
 primitive-state plaintext (P3)   |  P2-C steps 2-4 (reconstruct())
 AES key rotation / backup        |  seams: vectorstores, embeddings, tool_sources
 prune tenant filter              |  Vault-style secret providers (env:// only today)
 eval users' store pruning        |  layered pools + tenant filtering
 judge calibration, pass^k, VCR   |  minimum-tools guard for Decisions
 DNS rebinding in fetch_url       |  median/trimmed token gate
```

## 15. Document map

| Document | Role |
|---|---|
| `architecture.md` (this file) | consolidated design decisions as diagrams — the why |
| `docs/architecture.md` | technical reference verified against the code — the what/how |
| `reports/Reusable agent platform components.md` | research foundation and full roadmap |
| `docs/superpowers/specs/*.md`, `docs/superpowers/plans/*.md` | per-phase specs and plans |
| `docs/phase*-results.md`, `docs/phase2-model-visible-audit.md` | evidence and live-verification results |
| `research_notes/` | provider and prior-repo research |
