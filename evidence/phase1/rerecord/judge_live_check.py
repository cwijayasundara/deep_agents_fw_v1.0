import asyncio, warnings
from agentkit_core import ModelRegistry, Settings, get_model
from agentkit_evals import EvalCase, LLMJudge
warnings.simplefilter("error", UserWarning)
s = Settings(); spec = ModelRegistry.default().resolve("anthropic", "strong")
j = LLMJudge(get_model(spec, s))
case = EvalCase(id="x", question="What is MCP?", must_cover=["standard protocol"])
rep = "MCP is an open standard protocol connecting LLM apps to tools [1].\n\n## Sources\n[1] https://modelcontextprotocol.io"
print(spec.model_id, asyncio.run(j(case, rep, "The Model Context Protocol is an open standard protocol for tools.")))
