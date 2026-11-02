"""Offline smoke run of a factory agent on a scripted model, under a given PlatformContext.

    AGENTKIT_TENANT=acme uv run python scripts/smoke.py --tenant acme --user u1
    uv run python scripts/smoke.py --threads 2     # two threads, one process, own selections
    uv run python scripts/smoke.py --repeat 200    # perf probe: wall time of N runs
    uv run python scripts/smoke.py --persist --say "turn one"            # prints the thread
    uv run python scripts/smoke.py --persist --thread <id> --say "turn two"   # resumes it
    OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:4318 uv run python scripts/smoke.py --trace
    uv run python scripts/smoke.py --decisions-fixture <recorded /v1/decisions response.json>

Every run is built with `agentkit_telemetry.run_config` and metered by a `CostLedger` (each
scripted model step reports 10 input / 3 output tokens); under `--persist` its rows go to
`agentkit_usage`.

Exit codes: 0 ok, 1 the run was refused (TenantMismatch), 2 bad context or persistence config.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
from agentkit_core import ConfigError, PlatformContext, Settings
from agentkit_deep import agent_prompt_hash, build_deep_agent
from agentkit_deep.testing import MeteredChatModel, tool_call
from agentkit_middleware import (
    DecisionsClient,
    DecisionsSelector,
    Selection,
    SelectionMiddleware,
    Selector,
    TenantMismatch,
    ToolCard,
)
from agentkit_persistence import Persistence, PersistenceSettings, open_persistence, thread_lock
from agentkit_telemetry import (
    CostLedger,
    TelemetrySettings,
    configure_tracing,
    run_config,
    setup,
    shutdown_tracing,
    trace_id,
)
from langchain.tools import ToolRuntime, tool
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import ValidationError

TOOLS = ("whoami", "echo")


@tool
def whoami(runtime: ToolRuntime[PlatformContext]) -> str:
    """Report the tenant, user and thread this run belongs to."""
    c = runtime.context
    return f"{c.tenant}/{c.user_id}/{c.thread_id}"


@tool
def echo(text: str) -> str:
    """Echo the text back."""
    return text


class ScriptedSelector:
    """Thread i (in order of first sight) gets TOOLS[i % 2] when `alternate`, else all tools."""

    def __init__(self, alternate: bool) -> None:
        self.alternate = alternate
        self.seen: dict[str | None, Selection] = {}

    async def select(
        self, task: str, tools: list[ToolCard], *, thread_id: str | None = None
    ) -> Selection:
        names = {TOOLS[len(self.seen) % 2]} if self.alternate else set(TOOLS)
        return self.seen.setdefault(thread_id, Selection("default", frozenset(names)))


def fixture_selector(path: Path) -> DecisionsSelector:
    """The real DecisionsSelector, answered by a recorded /v1/decisions response (no network)."""
    body = json.loads(path.read_text())
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=body))
    client = DecisionsClient("sk-fixture", client=httpx.AsyncClient(transport=transport))
    return DecisionsSelector(client)


def script(runs: int) -> MeteredChatModel:
    """Three model steps per run: whoami, echo, final answer (each 10 in / 3 out tokens)."""
    steps: list[AIMessage] = []
    for i in range(runs):
        steps += [
            tool_call("whoami", {}, f"w{i}"),
            tool_call("echo", {"text": "hi"}, f"e{i}"),
            AIMessage(content="done"),
        ]
    return MeteredChatModel(messages=iter(steps))


def build(
    model: MeteredChatModel, selector: Selector, persistence: Persistence | None = None
) -> Any:
    return build_deep_agent(
        model=model,
        system_prompt="smoke",
        tools=[whoami, echo],
        middleware=[SelectionMiddleware(selector)],
        settings=Settings(),
        persistence=persistence,
    )


async def run_once(
    agent: Any, ctx: PlatformContext, ledger: CostLedger, say: str
) -> tuple[str, str | None]:
    """The first tool result and the run's trace id (None when tracing is off)."""
    config = run_config(ctx, agent_prompt_hash(agent), ledger)
    out = await agent.ainvoke({"messages": [HumanMessage(say)]}, config, context=ctx)
    return next(str(m.content) for m in out["messages"] if m.type == "tool"), trace_id(config)


async def persistent_turn(a: argparse.Namespace, ctx: PlatformContext) -> int:
    """One turn on a Postgres-checkpointed thread, inside its lock; a known thread resumes."""
    deployment = Settings().deployment_tenant
    if ctx.tenant != deployment:  # before any graph call: see research_agent.persist (Ruling P4)
        msg = f"run tenant {ctx.tenant!r} != deployment tenant {deployment!r}"
        print(f"TenantMismatch: {msg}", file=sys.stderr)
        return 1
    async with open_persistence(PersistenceSettings.from_env()) as p:
        await setup(p)
        ledger = CostLedger(p)
        agent = build(script(1), selector(a), p)
        config = run_config(ctx, agent_prompt_hash(agent), ledger)
        async with thread_lock(p, ctx.thread_id):
            before = await agent.aget_state(config)
            if before.values:
                print(f"resumed thread {ctx.thread_id} at step {before.metadata['step']}")
            else:
                print(f"thread: {ctx.thread_id}")
            out = await agent.ainvoke({"messages": [HumanMessage(a.say)]}, config, context=ctx)
    if (trace := trace_id(config)) is not None:
        print(f"  trace: {trace}")
    said = [str(m.content) for m in out["messages"] if m.type == "human"]
    print(f"  turns on this thread: {said}")
    print(ledger.summary())
    return 0


def selector(a: argparse.Namespace, alternate: bool = False) -> Selector:
    return (
        fixture_selector(a.decisions_fixture)
        if a.decisions_fixture
        else ScriptedSelector(alternate)
    )


def tracing(a: argparse.Namespace) -> None:
    if not a.trace:
        return
    telemetry = TelemetrySettings.from_env(tenant=Settings().deployment_tenant)
    if configure_tracing(telemetry) is None:
        print("tracing: off (OTEL_EXPORTER_OTLP_ENDPOINT is not set)")
    else:
        payloads = "on" if telemetry.trace_payloads else "masked"
        print(f"tracing: {telemetry.otlp_endpoint} (payloads {payloads})")


def context(a: argparse.Namespace, thread: str) -> PlatformContext:
    return PlatformContext(
        tenant=a.tenant,
        product="agentkit",
        team="platform",
        user_id=a.user,
        thread_id=thread,
        agent_name="smoke",
        agent_version="0",
    )


async def main(a: argparse.Namespace) -> int:
    threads = [a.thread or str(uuid.uuid4())] + [str(uuid.uuid4()) for _ in range(a.threads - 1)]
    try:
        contexts = [context(a, t) for t in threads]
    except ValidationError as e:
        print(f"context rejected before the agent started:\n{e}", file=sys.stderr)
        return 2
    if a.persist:
        try:
            return await persistent_turn(a, contexts[0])
        except ConfigError as e:
            print(f"ConfigError: {e}", file=sys.stderr)
            return 2
    ledger = CostLedger()
    if a.repeat:
        start = time.perf_counter()
        for i in range(a.repeat):
            await run_once(
                build(script(1), selector(a)),
                contexts[0].model_copy(update={"thread_id": f"{threads[0]}-{i}"}),
                ledger,
                a.say,
            )
        print(f"repeat {a.repeat}: {time.perf_counter() - start:.3f}s")
        return 0
    model = script(len(contexts))
    agent = build(model, selector(a, alternate=len(contexts) > 1))
    print(f"deployment tenant: {Settings().deployment_tenant}")
    for ctx in contexts:
        before = len(model.bound)
        try:
            saw, trace = await run_once(agent, ctx, ledger, a.say)
        except TenantMismatch as e:
            print(f"TenantMismatch: {e}", file=sys.stderr)
            print(f"model calls: {len(model.bound)}")
            return 1
        bound = sorted({n for b in model.bound[before:] for n in b if n in TOOLS})
        print(f"thread: {ctx.thread_id}")
        if trace is not None:
            print(f"  trace: {trace}")
        print(f"  tool saw: {saw}")
        print(f"  bound custom tools: {bound}")
    print(ledger.summary())
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser(prog="smoke")
    p.add_argument("--tenant", default="default")
    p.add_argument("--user", default="local")
    p.add_argument("--thread", help="thread id of the first run (default: a new uuid4)")
    p.add_argument("--threads", type=int, default=1, help="runs on N threads, one agent")
    p.add_argument("--repeat", type=int, default=0, help="time N fresh build+run cycles")
    p.add_argument(
        "--persist",
        action="store_true",
        help="one turn on a Postgres thread (DATABASE_URL, LANGGRAPH_AES_KEY); --thread resumes",
    )
    p.add_argument("--say", default="smoke", help="each run's user message")
    p.add_argument("--trace", action="store_true", help="trace to OTEL_EXPORTER_OTLP_ENDPOINT")
    p.add_argument(
        "--decisions-fixture",
        type=Path,
        help="select with DecisionsSelector replaying this recorded response (reports usage)",
    )
    args = p.parse_args()
    tracing(args)
    try:
        code = asyncio.run(main(args))
    finally:
        shutdown_tracing()  # blocking flush: outside the event loop, as in the research CLIs
    sys.exit(code)
