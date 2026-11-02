"""Runtime node callables for compiled flows: agent nodes and human-in-the-loop interrupts."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from agentkit_core import PlatformContext
from langchain_core.messages import HumanMessage
from langgraph.runtime import Runtime
from langgraph.types import interrupt

from agentkit_config.load import LoadedAgent
from agentkit_config.output import read_output

State = Any  # the flow's state schema (a TypedDict instance at runtime)


def agent_message(state: State, input: str | list[str]) -> str:
    """One field's value, or `## field` sections (absent/empty fields skipped)."""
    if isinstance(input, str):
        return str(state.get(input, ""))
    return "\n\n".join(f"## {f}\n{state[f]}" for f in input if state.get(f))


def agent_node(
    loaded: LoadedAgent, input: str | list[str], output: str
) -> Callable[[State, Runtime[PlatformContext]], Awaitable[dict[str, str]]]:
    """Run the agent on the input field(s) under the flow's PlatformContext; write its output
    (file or last message) to `output`."""

    async def run(state: State, runtime: Runtime[PlatformContext]) -> dict[str, str]:
        message = agent_message(state, input)
        result = await loaded.graph.ainvoke(
            {"messages": [HumanMessage(message)]}, context=runtime.context
        )
        return {output: read_output(result, loaded.spec.output)}

    return run


def interrupt_node(name: str) -> Callable[[State], dict[str, Any]]:
    """Pause with `{"node": name}`; the resume value must be a Mapping merged into state.

    Resume with a non-empty mapping: LangGraph reads `Command(resume={})` as an empty resume
    map (interrupt id -> value), which answers no interrupt and leaves the flow paused.
    """

    def pause(state: State) -> dict[str, Any]:
        value = interrupt({"node": name})
        if not isinstance(value, Mapping):
            msg = f"resume value for interrupt node {name!r} must be a Mapping, got {type(value)}"
            raise TypeError(msg)
        return dict(value)

    return pause
