"""agentkit-telemetry: tenant-tagged tracing and the per-run cost ledger.

configure_tracing(TelemetrySettings.from_env())   # off unless OTEL_EXPORTER_OTLP_ENDPOINT
ledger = CostLedger(persistence)                   # rows in memory, and in Postgres if given
config = run_config(ctx, agent_prompt_hash(agent), ledger)
await agent.ainvoke(inputs, config, context=ctx)
shutdown_tracing()
"""

from .ledger import CostLedger, UsageRow, setup
from .run_config import run_config, trace_id
from .tracing import (
    TENANT_ATTR,
    TelemetrySettings,
    configure_tracing,
    flush_tracing,
    shutdown_tracing,
)

__all__ = [
    "TENANT_ATTR",
    "CostLedger",
    "TelemetrySettings",
    "UsageRow",
    "configure_tracing",
    "flush_tracing",
    "run_config",
    "setup",
    "shutdown_tracing",
    "trace_id",
]
