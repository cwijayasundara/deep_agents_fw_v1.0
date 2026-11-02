"""Offline smoke run of a factory agent on a scripted model, under a given PlatformContext.

    AGENTKIT_TENANT=acme uv run python scripts/smoke.py --tenant acme --user u1
    uv run python scripts/smoke.py --threads 2     # two threads, one process, own selections
    uv run python scripts/smoke.py --repeat 200    # perf probe: wall time of N runs
    uv run python scripts/smoke.py --persist --say "turn one"            # prints the thread
    uv run python scripts/smoke.py --persist --thread <id> --say "turn two"   # resumes it

Exit codes: 0 ok, 1 the run was refused (TenantMismatch), 2 bad context or persistence config.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
import uuid
from typing import Any

from agentkit_core import ConfigError, PlatformContext, Settings
from agentkit_deep import build_deep_agent
from agentkit_deep.testing import ScriptedChatModel, tool_call
from agentkit_middleware import Selection, SelectionMiddleware, TenantMismatch, ToolCard
from agentkit_persistence import Persistence, PersistenceSettings, open_persistence, thread_lock
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


def script(runs: int) -> ScriptedChatModel:
    """Three model steps per run: whoami, echo, final answer."""
    steps: list[AIMessage] = []
    for i in range(runs):
        steps += [
            tool_call("whoami", {}, f"w{i}"),
            tool_call("echo", {"text": "hi"}, f"e{i}"),
            AIMessage(content="done"),
        ]
    return ScriptedChatModel(messages=iter(steps))


def build(
    model: ScriptedChatModel, selector: ScriptedSelector, persistence: Persistence | None = None
) -> Any:
    return build_deep_agent(
        model=model,
        system_prompt="smoke",
        tools=[whoami, echo],
        middleware=[SelectionMiddleware(selector)],
        settings=Settings(),
        persistence=persistence,
    )


async def run_once(agent: Any, ctx: PlatformContext) -> str:
    out = await agent.ainvoke({"messages": [HumanMessage("smoke")]}, context=ctx)
    return next(str(m.content) for m in out["messages"] if m.type == "tool")


async def persistent_turn(a: argparse.Namespace, ctx: PlatformContext) -> int:
    """One turn on a Postgres-checkpointed thread, inside its lock; a known thread resumes."""
    deployment = Settings().deployment_tenant
    if ctx.tenant != deployment:  # before any graph call: see research_agent.persist (Ruling P4)
        msg = f"run tenant {ctx.tenant!r} != deployment tenant {deployment!r}"
        print(f"TenantMismatch: {msg}", file=sys.stderr)
        return 1
    config: Any = {"configurable": {"thread_id": ctx.thread_id}}
    async with open_persistence(PersistenceSettings.from_env()) as p:
        agent = build(script(1), ScriptedSelector(False), p)
        async with thread_lock(p, ctx.thread_id):
            before = await agent.aget_state(config)
            if before.values:
                print(f"resumed thread {ctx.thread_id} at step {before.metadata['step']}")
            else:
                print(f"thread: {ctx.thread_id}")
            out = await agent.ainvoke({"messages": [HumanMessage(a.say)]}, config, context=ctx)
    said = [str(m.content) for m in out["messages"] if m.type == "human"]
    print(f"  turns on this thread: {said}")
    return 0


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
    if a.repeat:
        start = time.perf_counter()
        for i in range(a.repeat):
            await run_once(
                build(script(1), ScriptedSelector(False)),
                contexts[0].model_copy(update={"thread_id": f"{threads[0]}-{i}"}),
            )
        print(f"repeat {a.repeat}: {time.perf_counter() - start:.3f}s")
        return 0
    model = script(len(contexts))
    agent = build(model, ScriptedSelector(alternate=len(contexts) > 1))
    print(f"deployment tenant: {Settings().deployment_tenant}")
    for ctx in contexts:
        before = len(model.bound)
        try:
            saw = await run_once(agent, ctx)
        except TenantMismatch as e:
            print(f"TenantMismatch: {e}", file=sys.stderr)
            print(f"model calls: {len(model.bound)}")
            return 1
        bound = sorted({n for b in model.bound[before:] for n in b if n in TOOLS})
        print(f"thread: {ctx.thread_id}")
        print(f"  tool saw: {saw}")
        print(f"  bound custom tools: {bound}")
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
    p.add_argument("--say", default="smoke", help="this turn's user message (with --persist)")
    sys.exit(asyncio.run(main(p.parse_args())))
