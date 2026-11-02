from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from agentkit_core import ModelRegistry, Settings
from langchain_core.messages import HumanMessage

from .agent import build_research_agent, extract_report, load_config
from .progress import run_with_progress, setup_logging

DEFAULT_CONFIG = "apps/research_agent/config/fireworks-glm.yaml"

log = logging.getLogger("research_agent")


async def run(question: str, config_path: str) -> str:
    settings = Settings()
    cfg = load_config(config_path)
    spec = ModelRegistry.default().resolve(cfg["model"], cfg["tier"])
    log.info("env file: %s", settings.env_file_used() or "none found (using process env)")
    log.info("keys set: %s", ", ".join(settings.keys_present()) or "none")
    log.info(
        "config %s -> %s %s (tier=%s, selection=%s)",
        config_path,
        spec.provider,
        spec.model_id,
        cfg["tier"],
        cfg.get("selection", "off"),
    )
    log.info("question: %s", question)
    agent = build_research_agent(cfg, settings)
    result = await run_with_progress(
        agent, {"messages": [HumanMessage(question)]}, config={"recursion_limit": 100}
    )
    report = extract_report(result)
    if not report:
        raise SystemExit("agent finished without writing /report.md")
    return report


def main() -> None:
    p = argparse.ArgumentParser(prog="research")
    p.add_argument("question")
    p.add_argument("--config", default=DEFAULT_CONFIG)
    p.add_argument("--out", type=Path, default=Path("report.md"))
    p.add_argument("-v", "--verbose", action="store_true", help="debug logs (tool output, tokens)")
    p.add_argument("-q", "--quiet", action="store_true", help="warnings only")
    a = p.parse_args()
    setup_logging(-1 if a.quiet else 1 if a.verbose else 0)
    report = asyncio.run(run(a.question, a.config))
    a.out.write_text(report)
    log.info("wrote %s (%d chars)", a.out, len(report))
    print(f"wrote {a.out}")
