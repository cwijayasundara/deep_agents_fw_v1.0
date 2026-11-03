"""Audit: is what the model was sent recoverable from what we record?

Runs one persisted turn with a RequestCapture attached, then compares each main-agent model
request to the thread's checkpoints, the cost ledger rows and the run's prompt_hash.

    scripts/tenant_env.sh audit-p2 uv run python scripts/audit_model_visible.py \
        --tenant audit-p2 --question "What changed in LangGraph 1.2?" --out evidence/audit/<run>/
"""

from __future__ import annotations

import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from agentkit_config import load_agent
from agentkit_core import Settings
from agentkit_deep import agent_prompt_hash, agent_prompt_id
from agentkit_evals import CapturedRequest, RequestCapture, digest
from agentkit_middleware import BUILTIN_TOOLS
from agentkit_telemetry import run_config
from langchain_core.messages import HumanMessage
from research_agent.agent import new_thread, platform_context
from research_agent.persist import persistence_for, require_tenant, turn_lock
from research_agent.telemetry import ledger_for, tracing

MATCH, DIFFERS, NOT_RECORDED = "match", "differs", "not-recorded"


def _cmp(captured: Any, recorded: Any) -> str:
    if recorded is None:
        return NOT_RECORDED
    return MATCH if captured == recorded else DIFFERS


def _audit_one(
    cap: CapturedRequest,
    states: dict[int, dict[str, Any]],
    usage_models: set[str],
    prompt_hash: str,
) -> dict[str, Any]:
    values = states.get((cap.step or 0) - 1)
    messages = (values or {}).get("messages")
    selection = (values or {}).get("agentkit_selection")
    recorded_tools = (
        tuple(sorted(set(selection["tools"]) | BUILTIN_TOOLS)) if selection is not None else None
    )
    detail: dict[str, Any] = {}
    if recorded_tools is not None and recorded_tools != cap.tools:
        detail["tools_only_sent"] = sorted(set(cap.tools) - set(recorded_tools))
        detail["tools_only_recorded"] = sorted(set(recorded_tools) - set(cap.tools))
    return {
        "step": cap.step,
        "detail": detail,
        "messages": _cmp(cap.messages_sha, digest(messages) if messages is not None else None),
        "tools": _cmp(cap.tools, recorded_tools),
        "model": _cmp(cap.model, cap.model if cap.model in usage_models else None)
        if usage_models
        else NOT_RECORDED,
        "system": _cmp(cap.system_sha, prompt_hash) if cap.system_sha else NOT_RECORDED,
    }


async def _usage_models(p: Any, thread: str) -> set[str]:
    async with p.pool.connection() as conn:
        cur = await conn.execute("select model from agentkit_usage where thread_id = %s", (thread,))
        rows = await cur.fetchall()
    return {m for row in rows for m in row["model"].split(",")}


async def audit(a: argparse.Namespace) -> dict[str, Any]:
    thread = new_thread()
    settings = Settings()
    require_tenant(a.tenant, settings)
    capture = RequestCapture()
    async with persistence_for(True) as p:
        assert p is not None
        loaded = load_agent(a.agent, settings=settings, overrides={"model": a.model}, persistence=p)
        ctx = platform_context(loaded.spec, tenant=a.tenant, user="audit", thread=thread)
        ledger = await ledger_for(p)
        phash = agent_prompt_hash(loaded.graph)
        config = dict(run_config(ctx, phash, ledger, prompt_id=agent_prompt_id(loaded.graph)))
        config["callbacks"] = [*config["callbacks"], capture]
        async with turn_lock(p, thread):
            await loaded.graph.ainvoke(
                {"messages": [HumanMessage(a.question)]}, config=config, context=ctx
            )
        states: dict[int, dict[str, Any]] = {}
        task_calls = 0
        async for snap in loaded.graph.aget_state_history({"configurable": {"thread_id": thread}}):
            step = (snap.metadata or {}).get("step")
            if step is not None:
                states[int(step)] = snap.values
            if not states or snap.next == ():
                task_calls = sum(
                    1
                    for m in snap.values.get("messages", [])
                    for tc in getattr(m, "tool_calls", None) or []
                    if tc["name"] == "task"
                )
        models = await _usage_models(p, thread)
    main = [c for c in capture.records if c.namespace == ""]
    sub = [c for c in capture.records if c.namespace != ""]
    return {
        "thread": thread,
        "prompt_hash": phash,
        "usage_models": sorted(models),
        "main_captures": len(main),
        "subagent_captures": len(sub),
        "task_tool_calls_in_final_state": task_calls,
        "subagent_note": "not in parent checkpoints",
        "captures": [_audit_one(c, states, models, phash) for c in main],
        "_records": [asdict(c) for c in capture.records],
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--tenant", required=True)
    p.add_argument("--question", required=True)
    p.add_argument("--agent", default="apps/research_agent/agent.yaml")
    p.add_argument("--model", default="fireworks-glm")
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    with tracing(Settings()):
        result = asyncio.run(audit(a))
    a.out.mkdir(parents=True, exist_ok=True)
    records = result.pop("_records")
    (a.out / "captures.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records))
    (a.out / "audit.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "captures"}, indent=2))
    for c in result["captures"]:
        print(c)
    if not result["main_captures"]:
        raise SystemExit("no main-agent model calls captured")


if __name__ == "__main__":
    main()
