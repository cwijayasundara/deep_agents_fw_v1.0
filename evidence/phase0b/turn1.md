# What Is the Model Context Protocol (MCP)?

The **Model Context Protocol (MCP)** is an open-source standard for connecting AI applications to external systems — data sources, tools, and workflows. It was introduced and open-sourced by Anthropic on November 25, 2024, and was created at Anthropic by David Soria Parra and Justin Spahr-Summers [1][2]. The official documentation offers a simple analogy: "Think of MCP like a USB-C port for AI applications" — just as USB-C standardizes how devices connect to peripherals, MCP standardizes how AI applications like Claude or ChatGPT connect to external systems such as local files, databases, search engines, and specialized prompt workflows [2].

## The problem it solves

Before MCP, even the most sophisticated AI models were "constrained by their isolation from data—trapped behind information silos and legacy systems," and every new data source required its own custom implementation, making connected systems difficult to scale [1]. MCP replaces those fragmented, point-to-point integrations with a single universal protocol. Analysts describe this as collapsing an N×M integration problem (N AI models × M data sources, each pair needing a custom connector) into N + M: each AI client implements MCP once, each data source implements MCP once, and any client can reach any server [5].

## How it works: architecture

MCP follows a client–server architecture built on JSON-RPC 2.0 messaging, with three participants [1][3]:

- **MCP Host** — the AI application the user interacts with (e.g., Claude Desktop, Claude Code, Visual Studio Code). It coordinates one or more MCP clients [3].
- **MCP Client** — a component inside the host that maintains a dedicated connection to one MCP server and obtains context from it. A host creates one client per server it connects to [3].
- **MCP Server** — a program that exposes context and capabilities to clients. Servers can run locally (typically over the stdio transport) or remotely (over the Streamable HTTP transport) [1][3].

The protocol is organized into two layers [3]:

1. **Data layer** — a JSON-RPC 2.0-based protocol defining message structure and semantics, including capability/version discovery, core primitives (tools, resources, prompts), notifications, and progress tracking. Notably, as of the 2026-07-28 protocol version, MCP is a *stateless* protocol: each request carries protocol version and capability metadata, and servers advertise their capabilities via a mandatory `server/discover` request [3].
2. **Transport layer** — the communication mechanisms: **stdio** (standard input/output streams for local process communication) and **Streamable HTTP** (HTTP POST with optional Server-Sent Events for streaming, with authentication via OAuth, bearer tokens, or API keys) [3].

## Core primitives

MCP servers expose three core primitives to clients [3][5]:

- **Tools** — executable functions an AI application can invoke to perform actions (e.g., file operations, API calls, database queries), invoked via `tools/call` [3].
- **Resources** — data sources that provide contextual information to the AI application (e.g., file contents, database records, API responses) [3].
- **Prompts** — reusable templates that structure interactions with language models (e.g., system prompts, few-shot examples) [3].

Clients discover these dynamically at runtime via `*/list` methods (e.g., `tools/list`) before invoking them, so listings can change over time [3]. Clients can also expose capabilities to servers: **elicitation** lets a server request additional input or confirmation from the user, while **sampling** (allowing servers to request LLM completions from the client's application) and **logging** are deprecated as of protocol version 2026-07-28 [3]. Optional extensions build on the core protocol, such as the Tasks extension for long-running operations [3].

MCP focuses solely on the protocol for context exchange — it does not dictate how AI applications use LLMs or manage the provided context [3]. It also does not replace REST APIs: MCP servers typically call REST APIs internally, adding AI-friendly discovery, session management, and standardized auth on top [5].

## Adoption and ecosystem

At MCP's one-year mark (December 2025), Anthropic reported more than 10,000 active public MCP servers, 97M+ monthly SDK downloads across Python and TypeScript, and adoption by ChatGPT, Cursor, Gemini, Microsoft Copilot, and Visual Studio Code, with enterprise deployment support from AWS, Cloudflare, Google Cloud, and Microsoft Azure [4]. (Note: these figures are vendor-reported by Anthropic.) The docs list Claude, ChatGPT, VS Code, Cursor, and MCPJam among supporting clients [2]. At launch, early adopters included Block and Apollo, with development-tool companies Zed, Replit, Codeium, and Sourcegraph building MCP support; Anthropic also shipped pre-built servers for systems like Google Drive, Slack, GitHub, Git, Postgres, and Puppeteer [1].

## Governance and current status

On December 9, 2025, Anthropic donated MCP to the **Agentic AI Foundation (AAIF)**, a directed fund under the Linux Foundation co-founded by Anthropic, Block, and OpenAI, with support from Google, Microsoft, AWS, Cloudflare, and Bloomberg. MCP joined Block's goose and OpenAI's AGENTS.md as founding projects, with its maintainer governance model unchanged — moving the protocol under vendor-neutral, community-driven stewardship [4]. The project also now has an official community-driven registry for discovering MCP servers [4].

## In one sentence

MCP is the open, USB-C-like standard — created by Anthropic and now stewarded by the Linux Foundation's Agentic AI Foundation — that lets any AI application plug into any compliant data source or tool through one standardized protocol instead of a bespoke integration for each pairing [1][2][4].

---

## Sources

[1] https://www.anthropic.com/news/model-context-protocol
[2] https://modelcontextprotocol.io/docs/2026-07-28/getting-started/intro
[3] https://modelcontextprotocol.io/docs/2026-07-28/learn/architecture
[4] https://www.anthropic.com/news/donating-the-model-context-protocol-and-establishing-of-the-agentic-ai-foundation
[5] https://atlan.com/know/what-is-model-context-protocol/
