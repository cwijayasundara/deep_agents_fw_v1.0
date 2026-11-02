"""Send a run back to the model when it ends without writing its output file."""

from __future__ import annotations

import logging
from typing import Any

from langchain.agents.middleware import AgentMiddleware, hook_config
from langchain_core.messages import AIMessage, HumanMessage

log = logging.getLogger(__name__)

NUDGE_NAME = "require_output"


class RequireOutputMiddleware(AgentMiddleware):
    """When the model replies without a tool call while `path` is still missing from the state's
    files, add a user nudge and jump back to the model, at most `max_nudges` times per run.

    Models sometimes end a turn on a reply that only announces more work ("Let me delegate ..."),
    which leaves the agent's answer file unwritten."""

    def __init__(self, path: str, max_nudges: int = 2) -> None:
        super().__init__()
        self.path = path
        self.max_nudges = max_nudges

    @hook_config(can_jump_to=["model"])
    def after_model(self, state: Any, runtime: Any) -> dict[str, Any] | None:
        messages = state.get("messages") or []
        last = messages[-1] if messages else None
        if not isinstance(last, AIMessage) or last.tool_calls:
            return None
        if self.path in (state.get("files") or {}):
            return None
        nudges = sum(1 for m in messages if isinstance(m, HumanMessage) and m.name == NUDGE_NAME)
        if nudges >= self.max_nudges:
            log.warning("%s still missing after %d nudge(s); ending the run", self.path, nudges)
            return None
        log.info(
            "%s missing after a final reply; nudging (%d/%d)",
            self.path,
            nudges + 1,
            self.max_nudges,
        )
        nudge = HumanMessage(
            f"You ended your turn without saving {self.path}. Make any remaining tool calls now "
            f"(do not announce them), then save the final answer to {self.path}.",
            name=NUDGE_NAME,
        )
        return {"messages": [nudge], "jump_to": "model"}
