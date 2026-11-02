# What is the Model Context Protocol (MCP)?

The **Model Context Protocol (MCP)** is an open-source standard for connecting AI applications to external systems — data sources (local files, databases), tools (search engines, calculators) and workflows (specialized prompts) — so that applications like Claude or ChatGPT can access key information and perform tasks [2]. It is often described as "a USB-C port for AI applications": just as USB-C standardizes how devices connect to peripherals, MCP standardizes how AI applications connect to external systems [2].

## Origin and purpose

MCP was created at Anthropic by David Soria Parra and Justin Spahr-Summers and open-sourced on November 25, 2024 [1]. The problem it addresses is that even sophisticated models are "trapped behind information silos and legacy systems," and every new data source historically required its own custom integration, making connected systems hard to scale [1]. MCP replaces that fragmentation with a single universal protocol: instead of maintaining separate connectors for each data source, developers build against one standard [1]. At launch, Anthropic released the specification and SDKs, local MCP server support in Claude Desktop, and an open-source repository of pre-built servers (e.g., Google Drive, Slack, GitHub, Git, Postgres, Puppeteer), with early adopters including Block and Apollo and tooling companies Zed, Replit, Codeium, and Sourcegraph [1].

## How it works

MCP uses a **client–server architecture** with three participants [3]:

- **MCP Host** — the AI application (e.g., Claude Desktop, Claude Code, Visual Studio Code) that coordinates one or more MCP clients.
- **MCP Client** — a component that maintains a dedicated connection to one MCP server and obtains context from it for the host.
- **MCP Server** — a program that provides context; it may run locally (typically over STDIO) or remotely (typically over Streamable HTTP) [3].

The protocol is organized in two layers [3]:

1. **Data layer** — a JSON-RPC 2.0 based protocol defining message structure and semantics, capability/version discovery, and core primitives. MCP is a stateless protocol in which every request carries protocol version and capabilities metadata, and servers advertise their versions and capabilities through a mandatory `server/discover` request [3].
2. **Transport layer** — the communication mechanisms: **stdio** (standard input/output streams for local processes) and **Streamable HTTP** (HTTP POST for client-to-server messages, with optional Server-Sent Events for streaming; OAuth is the recommended authentication approach) [3].

Servers expose three core **primitives** [3]:

- **Tools** — executable functions an AI application can invoke to perform actions (file operations, API calls, database queries).
- **Resources** — data sources that provide contextual information (file contents, database records, API responses).
- **Prompts** — reusable templates that structure interactions with language models (system prompts, few-shot examples).

Each primitive has discovery methods (`*/list`), retrieval (`*/get`), and, for tools, execution (`tools/call`), so clients can dynamically discover what a server offers [3]. Clients can also expose primitives back to servers — notably **elicitation**, which lets a server request additional input or confirmation from the user (as of the 2026-07-28 protocol revision, the older client primitives *sampling* and *logging* are deprecated) [3]. The protocol also supports real-time notifications (e.g., a server notifying clients that its tool list changed) and optional extensions such as Tasks for long-running operations [3].

## Governance and ecosystem

MCP is no longer governed solely by Anthropic: the project is established as "Model Context Protocol, a Series of LF Projects, LLC" (a Linux Foundation–governed project), with code and specifications under Apache License 2.0, documentation under CC BY 4.0, and a hierarchical, merit-based governance structure (Lead Maintainers acting as BDFL, Core Maintainers, Working Groups, and a Specification Enhancement Proposal process) [4]. Its current Lead Maintainers are David Soria Parra and Den Delimarsky [4].

Adoption is broad: MCP clients include AI assistants like Claude and ChatGPT and development tools like Visual Studio Code, Cursor, and MCPJam [2]. Six Tier 1 SDKs exist — TypeScript, Python, C#, Go, Rust, and recently Ruby [5] — and as of the July 28, 2026 specification release, the project reported close to half a billion SDK downloads per month, with the TypeScript and Python SDKs each surpassing 1 billion total downloads [5].

## In short

MCP is the open, JSON-RPC–based standard that lets any AI application plug into any compliant data source or tool through a common client–server interface, eliminating bespoke point-to-point integrations [1][2][3]. It originated at Anthropic in November 2024 [1] and is now a community-governed Linux Foundation project with wide industry adoption [4][5].

*Note on sourcing:* web search was unavailable during research, so the specific announcement dates of third-party adoptions (e.g., OpenAI's and Google DeepMind's 2025 endorsements) could not be independently verified; the adoption claims above come from the MCP project's own documentation and blog.

## Sources

1. https://www.anthropic.com/news/model-context-protocol — Anthropic, "Introducing the Model Context Protocol" (Nov 25, 2024)
2. https://modelcontextprotocol.io/docs/getting-started/intro — "What is the Model Context Protocol (MCP)?", official MCP docs
3. https://modelcontextprotocol.io/docs/learn/architecture — "Architecture overview", official MCP docs
4. https://modelcontextprotocol.io/community/governance — "Governance and Stewardship", official MCP docs
5. https://blog.modelcontextprotocol.io/ — Model Context Protocol Blog (2026-07-28 spec release; SDK download figures; Ruby Tier 1 SDK)
