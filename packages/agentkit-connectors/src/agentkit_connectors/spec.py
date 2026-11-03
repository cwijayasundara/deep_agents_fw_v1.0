from __future__ import annotations

import os
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


def library_roots(start: Path | None = None) -> list[Path]:
    """Library roots for tool factories, which get no `Library`: the nearest `libraries/` at or
    above `start` (default: the working directory), then `AGENTKIT_LIBRARY_PATH` entries; the
    same order `Library.for_file` uses after the agent file's own directory."""
    roots: list[Path] = []
    here = (start or Path.cwd()).resolve()
    for ancestor in (here, *here.parents):
        if (ancestor / "libraries").is_dir():
            roots.append(ancestor / "libraries")
            break
    env = os.environ.get("AGENTKIT_LIBRARY_PATH", "")
    roots.extend(Path(p).resolve() for p in env.split(os.pathsep) if p)
    return [r for r in dict.fromkeys(roots) if r.is_dir()]
