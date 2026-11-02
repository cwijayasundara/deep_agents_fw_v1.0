"""Opt-in end-to-end run against real providers: `uv run pytest -m live`.

Set RESEARCH_LIVE_CONFIGS (comma-separated config names, default 'anthropic') and the matching
provider key plus TAVILY_API_KEY.
"""

import os
from pathlib import Path

import pytest
from agentkit_core import Settings
from agentkit_evals import extract_urls
from langchain_core.messages import HumanMessage
from research_agent import build_research_agent, extract_report, load_config

CFG_DIR = Path(__file__).parents[1] / "config"
NAMES = os.environ.get("RESEARCH_LIVE_CONFIGS", "anthropic").split(",")
PRESENT = set(Settings().keys_present())  # reads .env like the CLIs do


@pytest.mark.live
@pytest.mark.parametrize("name", NAMES)
async def test_full_research_run(name):
    if "TAVILY_API_KEY" not in PRESENT:
        pytest.skip("TAVILY_API_KEY not set")
    cfg = load_config(CFG_DIR / f"{name}.yaml")
    if cfg.get("selection") and "OPENAI_API_KEY" not in PRESENT:
        pytest.skip("OPENAI_API_KEY not set (needed for Decisions selection)")
    agent = build_research_agent(cfg, Settings())
    out = await agent.ainvoke(
        {"messages": [HumanMessage("What is the Model Context Protocol? Keep it short.")]},
        config={"recursion_limit": 100},
    )
    report = extract_report(out)
    assert report, "agent did not write /report.md"
    retrieved = "\n".join(str(m.content) for m in out["messages"] if m.type == "tool")
    cited = extract_urls(report)
    assert cited, "report has no citations"
    assert cited & extract_urls(retrieved), "cited URLs were never retrieved"
