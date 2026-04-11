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
        if new_summary == "NOISE" or not new_summary:
            return

        if _last_saved_memory.get(active_app) == new_summary:
            return

        _last_saved_memory[active_app] = new_summary

        vs = get_vector_store()
        if vs is None:
            print("[ingestion] vector store unavailable; skipping memory save.")
            return

        doc = Document(
            page_content=new_summary,
            metadata={
                "active_app": active_app,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        await asyncio.to_thread(vs.add_documents, [doc])
    except Exception as exc:
        print(f"[ingestion] memory ingestion error: {exc}")