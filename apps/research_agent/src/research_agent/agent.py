from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Mapping
from pathlib import Path

from agentkit_config import SpecErrors, read_output

DEFAULT_AGENT = Path(__file__).parents[2] / "agent.yaml"


def add_agent_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--agent", type=Path, default=DEFAULT_AGENT, help="agent.yaml to run")
    p.add_argument("--model", help="registry entry to use instead of the file's `model`")
    p.add_argument("--tier", choices=("fast", "default", "strong"), help="override `tier`")
    p.add_argument("--no-selection", action="store_true", help="turn Decisions selection off")


def overrides_from(a: argparse.Namespace) -> Mapping[str, str]:
    out = {"model": a.model, "tier": a.tier, "selection": "off" if a.no_selection else None}
    return {k: v for k, v in out.items() if v is not None}


def exit_on_spec_errors(main: Callable[[], None]) -> None:
    """Run a CLI main; print load-time spec errors one per line to stderr and exit 2."""
    try:
        main()
    except SpecErrors as e:
        for err in e.errors:
            if err.severity == "error":  # warnings were already logged by load_agent
                print(err, file=sys.stderr)
        raise SystemExit(2) from None


__all__ = [
    "DEFAULT_AGENT",
    "add_agent_args",
    "exit_on_spec_errors",
    "overrides_from",
    "read_output",
]
