from __future__ import annotations

import argparse
import asyncio
import logging
from collections.abc import Mapping
from pathlib import Path

from agentkit_config import load_agent, read_output
from agentkit_core import Settings
from langchain_core.messages import HumanMessage

from .agent import add_agent_args, exit_on_spec_errors, overrides_from
from .progress import run_with_progress, setup_logging

log = logging.getLogger("research_agent")


async def run(question: str, agent_path: str | Path, overrides: Mapping[str, str]) -> str:
    settings = Settings()
    log.info("env file: %s", settings.env_file_used() or "none found (using process env)")
    log.info("keys set: %s", ", ".join(settings.keys_present()) or "none")
    loaded = load_agent(agent_path, settings=settings, overrides=overrides)
    spec = loaded.model_spec
    log.info(
        "agent %s -> %s %s (tier=%s, selection=%s)",
        agent_path,
        spec.provider,
        spec.model_id,
        loaded.spec.tier,
        loaded.spec.selection or "off",
    )
    log.info("question: %s", question)
    result = await run_with_progress(
        loaded.graph, {"messages": [HumanMessage(question)]}, config={"recursion_limit": 100}
    )
    report = read_output(result, loaded.spec.output)
    if not report:
        raise SystemExit("agent finished without writing /report.md")
    return report


def _main() -> None:
    p = argparse.ArgumentParser(prog="research")
    p.add_argument("question")
    add_agent_args(p)
    p.add_argument("--out", type=Path, default=Path("report.md"))
    p.add_argument("-v", "--verbose", action="store_true", help="debug logs (tool output, tokens)")
    p.add_argument("-q", "--quiet", action="store_true", help="warnings only")
    a = p.parse_args()
    setup_logging(-1 if a.quiet else 1 if a.verbose else 0)
    report = asyncio.run(run(a.question, a.agent, overrides_from(a)))
    a.out.write_text(report)
    log.info("wrote %s (%d chars)", a.out, len(report))
    print(f"wrote {a.out}")


def main() -> None:
    exit_on_spec_errors(_main)
