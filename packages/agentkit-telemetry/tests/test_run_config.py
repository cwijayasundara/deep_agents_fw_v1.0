import hashlib
import json
import logging
import os
import time
import uuid

from agentkit_core import Settings
from agentkit_deep import agent_prompt_hash, build_deep_agent
from agentkit_deep.testing import MeteredChatModel, ctx
from agentkit_telemetry import (
    CostLedger,
    TelemetrySettings,
    configure_tracing,
    run_config,
    shutdown_tracing,
    trace_id,
)
from langchain_core.messages import AIMessage, HumanMessage

PROMPT = "the scripted question nobody should see in a span"
ANSWER = "the scripted answer nobody should see in a span"


def _ctx():
    return ctx(user_id="u7", thread_id="th-42", agent_name="researcher", agent_version="3")


def _agent(prompt: str = "be brief"):
    model = MeteredChatModel(messages=iter([AIMessage(content=ANSWER)]))
    return build_deep_agent(model=model, system_prompt=prompt, settings=Settings(_env_file=None))


def test_metadata_carries_every_context_key_and_the_prompt_hash():
    config = run_config(_ctx(), "abc123", CostLedger())
    assert config["metadata"] == {
        "tenant": "default",
        "product": "agentkit",
        "team": "platform",
        "user_id": "u7",
        "thread_id": "th-42",
        "agent_name": "researcher",
        "agent_version": "3",
        "prompt_hash": "abc123",
        "langfuse_user_id": "u7",
        "langfuse_session_id": "th-42",
        "langfuse_tags": ["tenant:default", "agent:researcher"],
    }


def test_thread_id_run_id_and_ledger_callback():
    ledger = CostLedger()
    config = run_config(_ctx(), "h", ledger)
    assert config["configurable"] == {"thread_id": "th-42"}
    assert isinstance(config["run_id"], uuid.UUID)
    assert run_config(_ctx(), "h", ledger)["run_id"] != config["run_id"]
    assert config["callbacks"] == [ledger]  # tracing is off: no Langfuse handler
    assert trace_id(config) is None


def test_tracing_is_off_without_an_endpoint():
    assert TelemetrySettings().otlp_endpoint is None
    assert configure_tracing(TelemetrySettings()) is None


def test_settings_read_the_otel_endpoint_and_payload_switch(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4318")
    monkeypatch.setenv("AGENTKIT_TRACE_PAYLOADS", "1")
    monkeypatch.setenv("AGENTKIT_TENANT", "acme")
    s = TelemetrySettings.from_env(env_file=None)
    assert (s.otlp_endpoint, s.trace_payloads, s.tenant) == ("http://127.0.0.1:4318", True, "acme")


def test_prompt_hash_is_sha256_of_the_system_prompt_and_stable():
    want = hashlib.sha256(b"be brief").hexdigest()
    assert agent_prompt_hash(_agent()) == want
    assert agent_prompt_hash(_agent()) == want
    assert agent_prompt_hash(_agent("be long")) != want
    assert agent_prompt_hash(object()) == ""  # not a factory agent


async def test_spans_carry_tenant_user_session_and_prompt_hash(traced):
    agent = _agent()
    config = run_config(_ctx(), agent_prompt_hash(agent), CostLedger())
    await agent.ainvoke({"messages": [HumanMessage(PROMPT)]}, config, context=_ctx())
    spans = traced()
    assert spans, "no spans exported"
    assert {s.resource.attributes.get("agentkit.tenant") for s in spans} == {"default"}
    attrs = [dict(s.attributes) for s in spans]
    assert any(a.get("user.id") == "u7" and a.get("session.id") == "th-42" for a in attrs)
    hashes = {a.get("langfuse.trace.metadata.prompt_hash") for a in attrs} - {None}
    assert hashes == {json.dumps(agent_prompt_hash(agent))}
    assert {format(s.context.trace_id, "032x") for s in spans} == {trace_id(config)}


async def test_prompt_and_completion_are_masked_by_default(traced):
    agent = _agent()
    config = run_config(_ctx(), agent_prompt_hash(agent), CostLedger())
    await agent.ainvoke({"messages": [HumanMessage(PROMPT)]}, config, context=_ctx())
    dumped = json.dumps([dict(s.attributes) for s in traced()], default=str)
    assert PROMPT not in dumped and ANSWER not in dumped
    assert "agentkit.payload.masked" in dumped


async def test_payloads_appear_only_when_opted_in(traced_payloads):
    agent = _agent()
    config = run_config(_ctx(), agent_prompt_hash(agent), CostLedger())
    await agent.ainvoke({"messages": [HumanMessage(PROMPT)]}, config, context=_ctx())
    dumped = json.dumps([dict(s.attributes) for s in traced_payloads()], default=str)
    assert PROMPT in dumped and ANSWER in dumped


async def test_no_langsmith_tracing_and_no_env_in_spans(traced, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-should-not-leak")
    assert "LANGSMITH_TRACING" not in os.environ
    agent = _agent()
    config = run_config(_ctx(), agent_prompt_hash(agent), CostLedger())
    await agent.ainvoke({"messages": [HumanMessage(PROMPT)]}, config, context=_ctx())
    dumped = json.dumps(
        [{**dict(s.attributes), **dict(s.resource.attributes)} for s in traced()], default=str
    )
    assert "LANGSMITH_" not in dumped and "_API_KEY" not in dumped
    assert "sk-should-not-leak" not in dumped
    assert "LANGSMITH_TRACING" not in os.environ


async def test_dead_collector_costs_one_warning_and_no_stall(caplog):
    caplog.set_level(logging.WARNING)
    configure_tracing(
        TelemetrySettings(otlp_endpoint="http://127.0.0.1:9", export_timeout_seconds=1.0)
    )
    agent = _agent()
    config = run_config(_ctx(), agent_prompt_hash(agent), CostLedger())
    start = time.monotonic()
    out = await agent.ainvoke({"messages": [HumanMessage(PROMPT)]}, config, context=_ctx())
    ran = time.monotonic() - start
    shutdown_tracing()
    total = time.monotonic() - start
    assert out["messages"][-1].content == ANSWER
    assert ran < 1.0 and total < 3.0
    export = [r for r in caplog.records if "export" in r.getMessage().lower()]
    assert len(export) == 1, [r.getMessage() for r in export]


def _error_dump(spans) -> str:
    """Every place error text can reach an exported span: attributes, status, events."""
    return json.dumps(
        [
            {
                "attrs": dict(s.attributes),
                "status": s.status.description,
                "events": [(e.name, dict(e.attributes)) for e in s.events],
            }
            for s in spans
        ],
        default=str,
    )


async def _run_erroring_tools():
    from agentkit_deep.testing import tool_call
    from langchain.tools import tool

    @tool
    def boom(text: str) -> str:
        """Raise with the user's text in the message."""
        raise ValueError(f"cannot handle {text}")

    @tool
    def typed(n: int) -> str:
        """Takes an int."""
        return str(n)

    model = MeteredChatModel(
        messages=iter(
            [
                tool_call("typed", {"n": "SECRET-USER-TEXT-1"}, "a"),
                tool_call("boom", {"text": "SECRET-USER-TEXT-2"}, "b"),
                AIMessage(content="done"),
            ]
        )
    )
    agent = build_deep_agent(
        model=model, system_prompt="p", tools=[boom, typed], settings=Settings(_env_file=None)
    )
    config = run_config(_ctx(), agent_prompt_hash(agent), CostLedger())
    try:
        await agent.ainvoke({"messages": [HumanMessage("go")]}, config, context=_ctx())
    except ValueError:
        pass


async def test_error_text_is_masked_by_default_keeping_the_exception_type(traced):
    await _run_erroring_tools()
    spans = traced()
    dumped = _error_dump(spans)
    assert "SECRET-USER-TEXT" not in dumped
    statuses = {s.attributes.get("langfuse.observation.status_message") for s in spans} - {None}
    assert {"ValidationError", "ValueError"} <= statuses
    assert {s.status.description for s in spans} - {None} <= statuses


async def test_error_text_appears_only_when_payloads_are_opted_in(traced_payloads):
    await _run_erroring_tools()
    dumped = _error_dump(traced_payloads())
    assert "SECRET-USER-TEXT-1" in dumped and "cannot handle SECRET-USER-TEXT-2" in dumped


def test_exporter_strips_exception_text_from_status_and_events():
    from agentkit_telemetry.export import redact_errors
    from opentelemetry.sdk.trace import Event, ReadableSpan
    from opentelemetry.trace import Status, StatusCode

    span = ReadableSpan(
        name="tool",
        attributes={"langfuse.observation.status_message": "ValueError"},
        status=Status(StatusCode.ERROR, "cannot handle SECRET"),
        events=[
            Event(
                "exception",
                {
                    "exception.type": "ValueError",
                    "exception.message": "cannot handle SECRET",
                    "exception.stacktrace": "Traceback ... SECRET",
                },
            )
        ],
    )
    (clean,) = redact_errors([span])
    assert clean.status.status_code is StatusCode.ERROR
    assert clean.status.description == "ValueError"
    assert dict(clean.events[0].attributes) == {"exception.type": "ValueError"}
    assert "SECRET" not in _error_dump([clean])


TOOL_ERRORS = ("hunter2", "sk_live_abc123")


async def _run_tool_returning_error_messages():
    """Tools that return an error ToolMessage (no exception): upstream Langfuse copies its
    content into the status message without calling the masking hook."""
    from typing import Annotated

    from agentkit_deep.testing import tool_call
    from langchain.tools import InjectedToolCallId, tool
    from langchain_core.messages import ToolMessage

    @tool
    def login(user: str, tool_call_id: Annotated[str, InjectedToolCallId]) -> ToolMessage:
        """Log in."""
        return ToolMessage(content=TOOL_ERRORS[0], tool_call_id=tool_call_id, status="error")

    @tool
    def charge(amount: int, tool_call_id: Annotated[str, InjectedToolCallId]) -> ToolMessage:
        """Charge a card."""
        return ToolMessage(content=TOOL_ERRORS[1], tool_call_id=tool_call_id, status="error")

    model = MeteredChatModel(
        messages=iter(
            [
                tool_call("login", {"user": "u"}, "a"),
                tool_call("charge", {"amount": 3}, "b"),
                AIMessage(content="done"),
            ]
        )
    )
    agent = build_deep_agent(
        model=model, system_prompt="p", tools=[login, charge], settings=Settings(_env_file=None)
    )
    config = run_config(_ctx(), agent_prompt_hash(agent), CostLedger())
    await agent.ainvoke({"messages": [HumanMessage("go")]}, config, context=_ctx())


async def test_one_token_tool_error_text_is_masked_by_default(traced):
    await _run_tool_returning_error_messages()
    dumped = _error_dump(traced())
    for text in TOOL_ERRORS:
        assert text not in dumped
    assert '"redacted"' in dumped


async def test_one_token_tool_error_text_appears_when_payloads_are_opted_in(traced_payloads):
    await _run_tool_returning_error_messages()
    spans = traced_payloads()
    statuses = {s.status.description for s in spans} | {
        s.attributes.get("langfuse.observation.status_message") for s in spans
    }
    assert set(TOOL_ERRORS) <= statuses


def test_status_text_is_kept_only_as_an_exception_type_name():
    from agentkit_telemetry.export import redact_errors
    from opentelemetry.sdk.trace import Event, ReadableSpan
    from opentelemetry.trace import Status, StatusCode

    def described(desc: str, event_type: str | None = None) -> str | None:
        events = [Event("exception", {"exception.type": event_type})] if event_type else []
        span = ReadableSpan(
            name="t", status=Status(StatusCode.ERROR, desc), events=events, attributes={}
        )
        return redact_errors([span])[0].status.description

    assert described("hunter2") == "redacted"
    assert described("sk_live_abc") == "redacted"
    assert described("Secret") == "redacted"  # an identifier, but not an exception shape
    assert described("ValueError") == "ValueError"
    assert described("KeyboardInterrupt") == "KeyboardInterrupt"
    assert described("TenantMismatch") == "TenantMismatch"
    assert described("StopIteration") == "redacted"
    assert described("StopIteration", "StopIteration") == "StopIteration"


def test_mask_payloads_keeps_only_exception_shaped_status_messages():
    from agentkit_telemetry.export import mask_payloads
    from langfuse.types import MaskOtelSpansParams, OtelSpanData, OtelSpanIdentifier

    def masked(status: str) -> str:
        ident = OtelSpanIdentifier(trace_id="0" * 32, span_id="1" * 16)
        data = OtelSpanData(
            trace_id="0" * 32,
            span_id="1" * 16,
            parent_span_id=None,
            name="t",
            instrumentation_scope_name="x",
            instrumentation_scope_version=None,
            attributes={"langfuse.observation.status_message": status},
            resource_attributes={},
        )
        result = mask_payloads(params=MaskOtelSpansParams(spans={ident: data}))
        patch = result.span_patches.get(ident)
        sets = dict(patch.set_attributes) if patch else {}
        return sets.get("langfuse.observation.status_message", status)

    assert masked("hunter2") == "redacted"
    assert masked("sk_live_abc") == "redacted"
    assert masked("ValidationError") == "ValidationError"
