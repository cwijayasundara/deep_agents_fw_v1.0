from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from agentkit_core import ModelRegistry, Settings, get_model
from agentkit_evals import LLMJudge, RunResult, aggregate, load_dataset, run_eval, to_markdown
from langchain_core.messages import HumanMessage

from .agent import build_research_agent, extract_report, load_config
from .progress import run_with_progress, setup_logging

log = logging.getLogger("research_agent")


async def evaluate(config_path: str, dataset: str, judge_entry: str) -> tuple[str, dict[str, Any]]:
    settings, cfg = Settings(), load_config(config_path)
    reg = ModelRegistry.default()
    judge = LLMJudge(get_model(reg.resolve(judge_entry, "strong"), settings))

    async def run_agent(question: str) -> RunResult:
        log.info("eval question: %s", question)
        agent = build_research_agent(cfg, settings, registry=reg)
        seen: list[str] = []  # every tool result, orchestrator and subagents
        res = await run_with_progress(
            agent,
            {"messages": [HumanMessage(question)]},
            config={"recursion_limit": 100},
            tool_outputs=seen,
        )
        return RunResult(report=extract_report(res), retrieved="\n".join(seen))

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
    p.add_argument("-v", "--verbose", action="store_true", help="debug logs (tool output, tokens)")
    p.add_argument("-q", "--quiet", action="store_true", help="warnings only")
    a = p.parse_args()
    setup_logging(-1 if a.quiet else 1 if a.verbose else 0)
    md, summary = asyncio.run(evaluate(a.config, a.dataset, a.judge))
    a.out.write_text(md)
    a.out.with_suffix(".json").write_text(json.dumps(summary, indent=2))
    print(md)
