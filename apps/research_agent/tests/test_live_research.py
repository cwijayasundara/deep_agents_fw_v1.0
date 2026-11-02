"""Opt-in end-to-end run against real providers: `uv run pytest -m live`.

Set RESEARCH_LIVE_MODELS (comma-separated registry entries, default 'fireworks-glm') and the
matching provider key (search uses DuckDuckGo, no key).
"""

import os

import pytest
from agentkit_config import load_agent, read_output
from agentkit_core import Settings
from agentkit_evals import extract_urls
from langchain_core.messages import HumanMessage
from research_agent import DEFAULT_AGENT

NAMES = os.environ.get("RESEARCH_LIVE_MODELS", "fireworks-glm").split(",")
PRESENT = set(Settings().keys_present())  # reads .env like the CLIs do


@pytest.mark.live
@pytest.mark.parametrize("name", NAMES)
async def test_full_research_run(name):
    if "OPENAI_API_KEY" not in PRESENT:
        pytest.skip("OPENAI_API_KEY not set (needed for Decisions selection)")
    loaded = load_agent(DEFAULT_AGENT, settings=Settings(), overrides={"model": name})
    out = await loaded.graph.ainvoke(
        {"messages": [HumanMessage("What is the Model Context Protocol? Keep it short.")]},
        config={"recursion_limit": 100},
    )
    report = read_output(out, loaded.spec.output)
    assert report, "agent did not write /report.md"
    retrieved = "\n".join(str(m.content) for m in out["messages"] if m.type == "tool")
    cited = extract_urls(report)
    assert cited, "report has no citations"
    assert cited & extract_urls(retrieved), "cited URLs were never retrieved"
