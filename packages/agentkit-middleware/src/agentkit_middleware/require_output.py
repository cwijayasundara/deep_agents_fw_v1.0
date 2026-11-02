"""Send a run back to the model when it ends without writing its output file."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Annotated, Any, NotRequired

from langchain.agents.middleware import AgentMiddleware, AgentState, hook_config
from langchain.agents.middleware.types import PrivateStateAttr
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.channels.untracked_value import UntrackedValue

log = logging.getLogger(__name__)

NUDGE_NAME = "require_output"
_ABSENT = ""


class RequireOutputState(AgentState):
    # Untracked: never checkpointed, so every invocation (turn) starts without them.
    require_output_nudges: NotRequired[Annotated[int, UntrackedValue, PrivateStateAttr]]
    require_output_at_start: NotRequired[Annotated[str, UntrackedValue, PrivateStateAttr]]


def _fingerprint(state: Any, path: str) -> str:
    """SHA-256 of the file's state entry (content plus timestamps), or `_ABSENT`."""
    entry = (state.get("files") or {}).get(path)
    if entry is None:
        return _ABSENT
    return hashlib.sha256(json.dumps(entry, sort_keys=True, default=str).encode()).hexdigest()


class RequireOutputMiddleware(AgentMiddleware):
    """When the model replies without a tool call while `path` has not been written in this run,
    add a user nudge and jump back to the model, at most `max_nudges` times per run.

    Models sometimes end a turn on a reply that only announces more work ("Let me delegate ..."),
    which leaves the agent's answer file unwritten.

    Per run, not per thread: a run is one graph invocation, i.e. one turn on a resumed thread.
    `before_agent` records a fingerprint of the file's state entry (a hash of its content and
    its `created_at`/`modified_at`), and the file counts as written only if its entry differs
    from that fingerprint, so a report left in the thread by an earlier turn does not satisfy
    this one. deepagents stamps `modified_at` on every write, so rewriting identical text still
    counts. The nudge counter and the fingerprint live in untracked state (the way
    `ModelCallLimitMiddleware` keeps its run count), so they are never checkpointed and each
    invocation starts fresh; the nudge count does not depend on `messages`, which summarization
    may trim. Consequence: a run resumed from an interrupt (`Command(resume=...)`) skips
    `before_agent` and has no start fingerprint, so there any present file counts as written.

    Only state-backed paths work: a path routed to the store never appears in `files`."""

    state_schema = RequireOutputState

    def __init__(self, path: str, max_nudges: int = 2) -> None:
        super().__init__()
        self.path = path
        self.max_nudges = max_nudges

    def before_agent(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        return {
            "require_output_nudges": 0,
            "require_output_at_start": _fingerprint(state, self.path),
        }

    @hook_config(can_jump_to=["model"])
    def after_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        messages = state.get("messages") or []
        last = messages[-1] if messages else None
        if not isinstance(last, AIMessage) or last.tool_calls:
            return None
        now = _fingerprint(state, self.path)
        if now != _ABSENT and now != state.get("require_output_at_start", _ABSENT):
            return None
        nudges = state.get("require_output_nudges", 0)
        if nudges >= self.max_nudges:
            log.warning("%s not written after %d nudge(s); ending the run", self.path, nudges)
            return None
        log.info(
            "%s not written this run after a final reply; nudging (%d/%d)",
            self.path,
            nudges + 1,
            self.max_nudges,
        )
        nudge = HumanMessage(
            f"You ended your turn without saving {self.path}. Make any remaining tool calls now "
            f"(do not announce them), then save the final answer to {self.path}.",
            name=NUDGE_NAME,
        )
        return {"messages": [nudge], "require_output_nudges": nudges + 1, "jump_to": "model"}
