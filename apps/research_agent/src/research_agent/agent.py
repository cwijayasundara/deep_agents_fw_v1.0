from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml
from agentkit_core import ConfigError, ModelRegistry, Provider, Settings, get_model
from agentkit_deep import build_deep_agent
from agentkit_middleware import DecisionsClient, DecisionsSelector, SelectionMiddleware
from agentkit_tools import (
    FetchTool,
    HttpFetch,
    SearchTool,
    TavilySearch,
    make_fetch_tool,
    make_web_search_tool,
)
from langchain.agents.middleware import AgentMiddleware
from langchain_core.language_models import BaseChatModel

from .prompts import ORCHESTRATOR, RESEARCHER


def load_config(path: str | Path) -> dict[str, str]:
    cfg = yaml.safe_load(Path(path).read_text()) or {}
    if "model" not in cfg:
        raise ValueError(f"{path}: 'model' is required")
    out = {"model": cfg["model"], "tier": cfg.get("tier", "default")}
    if cfg.get("selection"):
        if cfg["selection"] != "decisions":
            raise ValueError(f"{path}: unknown selection '{cfg['selection']}'")
        out["selection"] = cfg["selection"]
    return out


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
    tools = [make_web_search_tool(search), make_fetch_tool(fetch or HttpFetch())]
    researcher = {
        "name": "researcher",
        "description": "Read-only researcher for one sub-question; returns sourced findings.",
        "system_prompt": RESEARCHER,
        "tools": tools,
    }
    registry = registry or ModelRegistry.default()
    spec = registry.resolve(config["model"], config["tier"])
    middleware = list(middleware)
    if config.get("selection") == "decisions":
        middleware.append(
            _decisions_middleware(config, settings, registry, with_models=model is None)
        )
    return build_deep_agent(
        model=model or spec,
        settings=settings,
        system_prompt=ORCHESTRATOR,
        tools=tools,
        subagents=[researcher],
        middleware=middleware,
        name="research_agent",
    )


def _decisions_middleware(
    config: dict[str, str], settings: Settings, registry: ModelRegistry, *, with_models: bool
) -> SelectionMiddleware:
    """Decisions picks the visible tools and the model tier (tier -> model from the registry)."""
    selector = DecisionsSelector(
        DecisionsClient(settings.require_key(Provider.OPENAI)),
        default_tier=config["tier"],
        system_prompt=ORCHESTRATOR,
    )
    models = (
        {t: get_model(registry.resolve(config["model"], t), settings) for t in registry_tiers()}
        if with_models
        else {}
    )
    return SelectionMiddleware(selector, models=models, default_tier=config["tier"])


def registry_tiers() -> tuple[str, ...]:
    return ("fast", "default", "strong")


def _require(settings: Settings) -> str:
    if settings.tavily_api_key is None:
        raise ConfigError("TAVILY_API_KEY is required for the web search tool")
    return settings.tavily_api_key.get_secret_value()


def extract_report(result: dict[str, Any]) -> str:
    f = result.get("files", {}).get("/report.md")
    if f is None:
        return ""
    content = f["content"] if isinstance(f, dict) else f
    return "\n".join(content) if isinstance(content, list) else str(content)
