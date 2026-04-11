import os

from langchain_community.embeddings import OllamaEmbeddings
from langchain_postgres import PGVector


_vector_store: PGVector | None = None

# Keep embeddings resident so they are not recreated on every vector lookup.
embedding_model = OllamaEmbeddings(
    model="nomic-embed-text",
    base_url="http://127.0.0.1:11434",
)


async def init_vector_store() -> PGVector | None:
    global _vector_store

    if _vector_store is not None:
        return _vector_store

    connection = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:your_password@127.0.0.1:5432/privex",  # Update your password before production use.
    )

    try:
        _vector_store = PGVector(
            embeddings=embedding_model,
            collection_name="screen_memories",
            connection=connection,
            use_jsonb=True,
        )
        return _vector_store
    except Exception as exc:
        print(f"[vector-store] Warning: pgvector store unavailable: {exc}")
        _vector_store = None
        return None


def get_vector_store() -> PGVector | None:
    return _vector_store