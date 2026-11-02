"""Phase 1 fallback proof: a primary model that does not exist must fall back to glm-5p3.

Run from the repo root: uv run python <this file> <evidence dir>
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path

from agentkit_config import load_agent, read_output
from agentkit_core import Provider, Settings
from agentkit_deep import agent_prompt_hash
from agentkit_telemetry import CostLedger, run_config
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage
from research_agent.agent import DEFAULT_AGENT, new_thread, platform_context
from research_agent.progress import run_with_progress, setup_logging

BROKEN = "accounts/fireworks/models/does-not-exist"
QUESTION = "In two sentences, what is the Model Context Protocol? Cite one source."


async def main(out: Path) -> None:
    settings = Settings()
    primary = init_chat_model(
        BROKEN, model_provider="fireworks", api_key=settings.require_key(Provider.FIREWORKS)
    )
    loaded = load_agent(
        DEFAULT_AGENT, settings=settings, model=primary, overrides={"selection": "off"}
    )
    print(f"primary model: {BROKEN}", flush=True)
    ctx = platform_context(loaded.spec, tenant="default", user="local", thread=new_thread())
    ledger = CostLedger()
    config = run_config(ctx, agent_prompt_hash(loaded.graph), ledger)
    res = await run_with_progress(
        loaded.graph, {"messages": [HumanMessage(QUESTION)]}, config=dict(config), context=ctx
    )
    report = read_output(res, loaded.spec.output) or ""
    print(ledger.summary())
    rows = [{k: str(v) if k == "run_id" else v for k, v in asdict(r).items()} for r in ledger.rows]
    (out / "fallback_ledger.json").write_text(json.dumps(rows, indent=2, default=str))
    (out / "fallback_report.md").write_text(report)
    print(f"ledger rows: {json.dumps(rows, default=str)}")
    print(f"report chars: {len(report)}")
    if not report:
        raise SystemExit("no report")


if __name__ == "__main__":
    setup_logging(0)
    logging.getLogger("research_agent").setLevel(logging.INFO)
    asyncio.run(main(Path(sys.argv[1])))
