"""agentkit-connectors: connector specs, secret refs, embeddings, pooled Postgres engines."""

from .embeddings import embedding_dimensions, get_embeddings
from .engines import get_engine, get_vectorstore
from .spec import ConnectorSpec, PgVectorSpec, PostgresSpec, load_connector

__all__ = [
    "ConnectorSpec",
    "PgVectorSpec",
    "PostgresSpec",
    "embedding_dimensions",
    "get_embeddings",
    "get_engine",
    "get_vectorstore",
    "load_connector",
]
