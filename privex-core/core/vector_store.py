import asyncio
import os

from langchain_community.embeddings import OllamaEmbeddings
from langchain_postgres import PGVector


_vector_store: PGVector | None = None

# Keep embeddings resident so they are not recreated on every vector lookup.
embedding_model = OllamaEmbeddings(
    model="nomic-embed-text",
    base_url="http://127.0.0.1:11434",
)


def _normalize_pgvector_connection(connection_str: str) -> str:
    """PGVector initialization must use a synchronous SQLAlchemy driver."""
    normalized = (connection_str or "").strip()
    if normalized.startswith("postgresql+asyncpg://"):
        return normalized.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    if normalized.startswith("postgresql+psycopg_async://"):
        return normalized.replace("postgresql+psycopg_async://", "postgresql+psycopg://", 1)
    return normalized


def _setup_pgvector(connection_str: str) -> PGVector:
    """Synchronous helper to initialize PGVector without greenlet deadlock."""
    return PGVector(
        embeddings=embedding_model,
        collection_name="screen_memories",
        connection=connection_str,
        use_jsonb=True,
    )


async def init_vector_store() -> PGVector | None:
    global _vector_store

    if _vector_store is not None:
        return _vector_store

    connection = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:your_password@127.0.0.1:5432/privex",  # Update your password before production use.
    )
    connection = _normalize_pgvector_connection(connection)

    try:
        # 🛑 FIX: Run PGVector initialization on a separate thread to avoid greenlet_spawn deadlock
        _vector_store = await asyncio.to_thread(_setup_pgvector, connection)
        return _vector_store
    except Exception as exc:
        print(f"[vector-store] Warning: pgvector store unavailable: {exc}")
        _vector_store = None
        return None


def get_vector_store() -> PGVector | None:
    return _vector_store