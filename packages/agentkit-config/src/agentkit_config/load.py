from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentkit_core import ModelRegistry, ModelSpec, Settings
from agentkit_deep import build_deep_agent
from langchain_core.language_models import BaseChatModel
from pydantic import ValidationError

from agentkit_config.errors import SpecError, SpecErrors
from agentkit_config.library import Library
from agentkit_config.pools.code import CodePools
from agentkit_config.resolve import resolve_agent
from agentkit_config.spec import AgentSpec, parse_agent
from agentkit_config.validate import validate_agent

log = logging.getLogger(__name__)
_OVERRIDE_KEYS = ("model", "tier", "selection")


@dataclass(frozen=True)
class LoadedAgent:
    graph: Any
    spec: AgentSpec
    model_spec: ModelSpec


def apply_overrides(spec: AgentSpec, overrides: Mapping[str, str]) -> AgentSpec:
    bad = sorted(set(overrides) - set(_OVERRIDE_KEYS))
    if bad:
        msg = f"unknown override(s) {bad}; allowed: {list(_OVERRIDE_KEYS)}"
        raise SpecErrors([SpecError("<overrides>", "", msg)])
    changes: dict[str, Any] = dict(overrides)
    if changes.get("selection") == "off":
        changes["selection"] = None
    try:
        return AgentSpec.model_validate({**spec.model_dump(), **changes})
    except ValidationError as e:
        raise SpecErrors(
            [
                SpecError("<overrides>", ".".join(str(p) for p in err["loc"]), err["msg"])
                for err in e.errors()
            ]
        ) from e


def load_agent(
    path: str | Path,
    *,
    settings: Settings,
    library: Library | None = None,
    overrides: Mapping[str, str] | None = None,
    model: BaseChatModel | None = None,
) -> LoadedAgent:
    """parse -> overrides -> validate -> resolve -> build. Validation precedes any key check."""
    path = Path(path)
    lib = library if library is not None else Library.for_file(path, CodePools.from_entry_points())
    models = ModelRegistry.default()
    spec = parse_agent(path)
    if overrides:
        spec = apply_overrides(spec, overrides)
    problems = validate_agent(spec, lib, models, file=str(path))
    for w in (p for p in problems if p.severity == "warning"):
        log.warning("%s", w)
    SpecErrors(problems).raise_if_errors()
    kwargs = resolve_agent(spec, lib, models, settings, model=model)
    graph = build_deep_agent(**kwargs)
    return LoadedAgent(graph, spec, models.resolve(spec.model, spec.tier))
