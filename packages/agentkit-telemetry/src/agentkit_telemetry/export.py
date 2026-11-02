"""Export-side helpers: payload masking and a span exporter that fails quietly and fast.

Both run on the batch span processor's worker thread (or at flush/shutdown), never on the
run's own path.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from collections.abc import Sequence

from langfuse.types import (
    MaskOtelSpansParams,
    MaskOtelSpansResult,
    OtelSpanIdentifier,
    OtelSpanPatch,
)
from opentelemetry.sdk.trace import Event, ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult
from opentelemetry.trace import Status

log = logging.getLogger(__name__)

MASKED_ATTR = "agentkit.payload.masked"
STATUS_MESSAGE_ATTR = "langfuse.observation.status_message"
# Exception event attributes that carry error text (`exception.type` is kept).
_EXCEPTION_TEXT = frozenset({"exception.message", "exception.stacktrace", "exception.escaped"})
REDACTED = "redacted"
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


# What an exception class name looks like. A status text is kept only when it has this shape or
# names an exception recorded on the same span; any other text (e.g. an error ToolMessage's
# content, which upstream Langfuse copies into the status as is) may carry user data or secrets.
_EXCEPTION_NAME = re.compile(
    r"[A-Z][A-Za-z0-9]*(Error|Exception|Exit|Interrupt|Cancelled|Mismatch)"
)


def _is_type_name(text: str, recorded: frozenset[str] = frozenset()) -> bool:
    return text in recorded or _EXCEPTION_NAME.fullmatch(text) is not None


def mask_payloads(*, params: MaskOtelSpansParams) -> MaskOtelSpansResult:
    """Drop prompt/completion attributes from every span; mark the spans that lost some.

    An error status message is kept only when it is shaped like an exception class name (what
    `MaskingCallbackHandler` writes); any other text is replaced by "redacted". Span events are
    not visible here, so `redact_errors` makes the same check against recorded exception types."""
    patches: dict[OtelSpanIdentifier, OtelSpanPatch | None] = {}
    for ident, span in params.spans.items():
        drop = tuple(
            k for k in span.attributes if k in _PAYLOAD_KEYS or k.startswith(_PAYLOAD_PREFIXES)
        )
        status = span.attributes.get(STATUS_MESSAGE_ATTR)
        reword = isinstance(status, str) and not _is_type_name(status)
        if drop or reword:
            sets: dict[str, bool | str] = {MASKED_ATTR: True}
            if reword:
                sets[STATUS_MESSAGE_ATTR] = REDACTED
            patches[ident] = OtelSpanPatch(delete_attributes=drop, set_attributes=sets)
    return MaskOtelSpansResult(span_patches=patches)


def redact_errors(spans: Sequence[ReadableSpan]) -> list[ReadableSpan]:
    """Copies of `spans` without error text: the status description is kept only when it is an
    exception type name (one recorded in the span's `exception.type` events, or shaped like an
    exception class), else the span's type-name status message, else "redacted"; exception
    events keep only `exception.type`.

    `mask_otel_spans` can patch attributes only, so this runs in the exporter."""
    out: list[ReadableSpan] = []
    for span in spans:
        desc = span.status.description
        texty = [e for e in span.events if _EXCEPTION_TEXT & set(e.attributes or {})]
        if not desc and not texty:
            out.append(span)
            continue
        recorded = frozenset(
            t
            for e in span.events
            if isinstance(t := (e.attributes or {}).get("exception.type"), str)
        )
        status_attr = (span.attributes or {}).get(STATUS_MESSAGE_ATTR)
        kept = [t for t in (desc, status_attr) if isinstance(t, str) and _is_type_name(t, recorded)]
        name = kept[0] if kept else REDACTED
        events = [
            Event(
                e.name,
                {k: v for k, v in (e.attributes or {}).items() if k not in _EXCEPTION_TEXT},
                e.timestamp,
            )
            if e in texty
            else e
            for e in span.events
        ]
        out.append(
            ReadableSpan(
                name=span.name,
                context=span.context,
                parent=span.parent,
                resource=span.resource,
                attributes=span.attributes,
                events=events,
                links=span.links,
                kind=span.kind,
                status=Status(span.status.status_code, name if desc else None),
                start_time=span.start_time,
                end_time=span.end_time,
                instrumentation_scope=span.instrumentation_scope,
            )
        )
    return out


class QuietExporter(SpanExporter):
    """Wraps an exporter: logs the first failure once, then drops batches for `cooldown` seconds
    instead of retrying, so a dead collector costs one warning and never stalls shutdown.
    With `redact`, error text is stripped first (`redact_errors`)."""

    def __init__(
        self, inner: SpanExporter, where: str, cooldown: float = 30.0, *, redact: bool = False
    ) -> None:
        self._inner, self._where, self._cooldown = inner, where, cooldown
        self._redact = redact  # strip error text (status description, exception events)
        self._down_until = 0.0
        self._warned = False
        self._lock = threading.Lock()

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        if time.monotonic() < self._down_until:
            return SpanExportResult.FAILURE
        try:
            result = self._inner.export(redact_errors(spans) if self._redact else spans)
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
