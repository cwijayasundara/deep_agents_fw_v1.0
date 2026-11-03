# Web search provider: replace DuckDuckGo as the default

Date: 2026-11-03. Status: implemented 2026-11-03 (backends, `auto` chain, cache, empty-result fix); golden-set provider comparison still open. Prices are vendor list prices, not independently verified.

## Problem

`web_search` defaults to `backend: duckduckgo` (`packages/agentkit-tools/src/agentkit_tools/factories.py`).
`DuckDuckGoSearch` uses `ddgs` 9.16.1, which scrapes `html.duckduckgo.com`. It has no API contract or SLA,
and it runs a sync client in `asyncio.to_thread`.

The evidence logs show it fails often:

| Log | Searches | Failed |
|---|---|---|
| `evidence/phase1b/golden/golden_gate.stderr.log` | ~238 | 86 (61 `No results found`, 25 timeouts) |
| `evidence/verify/20261102-proof1/{turn1,eval}.stderr.log` | ~12 | 5 |
| `evidence/verify/20261102-phase1b/turn1.stderr.log` | ~4 | 1 |
| `evidence/declarative/glm-ddg.log` | ~5 | 2 |

That is about 36% failed. The `No results found` failures are on plainly answerable queries, which means DDG
is blocking the bot rather than finding nothing. The agent sees `ERROR: search failed: DDGSException`. It then
rephrases and burns its `web_search` `run_limit: 20` budget.

## Options

| Provider | $ / 1k searches | Free | Limits / latency | Notes |
|---|---|---|---|---|
| Parallel (turbo/fast) | $1 (10 results) | ~5k/month + up to $80 at signup | 600 rpm; ~200-700 ms | Returns excerpts sized for LLMs |
| DeepSeek Search | $0.75; failed, empty and timed-out calls not billed | none general | 100 QPS (fetch 25 QPS) | Launched 2026-10-17/18. Up to 50 results, optional summary and full content. Also a `/v1/tools/fetch` endpoint at the same price. Queries limited to 128 chars. Says nothing about data retention; China-based. |
| Brave | $5 | $5 credit/month | 50 QPS; ~670 ms | Own index; ZDR on Enterprise; storing results needs a storage-rights plan |
| Tavily (already wired) | ~$8 | 1k credits/month | n/a | Config change only (`TAVILY_API_KEY`) |
| Exa | $7 + contents | $10/month | n/a | Neural search |

Cheaper SERP options exist but were not evaluated. Serper costs about $0.30-1.00/1k and returns Google results.
Ceramic via the Cloudflare gateway costs $0.25/1k, a figure seen only in one comparison article.

Price is not the deciding factor. A research turn makes about 5-7 searches, against about 22k+ model tokens.
A full golden run costs about $0.18 on DeepSeek and about $1.19 on Brave.

## Recommendation

1. Make **Parallel** the primary backend. At current volume it stays inside the free tier, so it costs $0.
   It is fast and avoids DeepSeek's data-residency question. DeepSeek only becomes cheaper above about 20k
   searches/month.
2. Add **Brave** as an automatic fallback: a `FallbackSearch` that tries the next backend on `ToolError` or 429.
3. Keep **DuckDuckGo** only as a keyless dev option, never the default.
4. Revisit **DeepSeek** if volume passes about 20k/month, or if its `need_content` option proves it can replace
   many `fetch_url` calls. If adopted, truncate queries to 128 chars: 85 of about 3,000 logged agent queries are
   longer, up to 339 chars.

## Small fixes regardless of provider

- Return an empty result as `No results.` instead of raising a `ToolError`.
- Add a per-run query cache. The eval logs contain 55 duplicated queries.

## Implementation sketch

Each backend is about a 30-line class implementing the `SearchTool` protocol (`models.py`). Add it to
`BACKENDS`/`web_search` in `factories.py`, and add keys to settings (`PARALLEL_API_KEY`, `BRAVE_API_KEY`,
optionally `DEEPSEEK_API_KEY`). Before switching the default, run the research golden set (`golden.jsonl`) with
DDG, Parallel, Brave and DeepSeek. Compare failure rate, groundedness, latency and tokens.

## Sources

- DeepSeek Search guide: https://api-docs.deepseek.com/guides/search
- TechNode launch coverage: https://technode.com/2026/10/19/deepseek-launches-web-search-and-page-fetching-apis-for-ai-agents/
- LiteLLM DeepSeek search: https://docs.litellm.ai/docs/search/deepseek.md
- Parallel pricing: https://parallel.ai/pricing
- Brave Search API: https://brave.com/search/api/
- Tavily pricing: https://www.tavily.com/pricing
- Exa pricing: https://exa.ai/pricing
- Comparison (vendor-written): https://parallel.ai/articles/the-honest-2026-comparison-web-search-apis-for-ai-agents
