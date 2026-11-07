# Agentic AI Platforms for an Enterprise Team — Comparative Assessment

**LangChain/LangSmith · Google ADK · CrewAI · Microsoft Copilot Studio · OpenAI**

*Current as of November 2026. This market changes monthly; treat pricing and compliance details as directionally accurate and re-verify at contract time. Claims are tagged with numbered citations; vendor-reported figures and third-party estimates are flagged as such.*

---

## 1. Bottom line up front

| If your team is… | Lean toward | Why |
|---|---|---|
| Microsoft-centric, mixed business/IT builders, agents tied to M365 data | **Microsoft Copilot Studio** | Deepest enterprise integration (Entra, Purview, 1,400+ connectors) and the only true low-code option at enterprise scale [43][48][53] |
| Engineering-led, building custom agent products, wants model/cloud flexibility plus mature observability and evals | **LangChain/LangGraph + LangSmith** | Most-used agent framework by a wide margin, provider-agnostic, SOC 2/HIPAA, cloud/hybrid/self-hosted options [7][8][15] |
| Already on Google Cloud | **Google ADK (+ Vertex AI Agent Engine)** | Clean open-source framework with a managed runtime that inherits GCP's compliance stack (FedRAMP High, CMEK, VPC-SC) [18][21] |
| Committed to OpenAI models and/or wants distribution inside ChatGPT | **OpenAI (Responses API, Agents SDK/API, AgentKit)** | Fastest path to production agents and the only way to reach ChatGPT's user base, at the cost of model-vendor lock-in [58][64][65] |
| Prototyping role-based multi-agent workflows quickly | **CrewAI** | Lowest-friction multi-agent framework with a young but real enterprise control plane (AMP); requires procurement due diligence [27][28][29] |

Reality check before choosing: Gartner predicts **over 40% of agentic AI projects will be canceled by end-2027** (cost, unclear value, inadequate risk controls) [1], and enterprises **bought rather than built 76% of AI use cases** in 2025 [3]. Platform choice should follow your use-case portfolio — copilot-style employee assistants are largely a *buy* decision; custom, differentiating agent products are a *build* decision, and these five platforms serve mostly the build side (Copilot Studio straddles both).

---

## 2. Evaluation criteria used

1. **Builder persona** — code-first engineers vs low-code business builders
2. **Model & cloud flexibility** — single-vendor lock-in vs any-LLM/any-cloud
3. **Deployment & data control** — SaaS-only vs VPC/self-hosted; data residency
4. **Security & compliance** — SOC 2/HIPAA/GDPR/FedRAMP, SSO/SCIM, data-use terms
5. **Observability, evaluation & governance** — tracing, evals, RBAC, audit
6. **Pricing model & predictability** — metering unit, entry cost, bill-shock risk
7. **Ecosystem & integrations** — connectors, MCP/A2A interoperability
8. **Vendor maturity & adoption** — funding, customer base, roadmap velocity

---

## 3. Market context

- Gartner (June 2025): >40% of agentic AI projects canceled by end-2027; 33% of enterprise software will include agentic AI by 2028 (from <1% in 2024); 15% of day-to-day work decisions made autonomously by 2028 [1]. Gartner (Aug 2025): 40% of enterprise apps will feature task-specific AI agents by end-2026, up from <5% in 2025 [4].
- Forrester (2026): roughly three-quarters of enterprises are adopting agentic AI but few have scaled it — the "chase-catch gap" [2]; its Q3 2026 AI Platforms Wave says agentic AI has redrawn what counts as an AI platform and widened the vendor field [5].
- Menlo Ventures (Dec 2025): enterprise GenAI spend reached **$37B (3.2× YoY)**; 76% of use cases were *purchased*; copilots captured ~$7.2B (86%) of horizontal spend vs ~$750M (10%) for agent platforms; enterprise LLM API share: **Anthropic 40% / OpenAI 27% / Google 21%** [3].
- Framework adoption (third-party download analysis, July 2026): **LangGraph ~34.5M monthly downloads — ~3.3× the OpenAI Agents SDK and ~6.6× CrewAI**; Microsoft's AutoGen is in maintenance mode [15].
- Interoperability is converging on **MCP** (supported natively by all five platforms — Copilot Studio GA'd MCP in May 2025 [46], ADK ships MCP tools [18], OpenAI's Agents API supports MCP connections [58]) and **A2A**, donated by Google to the Linux Foundation in June 2025 [67] and now backed by 150+ organizations including Microsoft, AWS, Salesforce, SAP, and ServiceNow [68]. This materially reduces lock-in risk: tools and agents built as MCP/A2A endpoints can outlive any single framework choice.

---

## 4. Platform profiles

### 4.1 LangChain / LangGraph / LangSmith

**What it is.** An open-source stack — LangChain (quick-start agents) and LangGraph (low-level orchestration with durable execution, human-in-the-loop, persistence) — plus **LangSmith**, the commercial platform for observability, evaluation, deployment, and governance. LangChain and LangGraph **1.0 shipped October 22, 2025** with a no-breaking-changes-until-2.0 commitment, after a rewrite that the company itself admits was needed ("abstractions were sometimes too heavy") [6]. LangSmith is framework-agnostic and can trace agents built on other stacks [70].

**Licensing & pricing (verified on vendor pricing page).** Frameworks are **MIT-licensed** [10]. LangSmith: **Developer free** (1 seat, 5k base traces/mo); **Plus $39/seat/mo** (10k base traces, 1 free small serverless deployment, unlimited seats); **Enterprise custom** (self-hosted/hybrid options, custom SSO, ABAC/RBAC, SLA, annual invoicing). Usage is metered in **LSUs ($1 = 1 LSU)** — e.g., deployment runtime at 0.0675 LSU/vCPU-hr; the Engine feature (autonomous trace diagnosis) consumes ~7–45 LSUs per 6-hourly run; Fleet (no-code agents) and Sandboxes are metered similarly [7].

**Deployment & security.** LangSmith Enterprise offers **Cloud (US or EU), Hybrid (SaaS control plane + self-hosted data plane in your VPC), or fully Self-Hosted**; SOC 2 Type II, HIPAA, GDPR; SAML/OIDC SSO with SCIM, RBAC and ABAC (e.g., PII-restricted workspaces), configurable retention/purging [8], AWS PrivateLink on cloud [9], and AWS Marketplace availability (July 2025) for easier procurement [14]. LangSmith states it **does not train on customer data** [7].

**Model flexibility.** Works with essentially any model provider (OpenAI, Anthropic, Google, open-weight models via Ollama/vLLM) — the most vendor-neutral of the five [70].

**Maturity & adoption.** $125M Series B at a **$1.25B valuation** (Oct 2025, IVP-led), claiming 90M monthly downloads, ~35% of the Fortune 500 as customers (self-reported), and 12× YoY LangSmith trace growth [11]; customers include Cisco, Replit, Clay, Cloudflare, Workday, ServiceNow [12] and Klarna, Rippling [13]. Caveat on vendor scale: TechCrunch pegged ARR at only **$12–16M as of mid-2025** (the company disputed the figure), so you are betting on a startup for a platform-critical dependency [12].

**Enterprise watch-outs.** 2024–2025 version churn broke imports and forced refactors — a real cost for early adopters, though 1.0's stability commitment addresses it [6][17]; documentation is thin beyond the basics [17]; LSU metering across Engine/Fleet/Sandboxes requires active cost governance [7].

### 4.2 Google ADK (Agent Development Kit) + Vertex AI

**What it is.** An **open-source (Apache-2.0), Python-first framework** announced April 9, 2025 at Cloud Next — the same framework that powers agents inside Google's Agentspace and Customer Engagement Suite [18]. Python v1.0.0 stable shipped May 20, 2025, alongside a Java preview [19]. Core design: multi-agent hierarchies, workflow agents (Sequential/Parallel/Loop), LLM-driven dynamic routing, bidirectional audio/video streaming, a dev Web UI, **built-in evaluation** (response and trajectory), and deployment to **any container runtime or the managed Vertex AI Agent Engine** [18].

**Model flexibility.** Native Gemini plus anything in Vertex AI Model Garden, and **LiteLLM integration for Anthropic, Meta, Mistral, AI21, and others**; it can also use LangChain/LlamaIndex components and even other agents (LangGraph, CrewAI) as tools [18].

**Enterprise security & pricing.** Agent Engine inherits Google Cloud's controls — data residency, CMEK, VPC Service Controls; Agent Engine supports HIPAA workloads; Vertex AI generative services are **FedRAMP High authorized** [21]. Agent Engine began charging for runtime on **Nov 6, 2025** at roughly **$0.085–0.0864/vCPU-hr plus ~$0.009/GiB-hr** (third-party guides differ slightly on the exact rate; confirm on Google's pricing page) [20][22], on top of model token costs.

**Maturity.** The youngest framework here (April 2025) with a much smaller community than LangChain [23][24]. Google itself says "ADK works anywhere, but optimized for Google Cloud" — 100+ prebuilt connectors, Application Integration, AlloyDB/BigQuery/NetApp access, Apigee API reuse [18]. Independent reviewers find it clean but Gemini/Vertex-leaning [23][26]; one third-party benchmark measured a visible latency tax when routing non-Gemini models through the LiteLLM layer [25]. No credible head-to-head ADK-vs-LangGraph benchmark exists; comparisons are qualitative [23].

**Enterprise watch-outs.** Best value if you're already a GCP shop (biggest differentiation is GCP's compliance stack [21]); expect more friction running non-Gemini models at scale [25]; shorter track record means less community precedent for production patterns [23][24].

### 4.3 CrewAI (framework + CrewAI Enterprise/AMP)

**What it is.** An **MIT-licensed**, role-based multi-agent framework (~60.6k GitHub stars) [28], plus a commercial control plane: **CrewAI AMP ("Agent Management Platform")**, launched October 2, 2025, adding managed deployment, observability, governance, and security, deployable in CrewAI's cloud, a dedicated VPC, or on-premise [28][29]. AMP's launch claimed a Fortune 500 customer ran 100k+ executions in ~15 days across ~500k agents (vendor-reported) [29].

**Pricing (verified on vendor pricing page).** **Basic free** (50 workflow executions/mo, Studio visual editor + AI copilot, GitHub integration, MCP-server export); **Enterprise custom** — priced on **executions, not seats**, with SSO (Entra, Okta), RBAC, workload identity, PII redaction, policies, and a 45-day onboarding program; deploy on CrewAI cloud, your VPC, or your own infrastructure [27]. A mid-tier self-serve plan existed at launch (Oct 2025) and was later removed; only Basic/Enterprise remain [42]. CrewAI self-reports being "used by 65% of the Fortune 500" — a marketing claim, not independently verified [27].

**Model flexibility & observability.** Native SDK integrations for OpenAI, Anthropic, Google, Azure, AWS Bedrock, and Snowflake Cortex; everything else (including Ollama/open weights and IBM watsonx) via LiteLLM [30][33]. Observability is via third-party integrations (Langfuse, Arize Phoenix, MLflow, Datadog, Opik, Portkey, and ~15 others) rather than a first-party platform [31].

**Maturity & compliance.** Funding is modest: **$18M raised** (seed + Series A, Oct 2024) [32] — though PitchBook lists $44.5M, a conflict we could not resolve [32]. Third-party trust aggregators report **SOC 2 Type 2 and HIPAA-audited** status for the enterprise product, and CrewAI operates a formal Trust Center [34][35][36]; however, those artifacts are not independently verifiable from public pages, and community threads have questioned the scope of the claims [40]. **Procurement red flag:** third-party reviews flag that CrewAI's SaaS terms grant rights to use customer data "to improve and develop products and services, including by training and developing models," with no published opt-out — verify the current ToS directly before signing [34][35].

**Enterprise watch-outs.** Strong "demo velocity" reputation, but recurring practitioner criticism: observability gaps and debugging "detective work," token bills inflated by inter-agent chatter [37], multi-agent swarm patterns that fail at scale [38], built-in memory/knowledge locked to local datastores (SQLite/Chroma) — a real constraint for multi-pod enterprise deployments [39], and a 28-second cold start measured in one third-party benchmark [25]. Vendor case studies exist (PwC, IBM, AWS, Gelato) but are vendor-reported [41].

### 4.4 Microsoft Copilot Studio (+ Microsoft 365 Copilot)

**What it is.** A **graphical, low-code studio on Power Platform** for building agents, agent flows, and workflows, publishing them into Teams, Microsoft 365 Copilot, websites, and apps [44]. It now organizes authoring into "harnesses" — Copilot Chat, Standard, and GitHub Copilot — plus in-context "Agent Builder" for lightweight agents [43][44]. Autonomous agents (event-triggered, no user prompt) shipped in preview in late 2024 [44]; multi-agent orchestration across M365, Fabric, and A2A was announced at Build 2025 [48].

**Pricing (verified on vendor pricing page).** **M365 Copilot $30/user/month (annual)** now *includes* Copilot Chat plus **Standard-harness agent building and internal agent usage at no additional cost** for licensed users [43]. Standalone Copilot Studio: **$200/month per pack of 25,000 Copilot Credits** (tenant-wide), pay-as-you-go via an **Azure subscription** (required), or pre-purchase with up to 20% savings [43]. Consumption is multi-dimensional: classic answer = 1 credit, generative answer = 2, agent action = 5, tenant-graph grounding = 10, agent-flow actions = 13 per 100; premium generative tools = 10 credits per 1k tokens; **reasoning models bill by token (10 credits/1k billed tokens)** and can dwarf per-message costs; agents are **blocked at 125% of prepaid capacity** unless a PAYG meter is attached [45]. (The billing unit was renamed from "messages" to "Copilot Credits" in September 2025 with no rate change [43][45].)

**Ecosystem & governance — its core differentiator.** Entra ID SSO with per-agent app registrations [44][49]; **1,400+ prebuilt Power Platform connectors** (Microsoft marketing now says 1,500+) [53]; Dataverse for structured agent data; knowledge grounding in SharePoint, public sites, and Microsoft Graph [43][48]; **MCP GA since May 2025** [46] and **A2A** support for invoking external agents [47]; a computer-use tool (hosted Windows) for operating websites/desktop apps [52]; and an explicit **pro-code escape hatch into Azure AI Foundry** (custom models, Azure AI Search, connected agents) when low-code hits its ceiling [57]. Governance is unmatched: Copilot Studio agent audit events flow into **Purview Audit**, agents can be represented as Entra identities with Conditional Access via Agent 365 [49], Purview extends DLP/insider-risk/eDiscovery to agent actions [50], and agents deploy to chosen Azure regions with EU Data Boundary support [51].

**Maturity & adoption.** Microsoft reports **230,000+ organizations, including 90% of the Fortune 500**, have used Copilot Studio (vendor-reported, Build 2025) [48]; Microsoft is a Leader in Gartner's 2025 Magic Quadrant for Enterprise Low-Code Application Platforms [54].

**Enterprise watch-outs.** Credit metering across message types, tools, and token-based reasoning is genuinely complex and is the #1 complaint — CloudZero calls the pricing model "multi-dimensional" and hard to forecast [55], and community threads report bill shocks (e.g., an unverified "$47K bill" report after one agent deployment) [56]. Deep coupling to the Microsoft stack is a feature if you're all-in on M365 and a liability if you're not. Complex cognitive agents outgrow low-code; the intended path is Foundry, which means running two toolchains [57].

### 4.5 OpenAI (Responses API · Agents SDK/API · AgentKit · ChatGPT Enterprise)

**What it is.** OpenAI's agent stack now spans: the **Responses API** (March 2025) [59]; the **Agents SDK**; **AgentKit** (launched DevDay, Oct 6, 2025) — Agent Builder (visual canvas), ChatKit, and Evals for building, deploying, and optimizing agents on the Responses API [64][65]; **apps and connectors inside ChatGPT** for distribution to its ~800M weekly users [65]; and, per current API docs, a hosted **Agents API** with persistent sessions, scheduled automations, OpenAI-hosted or self-hosted sandboxes, MCP connections, multi-agent orchestration, tracing, and even Bedrock-managed agents [58]. The legacy Assistants API was **sunset on August 26, 2026**; OpenAI had flagged the 2026 sunset when it launched the Responses API [59][60]. Codex (with dedicated `gpt-5.3-codex` models) covers software-development agents [58]. Note: OpenAI's fine-tuning platform is being wound down [58].

**Pricing (verified on vendor pricing docs).** Per-token model pricing — current GPT-6 family examples per 1M tokens: **gpt-6.1-terra $1 in/$5 out; gpt-6.1-sol $2/$10; gpt-6-astra $10/$50; gpt-6-luna $0.10/$0.50**. The APIs themselves are not priced separately; built-in tools are: **web search $10/1k calls** (plus search-content tokens at model rates), **file search $2.50/1k calls + $0.10/GB/day storage**, **containers $0.03–$1.92 per 20-minute session** by size; **regional data-residency endpoints carry a 10% uplift** [58]. Computer use is billed through underlying model token rates (the original computer-use-preview model was $3/$12 per 1M tokens) [66]. ChatGPT Enterprise seat pricing is not publicly listed — negotiated.

**Enterprise security.** ChatGPT Enterprise: **no training on business data**, SOC 2 compliance, encryption in transit/at rest [61]; SSO with SCIM, custom data-retention windows, analytics, and CCPA/GDPR support [62]; OpenAI's enterprise-privacy page documents SOC 2 Type 2 completion for ChatGPT Business and restricted-access commitments [63]. API usage is likewise excluded from training by default [63]. Enterprises with Microsoft agreements can procure Azure OpenAI, though capabilities track OpenAI's first-party platform with a lag (commonly reported; not independently verified here).

**Enterprise watch-outs.** **OpenAI models only** — the least model-flexible option here, which matters given Menlo's finding that Anthropic now holds 40% of enterprise API share vs OpenAI's 27% [3]; more than 75% of teams run multiple models [16]. Per-tool-call costs compound in agentic loops [58]. Platform governance/observability, while improving (tracing, evals in AgentKit), is thinner than LangSmith's or Purview's dedicated tooling [58][64]. The flip side: fastest time-to-production for OpenAI-standardized teams and unmatched consumer-scale distribution via ChatGPT apps [64][65].

---

## 5. Side-by-side comparison

| Dimension | LangChain/LangSmith | Google ADK | CrewAI | Copilot Studio | OpenAI |
|---|---|---|---|---|---|
| Builder persona | Code-first engineers | Code-first engineers | Code-first + Studio visual layer | **Low-code business + IT** | Code-first + Agent Builder canvas |
| Open-source core | MIT (LangChain, LangGraph) [10] | Apache 2.0 [19] | MIT [28] | None (SaaS) | SDKs open-source; platform is SaaS |
| Model flexibility | Any provider + open weights [70] | Gemini + Model Garden + LiteLLM [18] | 6 native + LiteLLM [30] | Azure/Foundry models via connectors [43][57] | **OpenAI only** [58] |
| Deployment | Anywhere; LangSmith cloud/hybrid/self-hosted [7][8] | Any container runtime or Vertex Agent Engine [18] | CrewAI cloud, VPC, or self-hosted [27] | Azure only (Power Platform) [43][51] | OpenAI cloud (Azure option) [58][63] |
| Compliance posture | SOC 2 Type II, HIPAA, GDPR; ABAC/RBAC, SCIM [8] | GCP stack incl. **FedRAMP High**, CMEK, VPC-SC [21] | SOC 2 Type 2/HIPAA per aggregators — **verify** [34][35] | Azure + Purview audit/DLP/eDiscovery [49][50] | SOC 2, no-training commitments [61][63] |
| Observability/evals | **Native (LangSmith)**: tracing, evals, Engine [7] | Built-in eval; GCP ops [18] | Via third parties (Langfuse, Datadog…) [31] | Purview + admin analytics [49][50] | Tracing + AgentKit Evals [58][64] |
| Pricing model | $39/seat + LSUs ($1/LSU) [7] | Free OSS + ~$0.085/vCPU-hr runtime + tokens [20][22] | Free 50 execs/mo; custom, execution-based [27] | $30/user/mo or $200/25k credits + token-metered reasoning [43][45] | Tokens + per-tool-call fees [58] |
| Interoperability | MCP; A2A supporter | **MCP + A2A originator** [18][67] | MCP export [27] | **MCP GA + A2A** [46][47] | MCP connections [58] |
| Vendor scale | Startup, $1.25B val., ~$12–16M ARR (mid-2025 est.) [11][12] | Google | Startup, $18M raised [32] | Microsoft | OpenAI |
| Adoption signal | ~34.5M monthly downloads; 3.3× OpenAI SDK [15] | Young (Apr 2025), Google-internal use [18] | ~6.6× smaller than LangGraph [15] | 230k+ orgs, 90% of F500 (vendor) [48] | ~800M ChatGPT WAU [65] |

---

## 6. Recommendations by scenario

1. **Employee-assistance agents over M365 data (Support, HR, Sales ops) → Copilot Studio.** The included-agent licensing inside M365 Copilot ($30/user/mo) makes internal copilots nearly free to stand up for licensed users [43], and Purview governance is enterprise-grade [49][50]. Budget discipline is essential: model your credit burn before going live, attach a PAYG meter to avoid the 125% hard stop, and treat token-metered reasoning agents as a separate cost class [45][55].
2. **Differentiating, customer-facing agent products → LangChain/LangGraph + LangSmith (or ADK if GCP-native).** LangGraph's durable execution and LangSmith's evals/observability directly address the top production barriers (quality and security, per a 1,340-respondent survey where 57% now run agents in production) [16]. Buy the Enterprise tier for hybrid/self-hosted deployment and HIPAA coverage [8]. If your data estate and security stack are already GCP, ADK + Agent Engine gives you comparable capability with FedRAMP-High-grade controls and less vendor risk from a startup [18][21].
3. **OpenAI-standardized orgs / ChatGPT-adjacent experiences → OpenAI AgentKit + Agents API.** Accept the lock-in consciously: hedge by exposing all tools as MCP servers (portable across all five platforms) [58] and keeping prompts/evals exportable. Watch the Assistants API sunset if you have legacy builds — that migration already closed in Aug 2026 [59][60].
4. **Rapid internal prototyping of multi-agent workflows → CrewAI OSS.** Use it for pilots (it's the fastest to first demo [69][70]), but for production either pair it with LangGraph for deterministic control (a pattern seen in enterprise write-ups) or move to AMP with a completed security review — explicitly resolving the ToS training-data clause and SOC 2/HIPAA scope in writing [34][35][40].
5. **Portfolio strategy (what most large enterprises actually land on):** *buy* copilots where the market is mature (76% of use cases were bought in 2025 [3]); *build* only differentiating agents on one primary framework; run a **framework-agnostic observability layer** (LangSmith or an OSS option like Langfuse) across everything [7][31]; and standardize **MCP-first tool interfaces** so agents, tools, and even frameworks remain swappable [46][58][67].

---

## 7. Cross-cutting enterprise risks

- **Project-failure risk.** Gartner's >40% cancellation forecast argues for staged funding, kill criteria, and starting with read-only tools plus human approval gates [1].
- **Bill shock is platform-independent.** Every option meters something different (LSUs, vCPU-hours, executions, credits, tool calls) — all five can produce runaway costs in agentic loops; Copilot Studio and OpenAI's per-tool-call models are the most frequently cited offenders [45][55][56][58].
- **Vendor asymmetry.** You are choosing between a hyperscaler (Google, Microsoft), the model leader (OpenAI), and two startups (LangChain, CrewAI). For startups, contract for source-code escrow or self-hosted deployment (both LangSmith and CrewAI offer self-hosting; ADK and the LangChain/CrewAI frameworks are open source, so worst-case exits are survivable) [7][8][27][28].
- **Compliance nuance.** Certifications differ meaningfully: LangSmith documents SOC 2 Type II + HIPAA [8]; ADK inherits FedRAMP High via Vertex [21]; Copilot Studio inherits Azure + Purview [49]; OpenAI documents SOC 2 for enterprise offerings [61][63]; CrewAI's compliance claims rest on third-party aggregators and a trust portal and should be independently verified [34][35][36].
- **Data-use terms.** LangSmith and OpenAI publish no-training commitments [7][61]; CrewAI's SaaS terms have been flagged as permitting training on customer data — a genuine procurement blocker until resolved [34].
- **Model concentration.** Even "neutral" platforms embed model bets; the market itself has shifted (Anthropic 40% / OpenAI 27% / Google 21% of enterprise API spend [3]), which strengthens the case for model-flexible frameworks [16][70].

---

## 8. Conflicts, uncertainties, and unverified claims

- **CrewAI funding:** press reports say $18M raised [32]; PitchBook lists $44.5M — unresolved conflict.
- **CrewAI compliance:** SOC 2 Type 2 / HIPAA claims come from third-party aggregators and CrewAI's trust portal, not independently verifiable public artifacts; community threads have questioned scope [34][35][36][40].
- **CrewAI ToS training clause:** reported by two third-party reviewers [34][35]; must be confirmed against the live contract.
- **Fortune-500 usage figures** ("35%" LangChain, "65%" CrewAI, "90%" Copilot Studio) are vendor self-reported marketing claims [11][27][48].
- **Vertex AI Agent Engine rate:** $0.085 vs $0.0864 per vCPU-hr appears in different sources; treat as ~$0.09 and confirm at contract time [20][22].
- **LangChain ARR ($12–16M, mid-2025):** third-party estimate, disputed by the company [12].
- **Copilot Studio "$47K bill":** anonymous community anecdote, unverified — cited only as evidence that cost surprises are a known pattern [56].
- **AgentMail benchmark** (CrewAI 28s cold start, ADK LiteLLM latency tax): vendor-run methodology; treat as indicative, not definitive [25].
- **ADK vs LangGraph:** no credible head-to-head benchmark exists; comparisons are qualitative [23].
- **Azure OpenAI feature lag** behind OpenAI's first-party platform: commonly reported, not verified in this research pass.

---

## 9. Suggested next steps

1. **Classify your use-case portfolio** into buy (copilots, ITSM, support macros) vs build (differentiating agents) before picking a platform [3].
2. **Run a 4–6 week bake-off** on two representative workloads (one internal M365-grounded assistant; one custom multi-step agent with tool calls) across a shortlist of two platforms — include a cost model per 10k interactions.
3. **Ask each vendor:** current SOC 2/HIPAA report date; data-use/training terms in the live contract; self-hosted/VPC option and price; credit/LSU/execution forecasting tools; MCP and A2A support status; roadmap commitments in writing.
4. **Stand up the cross-cutting layer first:** observability/evals + an LLM gateway with PII redaction (LangSmith and Langfuse both fill this role across frameworks) [7][31], plus MCP-first tool standards [46][58][67].

---

## Sources

[1] https://www.gartner.com/en/newsroom/press-releases/2025-06-25-gartner-predicts-over-40-percent-of-agentic-ai-projects-will-be-canceled-by-end-of-2027
[2] https://www.forrester.com/blogs/the-state-of-agentic-ai-in-2026-companies-are-chasing-few-are-catching/
[3] https://menlovc.com/perspective/2025-the-state-of-generative-ai-in-the-enterprise/
[4] https://www.gartner.com/en/newsroom/press-releases/2025-08-26-gartner-predicts-40-percent-of-enterprise-apps-will-feature-task-specific-ai-agents-by-2026-up-from-less-than-5-percent-in-2025
[5] https://www.forrester.com/blogs/the-forrester-wave-ai-platforms-q3-2026-is-live-prepare-to-recalibrate/
[6] https://www.langchain.com/blog/langchain-langgraph-1dot0
[7] https://www.langchain.com/pricing
[8] https://docs.langchain.com/langsmith/enterprise
[9] https://docs.langchain.com/langsmith/cloud
[10] https://raw.githubusercontent.com/langchain-ai/langgraph/main/LICENSE
[11] https://www.langchain.com/blog/series-b
[12] https://fortune.com/2025/10/20/exclusive-early-ai-darling-langchain-is-now-a-unicorn-with-a-fresh-125-million-in-funding/
[13] https://www.forbes.com/sites/rashishrivastava/2025/07/09/ai-startup-langchain-is-in-talks-to-raise-100-million/
[14] https://www.langchain.com/blog/aws-marketplace-july-2025-announce
[15] https://the-agent-report.com/2026/07/ai-agent-frameworks-comparison-2026-langgraph-crewai-autogen/
[16] https://www.langchain.com/state-of-agent-engineering
[17] https://enterprisedna.co/resources/blog/practitioner-langchain-2026/
[18] https://developers.googleblog.com/en/agent-development-kit-easy-to-build-multi-agent-applications/
[19] https://developers.googleblog.com/en/agents-adk-agent-engine-a2a-enhancements-google-io/
[20] https://docs.cloud.google.com/vertex-ai/docs/release-notes
[21] https://docs.cloud.google.com/vertex-ai/docs/general/vertexai-security-controls
[22] https://cloud.google.com/vertex-ai/pricing
[23] https://www.zenml.io/blog/google-adk-vs-langgraph
[24] https://tinyagents.dev/vs/google-adk-vs-langchain
[25] https://www.agentmail.to/blog/best-ai-agent-frameworks-2026
[26] https://levelup.gitconnected.com/comparing-agent-frameworks-pydanticai-langchain-1-0-and-google-adk-4d2d46d927f0
[27] https://crewai.com/pricing
[28] https://github.com/crewAIInc/crewAI
[29] https://blog.crewai.com/crewai-amp-the-agent-management-platform/
[30] https://docs.crewai.com/en/concepts/llms
[31] https://docs.crewai.com/en/observability/overview
[32] https://techcrunch.com/2024/10/22/crewai-uses-third-party-models-to-automate-business-tasks/
[33] https://www.ibm.com/new/announcements/announcing-new-crewai-integration-with-watsonx-ai-to-build-and-streamline-workflows-with-multiple-ai-agents
[34] https://www.beri.net/tools/crewai
[35] https://aifoxx.com/trust/crewai
[36] https://trust.crewai.com/
[37] https://similarlabs.com/blog/crewai-review
[38] https://agentdaily.dev/content/6210ffb7-164d-4a8e-8c1f-98eca7c0841d
[39] https://www.reddit.com/r/AI_Agents/comments/1l6rw2n/whos_using_crewai_really/
[40] https://github.com/crewAIInc/crewAI/discussions/2404
[41] https://crewai.com/case-studies
[42] https://www.usagepricing.com/blueprint/crewai
[43] https://www.microsoft.com/en-us/copilot/pricing/copilot-studio
[44] https://learn.microsoft.com/en-us/microsoft-copilot-studio/fundamentals-what-is-copilot-studio
[45] https://learn.microsoft.com/en-us/microsoft-copilot-studio/requirements-messages-management
[46] https://www.microsoft.com/en-us/copilot/blog/copilot-studio/model-context-protocol-mcp-is-now-generally-available-in-microsoft-copilot-studio/
[47] https://www.microsoft.com/en-us/microsoft-cloud/blog/2025/05/07/empowering-multi-agent-apps-with-the-open-agent2agent-a2a-protocol/
[48] https://www.microsoft.com/en-us/copilot/blog/2025/05/19/introducing-microsoft-365-copilot-tuning-multi-agent-orchestration-and-more-from-microsoft-build-2025/
[49] https://learn.microsoft.com/en-us/microsoft-copilot-studio/security-and-governance
[50] https://techcommunity.microsoft.com/blog/microsoft-security-blog/announcing-new-microsoft-purview-capabilities-to-protect-genai-agents/4470696
[51] https://learn.microsoft.com/en-us/microsoft-copilot-studio/geo-data-residency
[52] https://learn.microsoft.com/en-us/microsoft-copilot-studio/computer-use
[53] https://www.microsoft.com/en-us/power-platform/blog/power-apps/unlock-new-levels-of-productivity-with-microsoft-dataverse-and-microsoft-copilot-studio-2/
[54] https://www.microsoft.com/en-us/power-platform/blog/power-apps/microsoft-recognized-as-a-leader-in-the-2025-gartner-magic-quadrant-for-enterprise-low-code-application-platforms/
[55] https://www.cloudzero.com/blog/copilot-studio-pricing/
[56] https://www.reddit.com/r/copilotstudio/comments/1ueqedl/woke_up_to_a_47k_bill_after_deploying_one_copilot/
[57] https://techcommunity.microsoft.com/blog/microsoft-security-blog/microsoft-copilot-studio-vs-microsoft-foundry-building-ai-agents-and-apps/4483160
[58] https://developers.openai.com/api/docs/pricing
[59] https://developers.openai.com/api/docs/deprecations
[60] https://developers.openai.com/api/docs/assistants/migration
[61] https://openai.com/index/introducing-chatgpt-enterprise/
[62] https://openai.com/index/new-tools-for-chatgpt-enterprise/
[63] https://openai.com/enterprise-privacy/
[64] https://openai.com/index/introducing-agentkit/
[65] https://techcrunch.com/2025/10/06/openai-launches-agentkit-to-help-developers-build-and-ship-ai-agents/
[66] https://openai.com/index/new-tools-for-building-agents/
[67] https://developers.googleblog.com/en/google-cloud-donates-a2a-to-linux-foundation/
[68] https://www.linuxfoundation.org/press/a2a-protocol-surpasses-150-organizations-lands-in-major-cloud-platforms-and-sees-enterprise-production-use-in-first-year
[69] https://langfuse.com/blog/2025-03-19-ai-agent-comparison
[70] https://www.firecrawl.dev/blog/best-open-source-agent-frameworks
