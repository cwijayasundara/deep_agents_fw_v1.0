from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any
from pathlib import Path

from agentkit_core import ModelRegistry, Settings, get_model
from agentkit_evals import LLMJudge, RunResult, aggregate, load_dataset, run_eval, to_markdown
from langchain_core.messages import HumanMessage

from .agent import build_research_agent, extract_report, load_config


async def evaluate(config_path: str, dataset: str, judge_entry: str) -> tuple[str, dict[str, Any]]:
    settings, cfg = Settings(), load_config(config_path)
    reg = ModelRegistry.default()
    judge = LLMJudge(get_model(reg.resolve(judge_entry, "strong"), settings))

    async def run_agent(question: str) -> RunResult:
        agent = build_research_agent(cfg, settings, registry=reg)
        res = await agent.ainvoke(
            {"messages": [HumanMessage(question)]}, config={"recursion_limit": 100}
        )
        tool_text = "\n".join(str(m.content) for m in res["messages"] if m.type == "tool")
        return RunResult(report=extract_report(res), retrieved=tool_text)

    results = await run_eval(load_dataset(dataset), run_agent, judge)
    md = f"## {cfg['model']} (judge: {judge_entry})\n\n{to_markdown(results)}\n"
    summary = {"config": cfg, "judge": judge_entry, "aggregate": aggregate(results)}
    return md, summary


def main() -> None:
    p = argparse.ArgumentParser(prog="research-eval")
    p.add_argument("--config", required=True)
    p.add_argument("--dataset", default="apps/research_agent/evals/smoke.jsonl")
    p.add_argument("--judge", default="anthropic", help="registry entry used as the judge model")
    p.add_argument("--out", type=Path, default=Path("eval_results.md"))
    a = p.parse_args()
    md, summary = asyncio.run(evaluate(a.config, a.dataset, a.judge))
    a.out.write_text(md)
    a.out.with_suffix(".json").write_text(json.dumps(summary, indent=2))
    print(md)
