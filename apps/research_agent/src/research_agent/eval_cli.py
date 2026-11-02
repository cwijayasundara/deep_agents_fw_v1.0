from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import sys
import time
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

from agentkit_config import load_agent, read_output
from agentkit_core import ConfigError, ModelRegistry, Settings, get_model
from agentkit_deep import agent_prompt_hash, agent_prompt_id
from agentkit_evals import (
    Baseline,
    BaselineMismatch,
    LLMJudge,
    RunResult,
    aggregate,
    check_gates,
    load_dataset,
    load_gates,
    run_eval,
    select_cases,
    to_markdown,
)
from agentkit_middleware import TenantMismatch
from agentkit_telemetry import run_config, trace_id
from langchain_core.messages import HumanMessage
from pydantic import ValidationError

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
    case_ids: Sequence[str] = (),
    tags: Sequence[str] = (),
    concurrency: int = 6,
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
    try:
        cases = select_cases(load_dataset(dataset), case_ids, tags)
    except ValueError as e:
        raise ConfigError(f"{dataset}: {e}") from None
    user = user or (f"eval-{uuid.uuid4().hex[:8]}" if persist else "local")
    print(f"eval user: {user}", flush=True)
    first = load_agent(agent_path, settings=settings, overrides=overrides)  # fail fast on bad specs
    judge_spec = ModelRegistry.default().resolve(judge_entry, "strong")
    judge = LLMJudge(get_model(judge_spec, settings))
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
            config = run_config(
                ctx,
                agent_prompt_hash(loaded.graph),
                ledger,
                prompt_id=agent_prompt_id(loaded.graph),
            )
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

        results = await run_eval(cases, run_agent, judge, concurrency=concurrency)
    print(ledger.summary())
    md = f"## {first.spec.model} (judge: {judge_entry})\n\n{to_markdown(results)}\n"
    summary = {
        "agent": str(agent_path),
        "overrides": dict(overrides),
        "model": first.spec.model,
        "tier": first.spec.tier,
        "selection": first.spec.selection,
        "judge": judge_entry,
        "model_id": spec.model_id,
        "judge_model_id": judge_spec.model_id,
        "dataset": dataset,
        "persist": persist,
        **({"subset": {"cases": list(case_ids), "tags": list(tags)}} if case_ids or tags else {}),
        "aggregate": aggregate(results),
        "cases": [asdict(r) for r in results],
    }
    return md, summary


def _positive_int(v: str) -> int:
    try:
        n = int(v)
    except ValueError:
        n = 0
    if n < 1:
        raise argparse.ArgumentTypeError(f"must be a positive integer, got {v!r}")
    return n


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
    p.add_argument(
        "--case",
        action="append",
        default=[],
        dest="case_ids",
        metavar="ID",
        help="run only this case id (repeatable; not with --gate)",
    )
    p.add_argument(
        "--tag",
        action="append",
        default=[],
        dest="tags",
        help="run only cases with this tag (repeatable; not with --gate)",
    )
    p.add_argument(
        "--concurrency", type=_positive_int, default=6, help="cases run at once (default 6)"
    )
    p.add_argument("--out", type=Path, default=Path("eval_results.md"))
    p.add_argument("--gate", type=Path, help="gates YAML; exit 1 on a regression vs its baseline")
    p.add_argument(
        "--write-baseline", action="store_true", help="record this run as the gate baseline"
    )
    p.add_argument("-v", "--verbose", action="store_true", help="debug logs (tool output, tokens)")
    p.add_argument("-q", "--quiet", action="store_true", help="warnings only")
    a = p.parse_args()
    if a.write_baseline and not a.gate:
        p.error("--write-baseline requires --gate")
    if a.gate and (a.case_ids or a.tags):
        p.error("--case/--tag run a subset; --gate needs the full dataset")
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
                case_ids=a.case_ids,
                tags=a.tags,
                concurrency=a.concurrency,
            )
        )
    a.out.write_text(md)
    a.out.with_suffix(".json").write_text(json.dumps(summary, indent=2))
    print(md)
    if a.gate:
        _gate(a, summary)


def _gate(a: argparse.Namespace, summary: dict[str, Any]) -> None:
    spec = load_gates(a.gate)
    if a.write_baseline:
        errored = [c["case_id"] for c in summary["cases"] if c.get("error")]
        if errored:
            print(f"gate: refusing to write baseline, cases errored: {errored}", file=sys.stderr)
            raise SystemExit(2)
        nan = sorted(k for k, v in summary["aggregate"].items() if math.isnan(v))
        if nan:
            print(f"gate: refusing to write baseline, NaN metrics: {nan}", file=sys.stderr)
            raise SystemExit(2)
        spec.baseline.write_text(
            Baseline.from_summary(summary, Path(a.dataset)).model_dump_json(indent=2)
        )
        print(f"gate: baseline written to {spec.baseline}")
        return
    if not spec.baseline.exists():
        print(
            f"gate: no baseline at {spec.baseline}; run with --write-baseline first",
            file=sys.stderr,
        )
        raise SystemExit(2)
    try:
        baseline = Baseline.model_validate_json(spec.baseline.read_text())
    except ValidationError as e:
        print(f"gate: unreadable baseline {spec.baseline}: {e}", file=sys.stderr)
        raise SystemExit(2) from None
    try:
        failures = check_gates(spec, baseline, summary, Path(a.dataset))
    except BaselineMismatch as e:
        print(f"gate: baseline mismatch: {e}", file=sys.stderr)
        raise SystemExit(2) from None
    if not failures:
        print("gate: PASS")
        return
    for f in failures:
        print(f"gate: FAIL {f.metric}: {f.detail}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    exit_on_spec_errors(_main)
