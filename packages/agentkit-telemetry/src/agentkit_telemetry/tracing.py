"""Tenant-tagged tracing: one Langfuse client emitting OTel spans to an OTLP collector.

Off unless `OTEL_EXPORTER_OTLP_ENDPOINT` is set. Spans go only to that collector (which may
forward to Langfuse); the client never calls the Langfuse API itself, so it runs without
Langfuse keys. Prompt and completion text, and error text (status messages, exception events;
the exception type name is kept), are dropped unless `AGENTKIT_TRACE_PAYLOADS=1`.
`LANGSMITH_TRACING` is never set: LangSmith's OTel path stamps every `LANGSMITH_*` variable
into spans and has no masking hook.
"""

from __future__ import annotations

import logging
import math
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from agentkit_core import Label
from agentkit_core.settings import find_env_file
from langfuse import Langfuse
from langfuse.langchain import CallbackHandler
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SpanExporter
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .export import QuietExporter, mask_payloads

TENANT_ATTR = "agentkit.tenant"
# The client is handed its own exporter, so this API address is never contacted.
_NO_LANGFUSE_API = "http://127.0.0.1:9"
# QuietExporter's one warning replaces the OTLP exporter's per-batch errors; Langfuse warns
# per run about metadata it drops (e.g. deepagents' `lc_agent_name=None`).
_QUIET_LOGGERS = {"opentelemetry.exporter.otlp": logging.CRITICAL, "langfuse": logging.ERROR}


class TelemetrySettings(BaseSettings):
    """Tracing settings, read from process env, then the nearest `.env` (via `from_env`)."""

    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)

    otlp_endpoint: str | None = Field(
        default=None, validation_alias=AliasChoices("OTEL_EXPORTER_OTLP_ENDPOINT", "otlp_endpoint")
    )
    trace_payloads: bool = Field(
        default=False, validation_alias=AliasChoices("AGENTKIT_TRACE_PAYLOADS", "trace_payloads")
    )
    tenant: Label = Field(
        default="default", validation_alias=AliasChoices("AGENTKIT_TENANT", "tenant")
    )
    service_name: str = Field(
        default="agentkit", validation_alias=AliasChoices("OTEL_SERVICE_NAME", "service_name")
    )
    export_timeout_seconds: float = Field(default=2.0, gt=0)

    @classmethod
    def from_env(cls, env_file: Path | None | str = "auto", **overrides: Any) -> TelemetrySettings:
        path = find_env_file() if env_file == "auto" else env_file
        return cls(_env_file=path, **overrides)  # type: ignore[call-arg]


class MaskingCallbackHandler(CallbackHandler):
    """Langfuse handler that records an error as its exception type name only.

    Langfuse sets `status_message` (and the span status) to `str(error)`, which can carry user
    text (a tool's ValidationError echoes its input). Overrides Langfuse's one error hook."""

    def _get_error_level_and_status_message(
        self, error: BaseException
    ) -> tuple[Literal["DEFAULT", "ERROR"], str]:
        level, _ = super()._get_error_level_and_status_message(error)
        return level, type(error).__name__


@dataclass(frozen=True)
class _Tracing:
    client: Langfuse
    provider: TracerProvider
    public_key: str
    masked: bool


_active: _Tracing | None = None


def configure_tracing(
    settings: TelemetrySettings, *, exporter: SpanExporter | None = None
) -> Langfuse | None:
    """Turn tracing on for this process (replacing any earlier setup); None when it stays off.

    `exporter` replaces the OTLP exporter (tests pass an in-memory one)."""
    global _active
    shutdown_tracing()
    if exporter is None:
        if not settings.otlp_endpoint:
            return None
        endpoint = settings.otlp_endpoint.rstrip("/") + "/v1/traces"
        exporter = OTLPSpanExporter(endpoint=endpoint, timeout=settings.export_timeout_seconds)
        where = endpoint
    else:
        where = type(exporter).__name__
    resource = Resource.create({SERVICE_NAME: settings.service_name, TENANT_ATTR: settings.tenant})
    provider = TracerProvider(resource=resource, shutdown_on_exit=False)
    public_key = f"agentkit-{uuid.uuid4().hex[:12]}"  # a local client label, not a Langfuse key
    client = Langfuse(
        public_key=public_key,
        secret_key="agentkit-local",
        base_url=_NO_LANGFUSE_API,
        tracer_provider=provider,
        span_exporter=QuietExporter(exporter, where, redact=not settings.trace_payloads),
        mask_otel_spans=None if settings.trace_payloads else mask_payloads,
        timeout=math.ceil(settings.export_timeout_seconds),
    )
    for name, level in _QUIET_LOGGERS.items():
        logging.getLogger(name).setLevel(level)
    _active = _Tracing(client, provider, public_key, masked=not settings.trace_payloads)
    return client


def langchain_handler(run_id: UUID) -> CallbackHandler | None:
    """A Langfuse callback handler whose trace id derives from `run_id`; None if tracing is off."""
    if _active is None:
        return None
    handler = MaskingCallbackHandler if _active.masked else CallbackHandler
    return handler(public_key=_active.public_key, trace_context={"trace_id": trace_id_for(run_id)})


def trace_id_for(run_id: UUID) -> str:
    """The trace id a traced run with this root run id gets (32 hex chars)."""
    return Langfuse.create_trace_id(seed=str(run_id))


def flush_tracing(timeout_millis: int = 5_000) -> None:
    """Export finished spans now (bounded)."""
    if _active is not None:
        _active.provider.force_flush(timeout_millis)


def shutdown_tracing(timeout_millis: int = 2_000) -> None:
    """Flush (bounded) and stop tracing; a no-op when it is off."""
    global _active
    if _active is None:
        return
    active, _active = _active, None
    active.provider.force_flush(timeout_millis)
    active.provider.shutdown()
    active.client.shutdown()
