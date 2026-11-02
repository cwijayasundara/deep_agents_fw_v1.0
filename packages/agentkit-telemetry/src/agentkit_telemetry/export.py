"""Export-side helpers: payload masking and a span exporter that fails quietly and fast.

Both run on the batch span processor's worker thread (or at flush/shutdown), never on the
run's own path.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Sequence

from langfuse.types import (
    MaskOtelSpansParams,
    MaskOtelSpansResult,
    OtelSpanIdentifier,
    OtelSpanPatch,
)
from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

log = logging.getLogger(__name__)

MASKED_ATTR = "agentkit.payload.masked"
# Where prompt and completion text can land on a span (Langfuse and GenAI conventions).
_PAYLOAD_KEYS = frozenset(
    {
        "langfuse.observation.input",
        "langfuse.observation.output",
        "langfuse.trace.input",
        "langfuse.trace.output",
    }
)
_PAYLOAD_PREFIXES = (
    "gen_ai.prompt",
    "gen_ai.completion",
    "gen_ai.input.messages",
    "gen_ai.output.messages",
    "gen_ai.system_instructions",
)


def mask_payloads(*, params: MaskOtelSpansParams) -> MaskOtelSpansResult:
    """Drop prompt/completion attributes from every span; mark the spans that lost some."""
    patches: dict[OtelSpanIdentifier, OtelSpanPatch | None] = {}
    for ident, span in params.spans.items():
        drop = tuple(
            k for k in span.attributes if k in _PAYLOAD_KEYS or k.startswith(_PAYLOAD_PREFIXES)
        )
        if drop:
            patches[ident] = OtelSpanPatch(
                delete_attributes=drop, set_attributes={MASKED_ATTR: True}
            )
    return MaskOtelSpansResult(span_patches=patches)


class QuietExporter(SpanExporter):
    """Wraps an exporter: logs the first failure once, then drops batches for `cooldown` seconds
    instead of retrying, so a dead collector costs one warning and never stalls shutdown."""

    def __init__(self, inner: SpanExporter, where: str, cooldown: float = 30.0) -> None:
        self._inner, self._where, self._cooldown = inner, where, cooldown
        self._down_until = 0.0
        self._warned = False
        self._lock = threading.Lock()

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        if time.monotonic() < self._down_until:
            return SpanExportResult.FAILURE
        try:
            result = self._inner.export(spans)
            reason = "not delivered"
        except Exception as e:  # the exporter must never raise into the processor
            result, reason = SpanExportResult.FAILURE, type(e).__name__
        if result is not SpanExportResult.SUCCESS:
            self._down_until = time.monotonic() + self._cooldown
            with self._lock:
                first, self._warned = not self._warned, True
            if first:
                log.warning(
                    "trace export to %s failed (%s); dropping spans, further export errors"
                    " are not logged",
                    self._where,
                    reason,
                )
        return result

    def shutdown(self) -> None:
        self._inner.shutdown()

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        return self._inner.force_flush(timeout_millis)
