import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine


load_dotenv()

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker | None = None


def _get_database_url() -> str:
    # Use SQLite by default for zero-config local state
    return os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./privex_state.db").strip()


def _row_hash(timestamp: datetime, event_type: str, details: dict[str, Any]) -> str:
    payload = {
        "timestamp": timestamp.isoformat(),
        "event_type": event_type,
        "details": details,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def init_db() -> None:
    """Initialize pooled DB engine and ensure audit_log table exists."""
    global _engine, _session_factory

    if _engine is not None:
        return

    database_url = _get_database_url()
    _engine = create_async_engine(
        database_url,
        # SQLite specific settings
        connect_args={"check_same_thread": False}
    )
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)

    create_table_sql = text(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id TEXT PRIMARY KEY,
            timestamp TEXT NOT NULL,
            event_type TEXT NOT NULL,
            details TEXT NOT NULL,
            hash TEXT NOT NULL
        )
        """
    )

    async with _engine.begin() as conn:
        await conn.execute(create_table_sql)


async def close_db() -> None:
    """Dispose pooled DB engine on application shutdown."""
    global _engine, _session_factory

    if _engine is not None:
        await _engine.dispose()

    _engine = None
    _session_factory = None


async def log_event(event_type: str, details: dict[str, Any]) -> str:
    """Insert a tamper-evident audit event and return the inserted id."""
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() before log_event().")

    event_id = str(uuid.uuid4())
    ts = datetime.now(timezone.utc)
    row_digest = _row_hash(ts, event_type, details)

    insert_sql = text(
        """
        INSERT INTO audit_log (id, timestamp, event_type, details, hash)
        VALUES (:id, :timestamp, :event_type, :details, :hash)
        """
    )

    async with _session_factory() as session:
        await session.execute(
            insert_sql,
            {
                "id": event_id,
                "timestamp": ts.isoformat(),
                "event_type": event_type,
                "details": json.dumps(details),
                "hash": row_digest,
            },
        )
        await session.commit()

    return event_id


async def get_recent_logs(limit: int = 10) -> list[dict[str, Any]]:
    """Fetch recent audit log rows ordered by newest first."""
    if _session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() before get_recent_logs().")

    query_sql = text(
        """
        SELECT id, timestamp, event_type, details, hash
        FROM audit_log
        ORDER BY timestamp DESC
        LIMIT :limit
        """
    )

    async with _session_factory() as session:
        result = await session.execute(query_sql, {"limit": limit})
        rows = result.fetchall()

    return [
        {
            "id": str(row.id),
            "timestamp": row.timestamp,
            "event_type": row.event_type,
            "details": json.loads(row.details) if row.details else {},
            "hash": row.hash,
        }
        for row in rows
    ]
