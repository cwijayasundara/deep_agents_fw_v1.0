"""`agentkit validate <paths...>`: offline validation of agent, subagent and flow specs."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from pathlib import Path

from agentkit_core import ModelRegistry, Settings

from agentkit_config.errors import SpecError, SpecErrors
from agentkit_config.flow import flow_library, validate_flow
from agentkit_config.library import Library
from agentkit_config.pools.code import CodePools
from agentkit_config.spec import load_yaml, parse_agent, parse_flow, parse_subagent
from agentkit_config.toolpolicy import (
    current_snapshot,
    default_snapshot_path,
    diff_snapshot,
    list_lines,
    read_snapshot,
    write_snapshot,
)
from agentkit_config.validate import validate_agent, validate_subagent

USAGE = (
    "usage: agentkit validate <path>...\n"
    "       agentkit tools list [--tenant T]\n"
    "       agentkit tools snapshot [--check] [--file PATH]"
)


def _check_file(path: Path, code: CodePools, models: ModelRegistry, tenant: str) -> list[SpecError]:
    file = str(path)
    kind = load_yaml(path).get("kind")
    if kind == "Flow":
        return validate_flow(parse_flow(path), flow_library(path, code), models, file=file)
    if kind not in ("Agent", "SubAgent"):
        msg = f"unknown or missing kind {kind!r}; expected Agent, SubAgent or Flow"
        return [SpecError(file, "kind", msg)]
    lib = Library.for_file(path, code)
    if kind == "Agent":
        return validate_agent(parse_agent(path), lib, models, file=file, tenant=tenant)
    return validate_subagent(parse_subagent(path), lib, models, file=file, tenant=tenant)


def _validate(paths: Sequence[str]) -> int:
    code = CodePools.from_entry_points()
    models = ModelRegistry.default()
    tenant = Settings().deployment_tenant
    checked = errors = warnings = 0
    for raw in paths:
        path = Path(raw)
        if "*" in raw and not path.exists():
            continue  # a glob the shell left literal because nothing matched
        checked += 1
        try:
            problems = _check_file(path, code, models, tenant)
        except SpecErrors as exc:
            problems = exc.errors
        for p in problems:
            print(p if p.severity == "error" else f"warning: {p}")
        errors += sum(p.severity == "error" for p in problems)
        warnings += sum(p.severity == "warning" for p in problems)
    print(f"checked {checked} file(s): {errors} error(s), {warnings} warning(s)")
    return 1 if errors else 0


def _option(args: list[str], flag: str) -> str | None:
    """The value after `flag`, or None."""
    return args[args.index(flag) + 1] if flag in args and args.index(flag) + 1 < len(args) else None


def _tools(args: list[str]) -> int:
    code = CodePools.from_entry_points()
    if args[:1] == ["list"]:
        for line in list_lines(code, _option(args, "--tenant") or Settings().deployment_tenant):
            print(line)
        return 0
    if args[:1] == ["snapshot"]:
        path = Path(_option(args, "--file") or default_snapshot_path())
        snap = current_snapshot(code)
        if "--check" not in args:
            write_snapshot(path, snap)
            print(f"wrote {len(snap)} tool schema(s) to {path}")
            return 0
        problems = diff_snapshot(snap, read_snapshot(path))
        for p in problems:
            print(p)
        return 1 if problems else 0
    print(USAGE)
    return 2


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] == ["validate"]:
        return _validate(args[1:])
    if args[:1] == ["tools"]:
        return _tools(args[1:])
    print(USAGE)
    return 2


if __name__ == "__main__":
    sys.exit(main())
