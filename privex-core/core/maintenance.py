"""
Sleep Cycle: Daily memory consolidation task.
Summarizes 24 hours of micro-memories into a single daily summary using a local LLM.
"""

import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Any

from langchain_community.chat_models import ChatOllama
from langchain_core.documents import Document
from sqlalchemy import text

from core import database
from core.graph_store import get_graph_store
from core.vector_store import get_vector_store


async def _get_db_connection():
    """Get a raw database connection from the session factory."""
    if database._session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() before running maintenance tasks.")
    
    async with database._session_factory() as session:
        return session.connection()


async def _fetch_recent_memories(hours: int = 24) -> list[dict[str, Any]]:
    """
    Fetch all memory documents from the PGVector store created in the past N hours.
    Returns list of dicts with 'content' and 'metadata' keys.
    """
    if database._session_factory is None:
        raise RuntimeError("Database not initialized.")
    
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
    cutoff_iso = cutoff_time.isoformat()
    
    # Query the PGVector vector store table directly
    query_sql = text(
        """
           SELECT document, cmetadata
        FROM langchain_pg_embedding
        WHERE collection_id = (
            SELECT uuid FROM langchain_pg_collection 
            WHERE name = 'screen_memories'
        )
           AND (cmetadata->>'timestamp' IS NULL 
               OR cmetadata->>'timestamp' > :cutoff_time)
           AND (cmetadata->>'type' IS NULL 
               OR cmetadata->>'type' != 'daily_summary')
        ORDER BY id DESC; 
        """
    )
    
    async with database._session_factory() as session:
        conn = await session.connection()
        result = await conn.execute(query_sql, {"cutoff_time": cutoff_iso})
        rows = result.fetchall()
    
    return [
        {
            "content": row.document if hasattr(row, "document") else row[0],
            "metadata": row.cmetadata if hasattr(row, "cmetadata") else row[1],
        }
        for row in rows
    ]


async def _delete_old_memories(hours: int = 24) -> int:
    """
    Delete all micro-memories from the past N hours (excluding daily_summary type).
    Returns the count of deleted records.
    """
    if database._session_factory is None:
        raise RuntimeError("Database not initialized.")
    
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
    cutoff_iso = cutoff_time.isoformat()
    
    delete_sql = text(
        """
        DELETE FROM langchain_pg_embedding
        WHERE collection_id = (
            SELECT uuid FROM langchain_pg_collection 
            WHERE name = 'screen_memories'
        )
           AND (cmetadata->>'timestamp' IS NULL 
               OR cmetadata->>'timestamp' > :cutoff_time)
           AND (cmetadata->>'type' IS NULL 
               OR cmetadata->>'type' != 'daily_summary');
        """
    )
    
    async with database._session_factory() as session:
        result = await session.execute(delete_sql, {"cutoff_time": cutoff_iso})
        await session.commit()
        return result.rowcount


async def run_sleep_cycle() -> bool:
    """
    Execute the full sleep cycle: fetch 24h memories, consolidate via LLM, save, and purge.
    
    Returns True on success, False on error or insufficient data.
    """
    print("\n🌙 [Sleep Cycle] Starting memory consolidation...")
    
    try:
        # 1. Fetch recent memories
        memories = await _fetch_recent_memories(hours=24)
        
        if not memories or len(memories) < 5:
            print(f"⏭️ [Sleep Cycle] Insufficient data ({len(memories)} memories < 5). Skipping consolidation.")
            return False
        
        print(f"✅ [Sleep Cycle] Fetched {len(memories)} memories from past 24 hours.")
        
        # 2. Combine into raw log
        raw_log = "\n---\n".join([
            f"[{mem.get('metadata', {}).get('timestamp', 'Unknown')}] {mem.get('content', '')}"
            for mem in memories
        ])
        
        # 3. Initialize Fallback-Aware LLM
        def get_consolidation_llm():
            if os.getenv("USE_CLOUD_LLM", "false").lower() == "true":
                from langchain_groq import ChatGroq
                # Fast inference fallback for CPU developers
                return ChatGroq(model="llama3-8b-8192", temperature=0.1)
            
            # Native Edge Inference
            return ChatOllama(
                model="llama3.2:1b",
                temperature=0.1,
                base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
            )

        llm = get_consolidation_llm()
        
        # 4. Create consolidation prompt
        consolidation_prompt = f"""You are a memory consolidation AI. Below is a raw log of the user's screen activity for the day. Write a concise, 3-4 sentence summary of what the user accomplished today (e.g., "The user spent the morning coding in VS Code on the Privex backend, and the afternoon reading about Quantum Computing on Wikipedia"). Be factual and specific.

RAW LOG:
{raw_log}

SUMMARY:"""
        
        print("🤔 [Sleep Cycle] Calling LLM for consolidation...")
        
        # 5. Get summary from LLM
        summary_msg = await asyncio.to_thread(
            lambda: llm.invoke(consolidation_prompt)
        )
        daily_summary = summary_msg.content.strip()
        
        print(f"✅ [Sleep Cycle] LLM Summary:\n{daily_summary}\n")
        
        # 6. Save summary to vector store (BEFORE deleting old memories)
        vector_store = get_vector_store()
        if not vector_store:
            print("❌ [Sleep Cycle] Vector store unavailable. Aborting consolidation.")
            return False
        
        summary_doc = Document(
            page_content=daily_summary,
            metadata={
                "type": "daily_summary",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "consolidated_count": len(memories),
            }
        )
        
        await asyncio.to_thread(vector_store.add_documents, [summary_doc])
        print("✅ [Sleep Cycle] Saved daily summary to vector store.")
        
        # 7. Delete old micro-memories
        deleted_count = await _delete_old_memories(hours=24)
        print(f"🗑️ [Sleep Cycle] Purged {deleted_count} old micro-memories.")

        # 8. Run GraphRAG Entity Resolution
        _ = get_graph_store()
        from core.graph_store import run_wcc_deduplication
        await asyncio.to_thread(run_wcc_deduplication)
        
        print("🌙 [Sleep Cycle] Memory consolidation complete!\n")
        return True
        
    except Exception as exc:
        print(f"❌ [Sleep Cycle] Error during consolidation: {exc}")
        import traceback
        traceback.print_exc()
        return False


async def sleep_cycle_loop() -> None:
    """
    Background loop that runs sleep_cycle every 24 hours.
    Call within asyncio.create_task() in the FastAPI lifespan.
    """
    while True:
        try:
            await asyncio.sleep(86400)  # Sleep 24 hours
            await run_sleep_cycle()
        except asyncio.CancelledError:
            print("\n🛑 [Sleep Cycle] Background task cancelled. Exiting.")
            break
        except Exception as exc:
            print(f"❌ [Sleep Cycle] Unexpected error in loop: {exc}")
            await asyncio.sleep(3600)  # Retry after 1 hour on error
