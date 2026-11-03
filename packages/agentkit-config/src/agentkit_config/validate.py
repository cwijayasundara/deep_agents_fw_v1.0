from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from typing import Any, Literal

from agentkit_core import TIERS, ModelRegistry
from agentkit_middleware.selection import BUILTIN_TOOLS

from agentkit_config.errors import SpecError, SpecErrors
from agentkit_config.library import Library
from agentkit_config.pools.code import check_params, factory_meta
from agentkit_config.pools.prompts import ALLOWED_VARS, compose, variables
from agentkit_config.registry import Registry
from agentkit_config.spec import AgentSpec, MiddlewareRef, SubAgentSpec, ToolRef
from agentkit_config.stack import SINGLETONS

NO_SCHEMA = "no response_schema; completion contract recommended"
NO_CALL_LIMIT = "no call_limit; a runaway loop is unbounded"
# Types that may repeat, and the param that must differ between repeats.
_REPEAT_KEY = {"pii": "type", "tool_call_limit": "tool_name"}


class _Ctx:
    def __init__(self, lib: Library, models: ModelRegistry, file: str) -> None:
        self.lib, self.models, self.file = lib, models, file

    def err(
        self, path: str, msg: str, severity: Literal["error", "warning"] = "error"
    ) -> SpecError:
        return SpecError(self.file, path, msg, severity)


def _join(prefix: str, leaf: str) -> str:
    return f"{prefix}.{leaf}" if prefix else leaf


def _unknown(c: _Ctx, path: str, kind: str, name: str, known: Iterable[str]) -> SpecError:
    return c.err(path, f"unknown {kind} {name!r}; known: {', '.join(sorted(known)) or '(none)'}")


def _check_name(c: _Ctx, path: str, kind: str, name: str, reg: Registry[Any]) -> list[SpecError]:
    return [] if name in reg else [_unknown(c, path, kind, name, reg.names())]


def _model_errors(c: _Ctx, path: str, model: str | None, tier: str | None) -> list[SpecError]:
    out: list[SpecError] = []
    if model is not None and model not in c.models.names():
        out.append(_unknown(c, _join(path, "model"), "model entry", model, c.models.names()))
    if tier is not None and tier not in TIERS:
        out.append(_unknown(c, _join(path, "tier"), "tier", tier, TIERS))
    return out


def _prompt_errors(c: _Ctx, path: str, ref: str) -> list[SpecError]:
    p = _join(path, "prompt")
    prompts = c.lib.prompts
    name = ref.partition("@")[0]
    broken = [c.err(p, m) for m in prompts.label_errors() if m.startswith(f"label {name}@")]
    if broken:
        return broken
    try:
        prompt = prompts.get_ref(ref, file=c.file, path=p)
        text = compose(prompt, prompts, file=c.file, path=p)
    except SpecErrors as exc:
        return list(exc.errors)
    bad = sorted(variables(text) - ALLOWED_VARS)
    if not bad:
        return []
    return [
        c.err(
            p,
            f"prompt {ref!r} uses unsupported variable(s) {bad}; allowed: {sorted(ALLOWED_VARS)}",
        )
    ]


def _params_error(
    c: _Ctx, path: str, factory: Callable[..., Any], params: Mapping[str, Any], name: str
) -> list[SpecError]:
    msg = check_params(factory, params)
    return [c.err(path, f"bad params for {name!r}: {msg}")] if msg else []


def _tool_errors(c: _Ctx, path: str, tools: list[ToolRef], tenant: str | None) -> list[SpecError]:
    out: list[SpecError] = []
    seen: set[str] = set()
    for i, t in enumerate(tools):
        p = f"{_join(path, 'tools')}[{i}]"
        if t.name in seen:
            out.append(c.err(p, f"duplicate tool {t.name!r}"))
        seen.add(t.name)
        if c.lib.code is None:
            out.append(c.err(p, f"no code pools loaded; cannot resolve tool {t.name!r}"))
        elif t.name not in c.lib.code.tools:
            out.append(_unknown(c, p, "tool", t.name, c.lib.code.tools.names()))
        else:
            factory = c.lib.code.tools.get(t.name, file=c.file, path=p)
            bad_params = _params_error(c, p, factory, t.params, t.name)
            out.extend(bad_params)
            if not bad_params:
                out.extend(_hook_errors(c, p, factory, t.params, t.name))
            out.extend(_policy_errors(c, p, factory, t.name, tenant))
    return out


def _hook_errors(
    c: _Ctx, path: str, factory: Callable[..., Any], params: Mapping[str, Any], name: str
) -> list[SpecError]:
    """A factory's own param checks (ruling S3): `__agentkit_validate__(params, library)`
    returns problem messages. Duck-typed, so config never imports the tool's package."""
    hook = getattr(factory, "__agentkit_validate__", None)
    if not callable(hook):
        return []
    try:
        problems = list(hook(params, c.lib))
    except Exception as e:  # validate never raises
        problems = [f"validation hook of tool {name!r} failed: {type(e).__name__}: {e}"]
    return [c.err(path, str(m)) for m in problems]


def _policy_errors(
    c: _Ctx, path: str, factory: Callable[..., Any], name: str, tenant: str | None
) -> list[SpecError]:
    meta = factory_meta(factory)
    if meta is None:
        return [
            c.err(
                path,
                f"tool {name!r} has no @platform_tool metadata; "
                "its calls would be refused as unregistered",
            )
        ]
    if tenant is not None and meta.tenants is not None and tenant not in meta.tenants:
        return [c.err(path, f"tool {name!r} is not available to tenant {tenant!r}")]
    return []


def _middleware_errors(c: _Ctx, path: str, mws: list[MiddlewareRef]) -> list[SpecError]:
    out: list[SpecError] = []
    seen: set[tuple[str, Any]] = set()
    for i, m in enumerate(mws):
        p = f"{_join(path, 'middleware')}[{i}]"
        if m.enabled and m.type != "selection" and (m.type in SINGLETONS or m.type in _REPEAT_KEY):
            key = (m.type, m.params.get(_REPEAT_KEY[m.type]) if m.type in _REPEAT_KEY else None)
            if key in seen:
                out.append(c.err(p, f"duplicate middleware {m.type!r}"))
            seen.add(key)
        if m.type == "selection":
            out.append(c.err(p, "use top-level 'selection:'"))
        elif c.lib.code is None:
            out.append(c.err(p, f"no code pools loaded; cannot resolve middleware {m.type!r}"))
        elif m.type not in c.lib.code.middleware:
            out.append(_unknown(c, p, "middleware", m.type, c.lib.code.middleware.names()))
        else:
            factory = c.lib.code.middleware.get(m.type, file=c.file, path=p)
            out.extend(_params_error(c, p, factory, m.params, m.type))
    return out


def _schema_errors(c: _Ctx, path: str, field: str, name: str | None) -> list[SpecError]:
    if name is None:
        return []
    if c.lib.code is None:
        msg = f"no code pools loaded; cannot resolve schema {name!r}"
        return [c.err(_join(path, field), msg)]
    return _check_name(c, _join(path, field), "schema", name, c.lib.code.schemas)


def _skill_errors(c: _Ctx, path: str, skills: list[str], tools: list[ToolRef]) -> list[SpecError]:
    out: list[SpecError] = []
    owned = {t.name for t in tools} | BUILTIN_TOOLS
    for i, name in enumerate(skills):
        p = f"{_join(path, 'skills')}[{i}]"
        if name not in c.lib.skills:
            out.append(_unknown(c, p, "skill", name, c.lib.skills.names()))
            continue
        missing = sorted(c.lib.skills.get(name, file=c.file, path=p).tools - owned)
        if missing:
            out.append(
                c.err(
                    p, f"skill {name!r} needs tools this owner lacks; missing: {', '.join(missing)}"
                )
            )
    return out


def validate_subagent(
    spec: SubAgentSpec,
    lib: Library,
    models: ModelRegistry,
    *,
    file: str,
    path: str = "",
    tenant: str | None = None,
) -> list[SpecError]:
    """Collect every cross-reference problem in one subagent; never raises.

    With `tenant`, tools restricted to other tenants are errors."""
    c = _Ctx(lib, models, file)
    out = _model_errors(c, path, spec.model, spec.tier)
    out += _prompt_errors(c, path, spec.prompt)
    out += _tool_errors(c, path, spec.tools, tenant)
    out += _skill_errors(c, path, spec.skills, spec.tools)
    out += _middleware_errors(c, path, spec.middleware)
    out += _schema_errors(c, path, "response_schema", spec.response_schema)
    if spec.response_schema is None:
        out.append(c.err(path, NO_SCHEMA, "warning"))
    return out


def _subagent_errors(c: _Ctx, spec: AgentSpec, tenant: str | None) -> list[SpecError]:
    out: list[SpecError] = []
    seen: set[str] = set()
    for i, entry in enumerate(spec.subagents):
        p = f"subagents[{i}]"
        if isinstance(entry, str):
            if entry not in c.lib.subagents:
                out.append(_unknown(c, p, "subagent", entry, c.lib.subagents.names()))
                continue
            entry = c.lib.subagents.get(entry, file=c.file, path=p)
        if entry.name == spec.name:
            out.append(c.err(p, f"subagent name {entry.name!r} must differ from the agent name"))
        if entry.name in seen:
            out.append(c.err(p, f"duplicate subagent {entry.name!r}"))
        seen.add(entry.name)
        out.extend(validate_subagent(entry, c.lib, c.models, file=c.file, path=p, tenant=tenant))
    return out


def validate_agent(
    spec: AgentSpec, lib: Library, models: ModelRegistry, *, file: str, tenant: str | None = None
) -> list[SpecError]:
    """Collect every cross-reference problem in an agent; never raises.

    With `tenant`, tools restricted to other tenants are errors."""
    c = _Ctx(lib, models, file)
    out = _model_errors(c, "", spec.model, spec.tier)
    out += _prompt_errors(c, "", spec.prompt)
    out += _tool_errors(c, "", spec.tools, tenant)
    out += _skill_errors(c, "", spec.skills, spec.tools)
    out += _middleware_errors(c, "", spec.middleware)
    if spec.output is not None and not spec.output.startswith("/"):
        out.append(c.err("output", "output must be an absolute file path like /report.md"))
    if not any(m.type == "call_limit" and m.enabled for m in spec.middleware):
        out.append(c.err("", NO_CALL_LIMIT, "warning"))
    out += _subagent_errors(c, spec, tenant)
    return out
