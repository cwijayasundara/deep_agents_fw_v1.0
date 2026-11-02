"""The per-run tenant context every agent run carries (passed as `ainvoke(..., context=ctx)`)."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    StringConstraints,
    TypeAdapter,
    ValidationError,
    field_validator,
)

# Lowercase, no dots: Postgres store namespaces reject dots, and labels become namespace parts.
LABEL_PATTERN = r"^[a-z0-9][a-z0-9_-]{0,62}$"
Label = Annotated[str, StringConstraints(pattern=LABEL_PATTERN)]
Scope = Literal["user", "global"]
# `store_namespace` puts "global" in the owner slot for tenant-wide items, so no user may be named
# "global" (Ruling P8): such a user's namespace would alias the tenant's.
RESERVED_USER_IDS = frozenset({"global"})

_LABEL: TypeAdapter[str] = TypeAdapter(Label)


def check_label(value: str, what: str) -> str:
    """`value` if it is a valid Label; else ValueError naming `what`."""
    try:
        return _LABEL.validate_python(value)
    except ValidationError:
        raise ValueError(f"invalid {what} {value!r}: must match {LABEL_PATTERN}") from None


def check_user_id(value: str) -> str:
    """`value` if it is a valid, unreserved user id; else ValueError."""
    check_label(value, "user")
    if value in RESERVED_USER_IDS:
        raise ValueError(f"user id {value!r} is reserved (it names the tenant-wide store owner)")
    return value


class PlatformContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    tenant: Label
    product: Label
    team: Label
    user_id: Label
    thread_id: str
    agent_name: Label
    agent_version: str

    @field_validator("user_id")
    @classmethod
    def _unreserved_user(cls, value: str) -> str:
        if value in RESERVED_USER_IDS:
            raise ValueError(f"{value!r} is reserved (it names the tenant-wide store owner)")
        return value


def store_namespace(ctx: PlatformContext, scope: Scope, kind: str) -> tuple[str, ...]:
    """`(tenant, product, team, user_id | "global", kind)`: one tenant's slice of the store."""
    owner = ctx.user_id if scope == "user" else "global"
    return (ctx.tenant, ctx.product, ctx.team, owner, check_label(kind, "kind"))
