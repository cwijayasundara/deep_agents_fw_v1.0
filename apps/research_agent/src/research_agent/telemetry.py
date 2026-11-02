"""Tracing and the cost ledger for the research CLIs."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from typing import Any
from uuid import UUID

from agentkit_core import Settings
from agentkit_persistence import Persistence
from agentkit_telemetry import (
    CostLedger,
    TelemetrySettings,
    configure_tracing,
    setup,
    shutdown_tracing,
)

log = logging.getLogger("research_agent")


@contextmanager
def tracing(settings: Settings) -> Iterator[None]:
    """Trace this process's runs when OTEL_EXPORTER_OTLP_ENDPOINT is set; flush on the way out."""
    telemetry = TelemetrySettings.from_env(tenant=settings.deployment_tenant)
    if configure_tracing(telemetry) is not None:
        payloads = "on" if telemetry.trace_payloads else "masked"
        log.info("tracing to %s (payloads %s)", telemetry.otlp_endpoint, payloads)
    try:
        yield
    finally:
        shutdown_tracing()


async def persistent_ledger(p: Persistence) -> CostLedger:
    """A ledger that also writes each row to `agentkit_usage` (created if missing)."""
    await setup(p)
    return CostLedger(p)


async def ledger_for(p: Persistence | None) -> CostLedger:
    return CostLedger() if p is None else await persistent_ledger(p)


def usage_of(ledger: CostLedger, run_id: Any) -> dict[str, Any] | None:
    """The run's ledger row as JSON-ready usage (no ids), or None if it recorded nothing."""
    row = ledger.row(run_id) if isinstance(run_id, UUID) else None
    if row is None:
        return None
    return {k: v for k, v in asdict(row).items() if k not in ("run_id", "tenant", "thread_id")}
