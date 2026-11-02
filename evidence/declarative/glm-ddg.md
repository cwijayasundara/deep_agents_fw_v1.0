# What Is the Model Context Protocol (MCP)?

The **Model Context Protocol (MCP)** is an open-source standard for connecting AI applications to external systems — data sources (e.g., local files, databases), tools (e.g., search engines, calculators), and workflows (e.g., specialized prompts). It was created by Anthropic and open-sourced in November 2024, and is often described as "a USB-C port for AI applications": just as USB-C standardizes how physical devices connect, MCP standardizes how AI applications connect to the systems around them [1][2][3].

## The problem it solves

Before MCP, connecting an AI assistant to each new data source or tool required a custom, bespoke integration, making connected systems difficult to scale. Anthropic's announcement framed the problem as even sophisticated models being "trapped behind information silos and legacy systems," and positioned MCP as "a universal, open standard for connecting AI systems with data sources, replacing fragmented integrations with a single protocol" [2]. In practice, this means developers build against one standard protocol rather than maintaining separate connectors for every data source, and AI applications can keep context as they move between tools and datasets [2].

## How it works

MCP follows a **client–server architecture** with three participants [4]:

- **MCP Host** — the AI application (e.g., Claude Desktop, Claude Code, Visual Studio Code) that coordinates one or more clients.
- **MCP Client** — a component the host creates to maintain a dedicated connection with one MCP server and obtain context from it.
- **MCP Server** — a program (local or remote) that provides context to clients. For example, VS Code acts as a host that instantiates one client for a Sentry server and another for a filesystem server [4].

The protocol has two layers [4]:

1. **Data layer** — a [JSON-RPC 2.0](https://www.jsonrpc.org)–based protocol defining message structure and semantics, including capability/version discovery and the core primitives. As of the 2026-07-28 specification, MCP is stateless: every request carries the protocol version and capabilities in a `_meta` field, and clients can learn a server's capabilities via a `server/discover` request [4].
2. **Transport layer** — the communication channels and authentication. Two transports are supported: **stdio** (standard input/output streams for local processes on the same machine) and **Streamable HTTP** (HTTP POST with optional Server-Sent Events for remote servers, with OAuth recommended for authentication) [4].

### Core primitives

Servers expose three core primitives to clients [4]:

- **Tools** — executable functions the AI can invoke to perform actions (file operations, API calls, database queries), discovered via `tools/list` and invoked via `tools/call`.
- **Resources** — data sources that provide contextual information (file contents, database records, API responses).
- **Prompts** — reusable templates that structure interactions with language models (system prompts, few-shot examples).

Clients can also expose primitives, notably **elicitation**, which lets a server request additional input or confirmation from the user. (The previously supported client-side **sampling** and **logging** primitives are deprecated as of protocol version 2026-07-28.) The protocol also supports real-time notifications — e.g., a server can notify clients when its tool list changes — and optional extensions such as Tasks for long-running operations [4].

## Who created it and where it stands

MCP was created at Anthropic by David Soria Parra and Justin Spahr-Summers [2]. Anthropic launched it with a specification and SDKs, local MCP server support in Claude Desktop, and pre-built servers for systems like Google Drive, Slack, GitHub, Git, Postgres, and Puppeteer; early adopters included Block and Apollo, with Zed, Replit, Codeium, and Sourcegraph integrating it into their development tools [2].

Adoption grew quickly. By December 2025 — one year after launch — Anthropic reported more than 10,000 active public MCP servers, adoption by ChatGPT, Cursor, Gemini, Microsoft Copilot, and Visual Studio Code, and 97M+ monthly SDK downloads across Python and TypeScript [5]. The Linux Foundation likewise credited MCP with becoming "the universal standard protocol for connecting AI models to tools, data and applications" [6].

**Governance:** On December 9, 2025, Anthropic donated MCP to the **Agentic AI Foundation (AAIF)**, a directed fund under the Linux Foundation co-founded by Anthropic, Block, and OpenAI, with support from Google, Microsoft, AWS, Cloudflare, and Bloomberg. MCP became a founding AAIF project alongside Block's goose and OpenAI's AGENTS.md, ensuring the standard remains open, neutral, and community-driven [5][6]. The protocol is now stewarded under Linux Foundation governance [5][6].

## Typical use cases

Examples cited in the official documentation include: agents accessing Google Calendar and Notion as personalized assistants; Claude Code generating a web app from a Figma design; enterprise chatbots querying multiple databases across an organization via chat; and AI models creating 3D designs in Blender and printing them on a 3D printer [1].

---

### Sources

[1] https://modelcontextprotocol.io/docs/2026-07-28/getting-started/intro — "What is the Model Context Protocol (MCP)?" (official MCP documentation, latest version 2026-07-28)
[2] https://www.anthropic.com/news/model-context-protocol — "Introducing the Model Context Protocol" (Anthropic, Nov 25, 2024)
[3] https://en.wikipedia.org/wiki/Model_Context_Protocol — Wikipedia: Model Context Protocol (corroborating Nov 2024 introduction by Anthropic)
[4] https://modelcontextprotocol.io/docs/2026-07-28/learn/architecture — "Architecture overview" (official MCP documentation, 2026-07-28 version)
[5] https://www.anthropic.com/news/donating-the-model-context-protocol-and-establishing-of-the-agentic-ai-foundation — "Donating the Model Context Protocol and establishing the Agentic AI Foundation" (Anthropic, Dec 9, 2025)
[6] https://www.linuxfoundation.org/press/linux-foundation-announces-the-formation-of-the-agentic-ai-foundation — "Linux Foundation Announces the Formation of the Agentic AI Foundation (AAIF)" (Dec 9, 2025)
