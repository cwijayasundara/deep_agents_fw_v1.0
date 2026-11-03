from __future__ import annotations

import argparse
import asyncio
import logging
from collections.abc import Mapping
from pathlib import Path

from agentkit_config import load_agent, read_output
from agentkit_core import Settings
from agentkit_deep import agent_prompt_hash, agent_prompt_id
from agentkit_telemetry import run_config, trace_id
from langchain_core.messages import HumanMessage

from .agent import add_agent_args, exit_on_spec_errors, new_thread, overrides_from, platform_context
from .persist import PERSIST_HELP, persistence_for, require_tenant, resumed_step, turn_lock
from .progress import run_with_progress, setup_logging
from .telemetry import ledger_for, tracing

log = logging.getLogger("research_agent")


async def run(
    question: str,
    agent_path: str | Path,
    overrides: Mapping[str, str],
    *,
    tenant: str = "default",
    user: str = "local",
    thread: str | None = None,
    persist: bool = False,
) -> str:
    """One research turn. With `persist`, the turn runs in the thread's lock and resumes it."""
    thread = thread or new_thread()
    print(f"thread: {thread}", flush=True)
    settings = Settings()
    log.info("env file: %s", settings.env_file_used() or "none found (using process env)")
    log.info("keys set: %s", ", ".join(settings.keys_present()) or "none")
    if persist:
        require_tenant(tenant, settings)
    async with persistence_for(persist) as p:
        loaded = load_agent(agent_path, settings=settings, overrides=overrides, persistence=p)
        spec = loaded.model_spec
        log.info(
            "agent %s -> %s %s (tier=%s, selection=%s)",
            agent_path,
            spec.provider,
            spec.model_id,
            loaded.spec.tier,
            loaded.spec.selection or "off",
        )
        ctx = platform_context(loaded.spec, tenant=tenant, user=user, thread=thread)
        log.info("run: tenant=%s user=%s thread=%s", ctx.tenant, ctx.user_id, ctx.thread_id)
        log.info("question: %s", question)
        ledger = await ledger_for(p)
        config = run_config(
            ctx, agent_prompt_hash(loaded.graph), ledger, prompt_id=agent_prompt_id(loaded.graph)
        )
        async with turn_lock(p, thread):
            if p is not None and (step := await resumed_step(loaded.graph, thread)) is not None:
                print(f"resumed thread {thread} at step {step}", flush=True)
            result = await run_with_progress(
                loaded.graph,
                {"messages": [HumanMessage(question)]},
                config=dict(config),
                context=ctx,
            )
    if (trace := trace_id(config)) is not None:
        print(f"trace: {trace}")
    print(ledger.summary())
    report = read_output(result, loaded.spec.output)
    if not report:
        raise SystemExit("agent finished without writing /report.md")
    return report


def _main() -> None:
    p = argparse.ArgumentParser(prog="research")
    p.add_argument("question")
    add_agent_args(p)
    p.add_argument("--persist", action="store_true", help=PERSIST_HELP)
    p.add_argument(
        "--thread",
        help="thread to resume (needs --persist; default: a new uuid4, printed)",
    )
    p.add_argument("--out", type=Path, default=Path("report.md"))
    p.add_argument("-v", "--verbose", action="store_true", help="debug logs (tool output, tokens)")
    p.add_argument("-q", "--quiet", action="store_true", help="warnings only")
    a = p.parse_args()
    if a.thread and not a.persist:
        p.error("--thread resumes a persisted thread; add --persist (needs DATABASE_URL)")
    setup_logging(-1 if a.quiet else 1 if a.verbose else 0)
    with tracing(Settings()):
        report = asyncio.run(
            run(
                a.question,
                a.agent,
                overrides_from(a),
                tenant=a.tenant,
                user=a.user,
                thread=a.thread,
                persist=a.persist,
            )
        )
    a.out.write_text(report)
    log.info("wrote %s (%d chars)", a.out, len(report))
    print(f"wrote {a.out}")


def main() -> None:
    exit_on_spec_errors(_main)
