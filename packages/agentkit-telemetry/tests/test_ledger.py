import asyncio
import json
import uuid
from pathlib import Path

import httpx
import pytest
from agentkit_core import Settings
from agentkit_deep import agent_prompt_hash, build_deep_agent
from agentkit_deep.testing import MeteredChatModel, ctx, tool_call
from agentkit_middleware import DecisionsClient, DecisionsSelector, SelectionMiddleware
from agentkit_middleware.tenant_guard import TenantMismatch
from agentkit_telemetry import CostLedger, UsageRow, run_config, setup
from langchain.tools import tool
from langchain_core.messages import AIMessage, HumanMessage

FIXTURE = (
    Path(__file__).parents[2]
    / "agentkit-middleware/tests/fixtures/decisions_live_short_prompt.json"
)
USAGE = {
    "input_tokens": 10,
    "output_tokens": 3,
    "total_tokens": 13,
    "input_token_details": {"cache_read": 4},
}


@tool
def echo(text: str) -> str:
    """Echo the text back."""
    return text


def _model(runs: int = 1) -> MeteredChatModel:
    steps: list[AIMessage] = []
    for i in range(runs):
        steps += [tool_call("echo", {"text": "hi"}, f"e{i}"), AIMessage(content="done")]
    return MeteredChatModel(messages=iter(steps), usage=USAGE, model_name="scripted-model")


def _agent(model, tenant: str = "acme", middleware=()):
    settings = Settings(_env_file=None, deployment_tenant=tenant)
    return build_deep_agent(
        model=model, system_prompt="p", tools=[echo], middleware=middleware, settings=settings
    )


async def _run(agent, ledger: CostLedger, thread: str, tenant: str = "acme"):
    c = ctx(tenant=tenant, thread_id=thread)
    config = run_config(c, agent_prompt_hash(agent), ledger)
    await agent.ainvoke({"messages": [HumanMessage("go")]}, config, context=c)
    return config["run_id"]


async def test_one_aggregated_row_per_run_with_the_tenant():
    ledger = CostLedger()
    run_id = await _run(_agent(_model()), ledger, "th-1")
    assert ledger.rows == [
        UsageRow(
            tenant="acme",
            thread_id="th-1",
            run_id=run_id,
            model="scripted-model",
            input_tokens=20,
            output_tokens=6,
            cached_input_tokens=8,
            decisions_input_tokens=0,
            decisions_output_tokens=0,
        )
    ]
    assert ledger.row(run_id) == ledger.rows[0]
    assert ledger.row(uuid.uuid4()) is None


async def test_runs_are_kept_apart_even_when_concurrent():
    ledger = CostLedger()
    a, b = _agent(_model()), _agent(_model())
    ids = await asyncio.gather(_run(a, ledger, "th-a"), _run(b, ledger, "th-b"))
    rows = {r.run_id: r for r in ledger.rows}
    assert set(rows) == set(ids) and len(ledger.rows) == 2
    assert {rows[ids[0]].thread_id, rows[ids[1]].thread_id} == {"th-a", "th-b"}
    assert all((r.input_tokens, r.output_tokens) == (20, 6) for r in ledger.rows)


async def test_decisions_usage_lands_in_its_own_columns():
    fixture = json.loads(FIXTURE.read_text())
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=fixture))
    client = DecisionsClient("sk-test", client=httpx.AsyncClient(transport=transport))
    selection = SelectionMiddleware(DecisionsSelector(client))
    ledger = CostLedger()
    run_id = await _run(_agent(_model(), middleware=[selection]), ledger, "th-d")
    row = ledger.row(run_id)
    assert row is not None
    assert (row.decisions_input_tokens, row.decisions_output_tokens) == (686, 0)
    assert (row.input_tokens, row.output_tokens) == (20, 6)


async def test_a_refused_run_writes_no_row():
    ledger = CostLedger()
    agent = _agent(_model(), tenant="acme")
    with pytest.raises(TenantMismatch):
        await _run(agent, ledger, "th-x", tenant="other")
    assert ledger.rows == []


async def test_summary_line_totals_every_run():
    ledger = CostLedger()
    agent = _agent(_model(2))
    await _run(agent, ledger, "th-1")
    await _run(agent, ledger, "th-2")
    assert ledger.summary() == (
        "usage: 2 runs, 4 model calls, input 40 (cached 16), output 12, decisions input 0"
    )


@pytest.mark.pg
async def test_rows_are_written_to_postgres(persistence):
    await setup(persistence)
    await setup(persistence)  # idempotent
    ledger = CostLedger(persistence)
    thread = f"ledger-{uuid.uuid4()}"
    run_ids = [await _run(_agent(_model()), ledger, thread) for _ in range(3)]
    async with persistence.pool.connection() as conn:
        cur = await conn.execute(
            "select tenant, thread_id, run_id, model, input_tokens, output_tokens,"
            " cached_input_tokens from agentkit_usage where thread_id = %s order by created_at",
            (thread,),
        )
        rows = await cur.fetchall()
    assert [r["run_id"] for r in rows] == run_ids
    assert {(r["tenant"], r["model"]) for r in rows} == {("acme", "scripted-model")}
    assert [(r["input_tokens"], r["output_tokens"], r["cached_input_tokens"]) for r in rows] == [
        (20, 6, 8)
    ] * 3
