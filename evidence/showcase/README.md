# Showcase replay fixture

One real research-agent run, recorded live and converted to `replay.json`.

- Run id: 20261107-201555 (throwaway tenant `verify-20261107-201555`, torn down after collecting evidence)
- Date: 2026-11-07
- Model: fireworks-glm (glm-5p3 / glm-5p3-flash tiers)
- Agent: `evidence/showcase/agent-demo.yaml` (the shipped research agent with `web_search` `run_limit: 4`, so the call limit trips)
- Question: Compare today's agentic AI platforms (LangChain/LangSmith, Google ADK, CrewAI, Microsoft Copilot Studio, OpenAI) for an enterprise team. Send follow-ups to demo.buyer@example.com.
- Recorded with span payloads on (`AGENTKIT_TRACE_PAYLOADS=1`), needed to see the PII mask and the limit message.
- Command: `AGENTKIT_TRACE_PAYLOADS=1 .claude/skills/verify-agentkit/scripts/drive_research.sh 20261107-201555 demo1 "<question>" --agent evidence/showcase/agent-demo.yaml`
- Convert: `uv run python -m showcase.replay <spans.jsonl> <usage.json> > evidence/showcase/replay.json` (run from `scripts/`)
- First attempt triggered both a `pii` and a `limit` event; no re-run or steering was needed. Cost is 0.0 because the usage ledger holds token counts only.
