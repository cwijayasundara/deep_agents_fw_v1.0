from __future__ import annotations

import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from agentkit_core import BuildContext, ModelRegistry, Settings, get_model
from agentkit_deep.memory import memory_backend
from agentkit_deep.skills_mount import (
    skills_mount,
    skills_permissions,
    skills_routes,
    skills_source,
)
from langchain.agents.middleware import AgentMiddleware
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool

from agentkit_config.errors import SpecError, SpecErrors
from agentkit_config.library import Library
from agentkit_config.pools.prompts import render
from agentkit_config.selection import decisions_middleware
from agentkit_config.spec import AgentSpec, MiddlewareRef, SubAgentSpec, ToolRef
from agentkit_config.stack import order_stack

if TYPE_CHECKING:
    from agentkit_persistence import Persistence

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
) -> list[tuple[str, AgentMiddleware]]:
    pool = _code(lib).middleware
    return [
        (r.type, pool.get(r.type, file=_FILE, path=r.type)(ctx, **r.params))
        for r in refs
        if r.enabled
    ]


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
    # An unset model or tier is inherited from the parent.
    spec = models.resolve(sub.model or parent.model, sub.tier or parent.tier)
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
    mw = order_stack(_middleware(sub.middleware, lib, ctx))
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
    persistence: Persistence | None = None,
) -> dict[str, Any]:
    """Turn a validated AgentSpec into kwargs for `build_deep_agent`.

    With `persistence`, skills routes are folded into the memory backend (one composite)."""
    today = datetime.date.today().isoformat()
    model_spec = models.resolve(spec.model, spec.tier)
    ctx = BuildContext(settings, model_spec, spec.name)
    prompt = lib.prompts.get(spec.prompt, file=_FILE, path=spec.prompt)
    system_prompt = render(prompt, agent_name=spec.name, date=today)

    subs = [
        lib.subagents.get(e, file=_FILE, path=e) if isinstance(e, str) else e
        for e in spec.subagents
    ]
    items = _middleware(spec.middleware, lib, ctx)
    if spec.selection == "decisions":
        items.append(
            (
                "selection",
                decisions_middleware(
                    ctx,
                    models,
                    spec.tier,
                    system_prompt,
                    with_models=model is None,
                    entry=spec.model,
                ),
            )
        )
    middleware = order_stack(items)
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
    if persistence is not None:
        kwargs["persistence"] = persistence
    if owners:
        if persistence is not None:
            kwargs["backend"] = memory_backend(skills_routes(owners))
            kwargs["permissions"] = skills_permissions()
        else:
            kwargs["backend"], kwargs["permissions"] = skills_mount(owners)
        if spec.skills:
            kwargs["skills"] = [skills_source(spec.name)]
    return kwargs
