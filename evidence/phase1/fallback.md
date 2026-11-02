# Fallback proof (live, fireworks only)

Script: `evidence/phase1/fallback_proof.py` (run from a scratch copy outside the repo). It loads the shipped
agent with `load_agent(DEFAULT_AGENT, model=init_chat_model("accounts/fireworks/models/does-not-exist", model_provider="fireworks", ...), overrides={"selection": "off"})`
and asks one short question. With selection off the tier cannot change, so any `glm-5p3` call comes from `model_fallback`.

```
$ UV_CONSTRAINT=constraints.txt uv run --no-sync python <scratchpad>/fallback_proof.py evidence/phase1
primary model: accounts/fireworks/models/does-not-exist
usage: 1 run, 4 model calls, input 23397 (cached 14392), output 839, decisions input 0
ledger rows: [{"tenant": "default", "thread_id": "6f8d4ca3-63fb-4bdd-9d91-84405f0caf81", "run_id": "ca91331a-93b8-4a95-9884-f91134edbe09", "model": "accounts/fireworks/models/does-not-exist,accounts/fireworks/models/glm-5p3", "input_tokens": 23397, "output_tokens": 839, "cached_input_tokens": 14392, "decisions_input_tokens": 0, "decisions_output_tokens": 0}]
report chars: 899
exit 0
```

stderr (full, 2026-11-02):

```
17:23:29 WARNING agentkit_config.load | <repo>/apps/research_agent/agent.yaml:subagents[0]: no response_schema; completion contract recommended
17:23:31 INFO  research_agent | orchestrator -> web_search 'Model Context Protocol Anthropic open standard'
17:23:34 WARNING agentkit_tools.duckduckgo | duckduckgo search 'Model Context Protocol Anthropic open standard' failed: DDGSException('No results found.')
17:23:34 WARNING agentkit_tools.langchain_tools | web_search 'Model Context Protocol Anthropic open standard' failed: search failed: DDGSException
17:23:34 INFO  research_agent | orchestrator <- web_search error (35 chars)
17:23:35 INFO  research_agent | orchestrator -> fetch_url https://modelcontextprotocol.io/introduction
17:23:36 INFO  research_agent | orchestrator <- fetch_url ok (20150 chars)
17:23:41 INFO  research_agent | orchestrator -> write_file /report.md
17:23:41 INFO  research_agent | orchestrator <- write_file ok (23 chars)
17:23:46 INFO  research_agent | orchestrator says: The Model Context Protocol (MCP) is an open-source standard for connecting AI applications to external systems, often described as a "USB-C port" for AI apps […
17:23:46 INFO  research_agent | agent finished in 17.5s
```

Ledger row: `fallback_ledger.json`. Report: `fallback_report.md`.
