from __future__ import annotations

import argparse
import asyncio
import json
import logging
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from agentkit_config import load_agent, read_output
from agentkit_core import ModelRegistry, Settings, get_model
from agentkit_evals import LLMJudge, RunResult, aggregate, load_dataset, run_eval, to_markdown
from langchain_core.messages import HumanMessage

from .agent import add_agent_args, overrides_from
from .progress import run_with_progress, setup_logging

log = logging.getLogger("research_agent")


async def evaluate(
    agent_path: str | Path, overrides: Mapping[str, str], dataset: str, judge_entry: str
) -> tuple[str, dict[str, Any]]:
    settings = Settings()
    judge = LLMJudge(get_model(ModelRegistry.default().resolve(judge_entry, "strong"), settings))
    first = load_agent(agent_path, settings=settings, overrides=overrides)  # fail fast on bad specs
    spec = first.model_spec
    log.info(
        "agent %s -> %s %s (tier=%s, selection=%s)",
        agent_path,
        spec.provider,
        spec.model_id,
        first.spec.tier,
        first.spec.selection or "off",
    )

    async def run_agent(question: str) -> RunResult:
        log.info("eval question: %s", question)
        loaded = load_agent(agent_path, settings=settings, overrides=overrides)
        seen: list[str] = []  # every tool result, orchestrator and subagents
        res = await run_with_progress(
            loaded.graph,
            {"messages": [HumanMessage(question)]},
            config={"recursion_limit": 100},
            tool_outputs=seen,
        )
        return RunResult(report=read_output(res, loaded.spec.output), retrieved="\n".join(seen))

    results = await run_eval(load_dataset(dataset), run_agent, judge)
    md = f"## {first.spec.model} (judge: {judge_entry})\n\n{to_markdown(results)}\n"
    summary = {
        "agent": str(agent_path),
        "overrides": dict(overrides),
        "model": first.spec.model,
        "tier": first.spec.tier,
        "selection": first.spec.selection,
        "judge": judge_entry,
        "aggregate": aggregate(results),
    }
    return md, summary


def main() -> None:
    p = argparse.ArgumentParser(prog="research-eval")
    add_agent_args(p)
    p.add_argument("--dataset", default="apps/research_agent/evals/smoke.jsonl")
    p.add_argument("--judge", default="anthropic", help="registry entry used as the judge model")
    p.add_argument("--out", type=Path, default=Path("eval_results.md"))
    p.add_argument("-v", "--verbose", action="store_true", help="debug logs (tool output, tokens)")
    p.add_argument("-q", "--quiet", action="store_true", help="warnings only")
    a = p.parse_args()
    setup_logging(-1 if a.quiet else 1 if a.verbose else 0)
    md, summary = asyncio.run(evaluate(a.agent, overrides_from(a), a.dataset, a.judge))
    a.out.write_text(md)
    a.out.with_suffix(".json").write_text(json.dumps(summary, indent=2))
    print(md)
