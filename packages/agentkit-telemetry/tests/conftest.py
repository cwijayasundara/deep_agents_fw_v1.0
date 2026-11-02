"""Shared fixtures: an in-memory span exporter behind `configure_tracing`, and pg settings.

`pg` tests use AGENTKIT_TEST_DATABASE_URL and skip (naming that variable) when it is unset.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator

import pytest
from agentkit_persistence import Persistence, PersistenceSettings, open_persistence
from agentkit_telemetry import TelemetrySettings, configure_tracing, shutdown_tracing
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic import SecretStr


@pytest.fixture(autouse=True)
def _no_ambient_telemetry(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for var in ("OTEL_EXPORTER_OTLP_ENDPOINT", "AGENTKIT_TRACE_PAYLOADS", "AGENTKIT_TENANT"):
        monkeypatch.delenv(var, raising=False)
    yield
    shutdown_tracing()


class Spans:
    """Finished spans of the in-memory exporter (flushed on read)."""

    def __init__(self, exporter: InMemorySpanExporter) -> None:
        self.exporter = exporter

    def __call__(self) -> list:  # type: ignore[type-arg]
        from agentkit_telemetry.tracing import flush_tracing

        flush_tracing()
        return list(self.exporter.get_finished_spans())


@pytest.fixture
def traced() -> Iterator[Spans]:
    """Tracing on for tenant `default`, payloads masked, spans kept in memory."""
    exporter = InMemorySpanExporter()
    configure_tracing(TelemetrySettings(tenant="default"), exporter=exporter)
    yield Spans(exporter)


@pytest.fixture
def traced_payloads() -> Iterator[Spans]:
    exporter = InMemorySpanExporter()
    configure_tracing(TelemetrySettings(tenant="default", trace_payloads=True), exporter=exporter)
    yield Spans(exporter)


@pytest.fixture
async def persistence() -> AsyncIterator[Persistence]:
    url = os.environ.get("AGENTKIT_TEST_DATABASE_URL", "")
    if not url:
        pytest.skip("AGENTKIT_TEST_DATABASE_URL is not set")
    settings = PersistenceSettings.model_validate(
        {
            "database_url": SecretStr(url),
            "langgraph_aes_key": SecretStr("0123456789abcdef0123456789abcdef"),
        }
    )
    async with open_persistence(settings) as p:
        yield p
