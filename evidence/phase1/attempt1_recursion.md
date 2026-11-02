## fireworks-glm (judge: anthropic)

| case | citation_validity | completeness | groundedness | has_citation | source_count_ok | sources_section | tool_recall | error |
|---|---|---|---|---|---|---|---|---|
| rag-vs-finetune | 1.00 | 0.80 | 0.75 | 1.00 | 1.00 | 1.00 | 1.00 |  |
| lang-graph | 1.00 | 1.00 | 0.50 | 1.00 | 1.00 | 1.00 | 1.00 |  |
| mcp | - | - | - | - | - | - | - | GraphRecursionError: Recursion limit of 100 reached without hitting a stop condition. You can increase the limit by setting the `recursion_limit` config key.
For troubleshooting, visit: https://docs.langchain.com/oss/python/langgraph/errors/GRAPH_RECURSION_LIMIT |
| prompt-cache | 1.00 | 0.95 | 0.45 | 1.00 | 1.00 | 1.00 | 1.00 |  |
| llm-judge | - | - | - | - | - | - | - | GraphRecursionError: Recursion limit of 100 reached without hitting a stop condition. You can increase the limit by setting the `recursion_limit` config key.
For troubleshooting, visit: https://docs.langchain.com/oss/python/langgraph/errors/GRAPH_RECURSION_LIMIT |
| agent-evals | - | - | - | - | - | - | - | GraphRecursionError: Recursion limit of 100 reached without hitting a stop condition. You can increase the limit by setting the `recursion_limit` config key.
For troubleshooting, visit: https://docs.langchain.com/oss/python/langgraph/errors/GRAPH_RECURSION_LIMIT |
| vector-db | 1.00 | 1.00 | 0.85 | 1.00 | 1.00 | 1.00 | 1.00 |  |
| guardrails | - | - | - | - | - | - | - | GraphRecursionError: Recursion limit of 100 reached without hitting a stop condition. You can increase the limit by setting the `recursion_limit` config key.
For troubleshooting, visit: https://docs.langchain.com/oss/python/langgraph/errors/GRAPH_RECURSION_LIMIT |
| context-eng | 0.86 | 1.00 | 0.88 | 1.00 | 1.00 | 1.00 | 1.00 |  |
| oss-models | - | - | - | - | - | - | - | GraphRecursionError: Recursion limit of 100 reached without hitting a stop condition. You can increase the limit by setting the `recursion_limit` config key.
For troubleshooting, visit: https://docs.langchain.com/oss/python/langgraph/errors/GRAPH_RECURSION_LIMIT |
| pgvector-hnsw | 1.00 | 0.98 | 0.80 | 1.00 | 1.00 | 1.00 | 1.00 |  |
| otel-genai | - | - | - | - | - | - | - | GraphRecursionError: Recursion limit of 100 reached without hitting a stop condition. You can increase the limit by setting the `recursion_limit` config key.
For troubleshooting, visit: https://docs.langchain.com/oss/python/langgraph/errors/GRAPH_RECURSION_LIMIT |
| react-pattern | - | - | - | - | - | - | - | GraphRecursionError: Recursion limit of 100 reached without hitting a stop condition. You can increase the limit by setting the `recursion_limit` config key.
For troubleshooting, visit: https://docs.langchain.com/oss/python/langgraph/errors/GRAPH_RECURSION_LIMIT |
| speculative-decoding | 1.00 | 0.97 | 0.60 | 1.00 | 1.00 | 1.00 | 1.00 |  |
| quantization | - | - | - | - | - | - | - | GraphRecursionError: Recursion limit of 100 reached without hitting a stop condition. You can increase the limit by setting the `recursion_limit` config key.
For troubleshooting, visit: https://docs.langchain.com/oss/python/langgraph/errors/GRAPH_RECURSION_LIMIT |
| structured-output | 1.00 | 1.00 | 0.35 | 1.00 | 1.00 | 1.00 | 1.00 |  |
| rag-eval | - | - | - | - | - | - | - | GraphRecursionError: Recursion limit of 100 reached without hitting a stop condition. You can increase the limit by setting the `recursion_limit` config key.
For troubleshooting, visit: https://docs.langchain.com/oss/python/langgraph/errors/GRAPH_RECURSION_LIMIT |
| agent-memory | - | - | - | - | - | - | - | empty report |
| pii-llm | 1.00 | 0.90 | 0.45 | 1.00 | 1.00 | 1.00 | 1.00 |  |
| model-routing | - | - | - | - | - | - | - | GraphRecursionError: Recursion limit of 100 reached without hitting a stop condition. You can increase the limit by setting the `recursion_limit` config key.
For troubleshooting, visit: https://docs.langchain.com/oss/python/langgraph/errors/GRAPH_RECURSION_LIMIT |
| mcp-false-premise | 1.00 | 1.00 | 0.88 | 1.00 | 1.00 | 1.00 | 1.00 |  |
| postgres-rls | - | - | - | - | - | - | - | GraphRecursionError: Recursion limit of 100 reached without hitting a stop condition. You can increase the limit by setting the `recursion_limit` config key.
For troubleshooting, visit: https://docs.langchain.com/oss/python/langgraph/errors/GRAPH_RECURSION_LIMIT |
| tokenization | 0.88 | 1.00 | 0.60 | 1.00 | 1.00 | 1.00 | 1.00 |  |
| moe | 1.00 | 0.90 | 0.60 | 1.00 | 1.00 | 1.00 | 1.00 |  |
| circuit-breaker | 0.83 | 1.00 | 0.92 | 1.00 | 1.00 | 1.00 | 1.00 |  |
| **mean** | 0.97 | 0.96 | 0.66 | 1.00 | 1.00 | 1.00 | 1.00 | |
