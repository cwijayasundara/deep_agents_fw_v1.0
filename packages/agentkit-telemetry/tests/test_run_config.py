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
