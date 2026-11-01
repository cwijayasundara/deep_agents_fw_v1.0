from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from agentkit_core import Settings
from langchain_core.messages import HumanMessage

from .agent import build_research_agent, extract_report, load_config


async def run(question: str, config_path: str) -> str:
    agent = build_research_agent(load_config(config_path), Settings())
    result = await agent.ainvoke(
        {"messages": [HumanMessage(question)]}, config={"recursion_limit": 100}
    )
    report = extract_report(result)
    if not report:
        raise SystemExit("agent finished without writing /report.md")
    return report


def main() -> None:
    p = argparse.ArgumentParser(prog="research")
    p.add_argument("question")
    p.add_argument("--config", default="apps/research_agent/config/anthropic.yaml")
    p.add_argument("--out", type=Path, default=Path("report.md"))
    a = p.parse_args()
    a.out.write_text(asyncio.run(run(a.question, a.config)))
    print(f"wrote {a.out}")
