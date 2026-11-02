"""Refuse any run whose PlatformContext names a tenant other than the deployment's."""

from __future__ import annotations

from typing import Any

from agentkit_core import PlatformContext, check_label
from langchain.agents.middleware import AgentMiddleware
from langgraph.runtime import Runtime


class TenantMismatch(PermissionError):
    """The run's tenant is not the tenant this deployment serves."""


class MissingPlatformContext(TypeError):
    """The run was invoked without a PlatformContext."""


class TenantGuardMiddleware(AgentMiddleware[Any, PlatformContext]):
    """First middleware of every factory agent: validates the run context before anything runs."""

    def __init__(self, deployment_tenant: str) -> None:
        super().__init__()
        self.deployment_tenant = check_label(deployment_tenant, "deployment tenant")

    def before_agent(self, state: Any, runtime: Runtime[PlatformContext]) -> None:
        ctx = runtime.context
        if not isinstance(ctx, PlatformContext):
            got = "nothing" if ctx is None else type(ctx).__name__
            raise MissingPlatformContext(
                f"agent runs need context=PlatformContext(...) on invoke/stream; got {got}"
            )
        if ctx.tenant != self.deployment_tenant:
            raise TenantMismatch(
                f"run tenant {ctx.tenant!r} != deployment tenant {self.deployment_tenant!r}"
            )
        return None
