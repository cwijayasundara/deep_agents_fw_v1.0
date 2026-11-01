from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml
from agentkit_core import ModelRegistry, Settings
from agentkit_deep import build_deep_agent
from agentkit_tools import FetchTool, HttpFetch, SearchTool, TavilySearch, make_research_tools
from langchain.agents.middleware import AgentMiddleware
from langchain_core.language_models import BaseChatModel

from .prompts import ORCHESTRATOR, RESEARCHER


def load_config(path: str | Path) -> dict[str, str]:
    cfg = yaml.safe_load(Path(path).read_text()) or {}
    if "model" not in cfg:
        raise ValueError(f"{path}: 'model' is required")
    return {"model": cfg["model"], "tier": cfg.get("tier", "default")}


def build_research_agent(
    config: dict[str, str],
    settings: Settings,
    *,
    search: SearchTool | None = None,
    fetch: FetchTool | None = None,
    model: BaseChatModel | None = None,
    middleware: Sequence[AgentMiddleware] = (),
    registry: ModelRegistry | None = None,
) -> Any:
    """Provider is chosen purely by `config['model']` (a registry entry name)."""
    if search is None:
        search = TavilySearch(_require(settings))
    tools = make_research_tools(search, fetch or HttpFetch())
    researcher = {
        "name": "researcher",
        "description": "Read-only researcher for one sub-question; returns sourced findings.",
        "system_prompt": RESEARCHER,
        "tools": tools,
    }
    spec = (registry or ModelRegistry.default()).resolve(config["model"], config["tier"])
    return build_deep_agent(
        model=model or spec,
        settings=settings,
        system_prompt=ORCHESTRATOR,
        tools=tools,
        subagents=[researcher],
        middleware=middleware,
        name="research_agent",
    )


def _require(settings: Settings) -> str:
    if settings.tavily_api_key is None:
        from agentkit_core import ConfigError

        raise ConfigError("TAVILY_API_KEY is required for the web search tool")
    return settings.tavily_api_key.get_secret_value()


def extract_report(result: dict[str, Any]) -> str:
    f = result.get("files", {}).get("/report.md")
    if f is None:
        return ""
    content = f["content"] if isinstance(f, dict) else f
    return "\n".join(content) if isinstance(content, list) else str(content)
