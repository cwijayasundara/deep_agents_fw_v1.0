from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Annotated, Literal

import yaml
from agentkit_core import ConfigError
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dsn: str  # a secret ref, e.g. env://KB_DATABASE_URL


class PgVectorSpec(_Base):
    kind: Literal["pgvector"]
    collection: str
    embeddings: str


class PostgresSpec(_Base):
    kind: Literal["postgres"]
    schemas: list[str] = Field(min_length=1)
    statement_timeout_ms: int = 5000
    max_rows: int = 200


ConnectorSpec = Annotated[PgVectorSpec | PostgresSpec, Field(discriminator="kind")]
_ADAPTER: TypeAdapter[PgVectorSpec | PostgresSpec] = TypeAdapter(ConnectorSpec)


def load_connector(name: str, roots: Iterable[Path]) -> PgVectorSpec | PostgresSpec:
    """First `<root>/connectors/<name>.yaml` wins."""
    roots = list(roots)
    for root in roots:
        path = Path(root) / "connectors" / f"{name}.yaml"
        if path.is_file():
            try:
                return _ADAPTER.validate_python(yaml.safe_load(path.read_text()))
            except ValidationError as e:
                raise ConfigError(f"invalid connector '{name}' ({path}): {e}") from e
    known = sorted({p.stem for r in roots for p in (Path(r) / "connectors").glob("*.yaml")})
    raise ConfigError(f"unknown connector '{name}'; known: {', '.join(known) or 'none'}")
