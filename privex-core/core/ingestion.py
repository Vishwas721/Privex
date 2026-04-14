import asyncio
import os
from datetime import datetime, timezone

from langchain_community.chat_models import ChatOllama
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage

from core.vector_store import get_vector_store


def get_ingestion_llm():
    if os.getenv("USE_CLOUD_LLM", "false").lower() == "true":
        from langchain_groq import ChatGroq
        # Groq fallback for CPU developers (fast inference)
        return ChatGroq(model="llama3-8b-8192", temperature=0.1)

    # Native Edge Inference
    return ChatOllama(
        base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
        model="llama3.2:1b",
        temperature=0.1,
    )


llm = get_ingestion_llm()

_last_saved_memory: dict[str, str] = {}


async def process_and_store_memory(ocr_text: str, active_app: str) -> None:
    try:
        ocr_text = (ocr_text or "").strip()
        active_app = (active_app or "").strip()
        
        # ⚙️ TRACER: Log entry point with parameters
        print(f"⚙️ [Ingestion] Received request for {active_app}. Text length: {len(ocr_text)}")
        
        if not ocr_text:
            return

        prompt = (
            f"You are an AI analyzing OCR text from a user's screen in the app: {active_app}. "
            "Summarize what the user is doing or looking at in ONE concise sentence. "
            "If the text is just an empty desktop or random UI noise, reply ONLY with the exact word 'NOISE'. "
            f"OCR Text: {ocr_text}"
        )

        response = await llm.ainvoke([HumanMessage(content=prompt)])
        new_summary = (getattr(response, "content", response) or "").strip()
        
        # 🛑 ADDED PRINT: See when it ignores useless screens
        if new_summary == "NOISE" or not new_summary:
            print(f"🙈 [Ingestion] Ignored noise in app: {active_app}")
            return

        # 🛑 ADDED PRINT: See the deduplication engine working
        if _last_saved_memory.get(active_app) == new_summary:
            print(f"♻️ [Ingestion] Deduplicated identical screen in: {active_app}")
            return

        _last_saved_memory[active_app] = new_summary

        vs = get_vector_store()
        if vs is None:
            print("[ingestion] vector store unavailable; skipping memory save.")
            return
        else:
            # 🔌 TRACER: Confirm vector store connection
            print(f"🔌 [Ingestion] Vector store connection confirmed. Saving document...")

        doc = Document(
            page_content=new_summary,
            metadata={
                "active_app": active_app,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        await asyncio.to_thread(vs.add_documents, [doc])
        
        # 🛑 ADDED PRINT: The Success Log!
        print(f"\n🧠 [Ingestion] SAVED NEW MEMORY: {new_summary}\n")
    except Exception as exc:
        print(f"[ingestion] memory ingestion error: {exc}")