from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
import uuid
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any

from agentkit_config import load_agent, read_output
from agentkit_core import ConfigError, ModelRegistry, Settings, get_model
from agentkit_deep import agent_prompt_hash
from agentkit_evals import LLMJudge, RunResult, aggregate, load_dataset, run_eval, to_markdown
from agentkit_middleware import TenantMismatch
from agentkit_telemetry import run_config, trace_id
from langchain_core.messages import HumanMessage

from .agent import add_agent_args, exit_on_spec_errors, new_thread, overrides_from, platform_context
from .persist import PERSIST_HELP, persistence_for, require_tenant, turn_lock
from .progress import run_with_progress, setup_logging
from .telemetry import ledger_for, tracing, usage_of

log = logging.getLogger("research_agent")


async def evaluate(
    agent_path: str | Path,
    overrides: Mapping[str, str],
    dataset: str,
    judge_entry: str,
    *,
    tenant: str = "default",
    user: str | None = None,
    persist: bool = False,
) -> tuple[str, dict[str, Any]]:
    """Run every case on its own thread; with `persist`, each thread is checkpointed and locked.

    Without an explicit `user`, a persisted eval runs as a fresh `eval-<hex>` user per invocation,
    so `/memories/` from interactive runs or earlier evals never reach its prompts (Ruling P9).

    Every case would run under `tenant`, so another deployment's tenant is a configuration error
    (`ConfigError`, exit 2) raised before any case runs, persisted or not (Ruling P4)."""
    settings = Settings()
    try:
        require_tenant(tenant, settings)
    except TenantMismatch as e:
        raise ConfigError(f"TenantMismatch: {e}") from None
    user = user or (f"eval-{uuid.uuid4().hex[:8]}" if persist else "local")
    print(f"eval user: {user}", flush=True)
    first = load_agent(agent_path, settings=settings, overrides=overrides)  # fail fast on bad specs
    judge = LLMJudge(get_model(ModelRegistry.default().resolve(judge_entry, "strong"), settings))
    spec = first.model_spec
    log.info(
        "agent %s -> %s %s (tier=%s, selection=%s)",
        agent_path,
        spec.provider,
        spec.model_id,
        first.spec.tier,
        first.spec.selection or "off",
    )

    async with persistence_for(persist) as p:
        ledger = await ledger_for(p)

        async def run_agent(question: str) -> RunResult:
            loaded = load_agent(agent_path, settings=settings, overrides=overrides, persistence=p)
            ctx = platform_context(loaded.spec, tenant=tenant, user=user, thread=new_thread())
            log.info("eval thread %s: %s", ctx.thread_id, question)
            config = run_config(ctx, agent_prompt_hash(loaded.graph), ledger)
            seen: list[str] = []  # every tool result, orchestrator and subagents
            calls: list[str] = []
            started = time.monotonic()
            async with turn_lock(p, ctx.thread_id):
                res = await run_with_progress(
                    loaded.graph,
                    {"messages": [HumanMessage(question)]},
                    config=dict(config),
                    context=ctx,
                    tool_outputs=seen,
                    tool_calls=calls,
                )
            latency = time.monotonic() - started
            return RunResult(
                report=read_output(res, loaded.spec.output),
                retrieved="\n".join(seen),
                run_id=str(config["run_id"]),
                trace_id=trace_id(config),
                usage=usage_of(ledger, config["run_id"]),
                tool_calls=calls,
                latency_s=latency,
            )

        results = await run_eval(load_dataset(dataset), run_agent, judge)
    print(ledger.summary())
    md = f"## {first.spec.model} (judge: {judge_entry})\n\n{to_markdown(results)}\n"
    summary = {
        "agent": str(agent_path),
        "overrides": dict(overrides),
        "model": first.spec.model,
        "tier": first.spec.tier,
        "selection": first.spec.selection,
        "judge": judge_entry,
        "persist": persist,
        "aggregate": aggregate(results),
        "cases": [asdict(r) for r in results],
    }
    return md, summary


def _main() -> None:
    p = argparse.ArgumentParser(prog="research-eval")
    add_agent_args(p)
    p.add_argument("--persist", action="store_true", help=PERSIST_HELP)
    p.set_defaults(user=None)
    for action in p._actions:
        if action.dest == "user":
            action.help = "user id (default: local; with --persist a fresh eval-<hex> per run)"
    p.add_argument("--dataset", default="apps/research_agent/evals/smoke.jsonl")
    p.add_argument("--judge", default="anthropic", help="registry entry used as the judge model")
    p.add_argument("--out", type=Path, default=Path("eval_results.md"))
    p.add_argument("-v", "--verbose", action="store_true", help="debug logs (tool output, tokens)")
    p.add_argument("-q", "--quiet", action="store_true", help="warnings only")
    a = p.parse_args()
    setup_logging(-1 if a.quiet else 1 if a.verbose else 0)
    with tracing(Settings()):
        md, summary = asyncio.run(
            evaluate(
                a.agent,
                overrides_from(a),
                a.dataset,
                a.judge,
                tenant=a.tenant,
                user=a.user,
                persist=a.persist,
            )
        )
    a.out.write_text(md)
    a.out.with_suffix(".json").write_text(json.dumps(summary, indent=2))
    print(md)


def main() -> None:
    exit_on_spec_errors(_main)
