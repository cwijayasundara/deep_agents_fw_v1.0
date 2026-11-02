"""`agentkit validate <paths...>`: offline validation of agent, subagent and flow specs."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

from agentkit_core import ModelRegistry

from agentkit_config.errors import SpecError, SpecErrors
from agentkit_config.library import Library
from agentkit_config.pools.code import CodePools
from agentkit_config.spec import load_yaml, parse_agent, parse_subagent
from agentkit_config.validate import validate_agent, validate_subagent

USAGE = "usage: agentkit validate <path>..."


def _check_file(path: Path, code: CodePools, models: ModelRegistry) -> list[SpecError]:
    file = str(path)
    kind = load_yaml(path).get("kind")
    if kind == "Flow":
        return [SpecError(file, "kind", "flows not supported yet")]
    if kind not in ("Agent", "SubAgent"):
        msg = f"unknown or missing kind {kind!r}; expected Agent, SubAgent or Flow"
        return [SpecError(file, "kind", msg)]
    lib = Library.for_file(path, code)
    if kind == "Agent":
        return validate_agent(parse_agent(path), lib, models, file=file)
    return validate_subagent(parse_subagent(path), lib, models, file=file)


def _validate(paths: Sequence[str]) -> int:
    code = CodePools.from_entry_points()
    models = ModelRegistry.default()
    checked = errors = warnings = 0
    for raw in paths:
        path = Path(raw)
        if "*" in raw and not path.exists():
            continue  # a glob the shell left literal because nothing matched
        checked += 1
        try:
            problems = _check_file(path, code, models)
        except SpecErrors as exc:
            problems = exc.errors
        for p in problems:
            print(p if p.severity == "error" else f"warning: {p}")
        errors += sum(p.severity == "error" for p in problems)
        warnings += sum(p.severity == "warning" for p in problems)
    print(f"checked {checked} file(s): {errors} error(s), {warnings} warning(s)")
    return 1 if errors else 0


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] != "validate":
        print(USAGE)
        return 2
    return _validate(args[1:])


if __name__ == "__main__":
    sys.exit(main())
