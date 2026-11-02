from __future__ import annotations

import argparse
import sys
import uuid
from collections.abc import Callable, Mapping
from pathlib import Path

from agentkit_config import SpecErrors, read_output
from agentkit_config.spec import AgentSpec
from agentkit_core import ConfigError, PlatformContext, check_label, check_user_id
from agentkit_middleware import TenantMismatch

DEFAULT_AGENT = Path(__file__).parents[2] / "agent.yaml"
PRODUCT, TEAM = "agentkit", "platform"


def _arg(validate: Callable[[str], str]) -> Callable[[str], str]:
    def check(value: str) -> str:
        try:
            return validate(value)
        except ValueError as e:
            raise argparse.ArgumentTypeError(str(e)) from None

    return check


def _label(what: str) -> Callable[[str], str]:
    return _arg(lambda value: check_label(value, what))


def add_agent_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--agent", type=Path, default=DEFAULT_AGENT, help="agent.yaml to run")
    p.add_argument("--model", help="registry entry to use instead of the file's `model`")
    p.add_argument("--tier", choices=("fast", "default", "strong"), help="override `tier`")
    p.add_argument("--no-selection", action="store_true", help="turn Decisions selection off")
    p.add_argument(
        "--tenant",
        type=_label("tenant"),
        default="default",
        help="tenant the run belongs to; must match AGENTKIT_TENANT (default: %(default)s)",
    )
    p.add_argument(
        "--user", type=_arg(check_user_id), default="local", help="user id (default: %(default)s)"
    )


def new_thread() -> str:
    return str(uuid.uuid4())


def platform_context(spec: AgentSpec, *, tenant: str, user: str, thread: str) -> PlatformContext:
    """The run's PlatformContext: agent name and version come from the loaded spec."""
    return PlatformContext(
        tenant=tenant,
        product=PRODUCT,
        team=TEAM,
        user_id=user,
        thread_id=thread,
        agent_name=spec.name,
        agent_version=spec.version,
    )


def overrides_from(a: argparse.Namespace) -> Mapping[str, str]:
    out = {"model": a.model, "tier": a.tier, "selection": "off" if a.no_selection else None}
    return {k: v for k, v in out.items() if v is not None}


def exit_on_spec_errors(main: Callable[[], None]) -> None:
    """Run a CLI main; print load-time spec errors one per line to stderr and exit 2.
    A configuration error (e.g. `--persist` without DATABASE_URL) prints one line and exits 2.
    A run refused by the tenant guard prints one line and exits 1."""
    try:
        main()
    except SpecErrors as e:
        for err in e.errors:
            if err.severity == "error":  # warnings were already logged by load_agent
                print(err, file=sys.stderr)
        raise SystemExit(2) from None
    except ConfigError as e:
        print(f"ConfigError: {e}", file=sys.stderr)
        raise SystemExit(2) from None
    except TenantMismatch as e:
        print(f"TenantMismatch: {e}", file=sys.stderr)
        raise SystemExit(1) from None


__all__ = [
    "DEFAULT_AGENT",
    "add_agent_args",
    "exit_on_spec_errors",
    "new_thread",
    "overrides_from",
    "platform_context",
    "read_output",
]
