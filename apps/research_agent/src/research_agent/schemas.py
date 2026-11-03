"""Completion contracts for the research agent's subagents."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Finding(BaseModel):
    claim: str = Field(description="One concise, sourced finding.")
    url: str = Field(description="The URL the finding was retrieved from.")


class Findings(BaseModel):
    """What the researcher subagent hands back for one sub-question."""

    question: str = Field(description="The sub-question that was researched.")
    findings: list[Finding] = Field(description="Sourced findings; empty if nothing was found.")
