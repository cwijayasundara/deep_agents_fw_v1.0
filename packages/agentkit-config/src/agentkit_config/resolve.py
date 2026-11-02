from __future__ import annotations

import datetime
from pathlib import Path
from typing import Any

from agentkit_core import BuildContext, ModelRegistry, Settings, get_model
from agentkit_deep.skills_mount import skills_mount, skills_source
from langchain.agents.middleware import AgentMiddleware
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool

from agentkit_config.errors import SpecError, SpecErrors
from agentkit_config.library import Library
from agentkit_config.pools.prompts import render
from agentkit_config.selection import decisions_middleware
from agentkit_config.spec import AgentSpec, MiddlewareRef, SubAgentSpec, ToolRef

_FILE = "<resolve>"


def _code(lib: Library) -> Any:
    if lib.code is None:
        raise SpecErrors([SpecError(_FILE, "", "no code pools loaded")])
    return lib.code


def _tools(refs: list[ToolRef], lib: Library, ctx: BuildContext) -> list[BaseTool]:
    pool = _code(lib).tools
    return [pool.get(r.name, file=_FILE, path=r.name)(ctx, **r.params) for r in refs]


def _middleware(
    refs: list[MiddlewareRef], lib: Library, ctx: BuildContext
) -> list[AgentMiddleware]:
    pool = _code(lib).middleware
    return [pool.get(r.type, file=_FILE, path=r.type)(ctx, **r.params) for r in refs if r.enabled]


def _skill_dirs(names: list[str], lib: Library) -> list[Path]:
    return [lib.skills.get(n, file=_FILE, path=n).dir for n in names]


def _subagent(
    sub: SubAgentSpec,
    lib: Library,
    models: ModelRegistry,
    settings: Settings,
    parent: AgentSpec,
    today: str,
) -> dict[str, Any]:
    # Only a tier: parent's entry at that tier. A model: that entry at its tier (default if unset).
    inherited_tier = parent.tier if sub.model is None else "default"
    spec = models.resolve(sub.model or parent.model, sub.tier or inherited_tier)
    ctx = BuildContext(settings, spec, sub.name)
    prompt = lib.prompts.get(sub.prompt, file=_FILE, path=sub.prompt)
    out: dict[str, Any] = {
        "name": sub.name,
        "description": sub.description,
        "system_prompt": render(prompt, agent_name=sub.name, date=today),
        "tools": _tools(sub.tools, lib, ctx),
    }
    if sub.model is not None or sub.tier is not None:
        out["model"] = get_model(spec, settings)
    if sub.skills:
        out["skills"] = [skills_source(sub.name)]
    if sub.response_schema is not None:
        out["response_format"] = _code(lib).schemas.get(
            sub.response_schema, file=_FILE, path=sub.response_schema
        )
    mw = _middleware(sub.middleware, lib, ctx)
    if mw:
        out["middleware"] = mw
    return out


def resolve_agent(
    spec: AgentSpec,
    lib: Library,
    models: ModelRegistry,
    settings: Settings,
    *,
    model: BaseChatModel | None,
) -> dict[str, Any]:
    """Turn a validated AgentSpec into kwargs for `build_deep_agent`."""
    today = datetime.date.today().isoformat()
    model_spec = models.resolve(spec.model, spec.tier)
    ctx = BuildContext(settings, model_spec, spec.name)
    prompt = lib.prompts.get(spec.prompt, file=_FILE, path=spec.prompt)
    system_prompt = render(prompt, agent_name=spec.name, date=today)

    subs = [
        lib.subagents.get(e, file=_FILE, path=e) if isinstance(e, str) else e
        for e in spec.subagents
    ]
    middleware = _middleware(spec.middleware, lib, ctx)
    if spec.selection == "decisions":
        middleware.append(
            decisions_middleware(
                ctx,
                models,
                spec.tier,
                system_prompt,
                with_models=model is None,
                entry=spec.model,
            )
        )
    kwargs: dict[str, Any] = {
        "name": spec.name,
        "model": model or model_spec,
        "settings": settings,
        "system_prompt": system_prompt,
        "tools": _tools(spec.tools, lib, ctx),
        "subagents": [_subagent(s, lib, models, settings, spec, today) for s in subs],
        "middleware": middleware,
    }
    owners = {spec.name: _skill_dirs(spec.skills, lib)}
    owners.update({s.name: _skill_dirs(s.skills, lib) for s in subs})
    owners = {o: dirs for o, dirs in owners.items() if dirs}
    if owners:
        backend, permissions = skills_mount(owners)
        kwargs["backend"] = backend
        kwargs["permissions"] = permissions
        if spec.skills:
            kwargs["skills"] = [skills_source(spec.name)]
    return kwargs
