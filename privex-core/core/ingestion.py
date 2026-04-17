import asyncio
import json
import os
import re
from datetime import datetime, timezone
from uuid import uuid4

from langchain_community.chat_models import ChatOllama
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage

from core.graph_store import get_graph_store
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


def _parse_graph_json(raw_content: str) -> dict:
    content = (raw_content or "").strip()
    if not content:
        return {"applications": [], "secrets": [], "dates": []}

    try:
        payload = json.loads(content)
    except Exception:
        match = re.search(r"\{[\s\S]*\}", content)
        if not match:
            return {"applications": [], "secrets": [], "dates": []}
        try:
            payload = json.loads(match.group(0))
        except Exception:
            return {"applications": [], "secrets": [], "dates": []}

    applications = payload.get("applications") if isinstance(payload, dict) else []
    secrets = payload.get("secrets") if isinstance(payload, dict) else []
    dates = payload.get("dates") if isinstance(payload, dict) else []

    if not isinstance(applications, list):
        applications = []
    if not isinstance(secrets, list):
        secrets = []
    if not isinstance(dates, list):
        dates = []

    normalized_apps = [str(item).strip() for item in applications if str(item).strip()]
    normalized_dates = [str(item).strip() for item in dates if str(item).strip()]
    normalized_secrets = [str(item).strip() for item in secrets if str(item).strip()]

    return {
        "applications": normalized_apps,
        "secrets": normalized_secrets,
        "dates": normalized_dates,
    }

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

        doc = Document(
            page_content=new_summary,
            metadata={
                "active_app": active_app,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        await asyncio.to_thread(vs.add_documents, [doc])

        # GraphRAG extraction path (additive to PGVector, never blocking the main pipeline)
        try:
            graph_store = get_graph_store()
            if graph_store is not None:
                graph_prompt = (
                    "Use the schema in docs/GRAPH_SCHEMA.md. "
                    f"Extract graph entities from this summary: {new_summary}. "
                    "Output valid JSON with 'applications', 'secrets', and 'dates'. "
                    "Each value must be an array of strings. "
                    "RULE: When extracting the 'secret' field, ONLY extract literal cryptographic keys, passwords, or API tokens. "
                    "If none exist in the text, you MUST output EXACTLY the word 'Unknown'. "
                    "Do NOT invent descriptions like 'YouTube Secret' or 'Hotstar Secret'."
                )
                graph_response = await llm.ainvoke([HumanMessage(content=graph_prompt)])
                graph_json_raw = getattr(graph_response, "content", graph_response)
                entities = _parse_graph_json(str(graph_json_raw))

                applications = entities.get("applications", [])
                secrets = entities.get("secrets", [])
                dates = entities.get("dates", [])

                if active_app and active_app not in applications:
                    applications.append(active_app)
                if not dates:
                    dates.append(datetime.now(timezone.utc).date().isoformat())

                cypher = """
                MERGE (evt:Alert {id: $alert_id})
                SET evt.timestamp = $timestamp,
                    evt.risk_level = $risk_level,
                    evt.summary = $summary
                WITH evt
                UNWIND $applications AS app_name
                MERGE (a:Application {name: app_name})
                MERGE (evt)-[:OCCURRED_IN]->(a)
                WITH evt
                UNWIND $secrets AS secret_type
                MERGE (s:Secret {type: secret_type, redacted_preview: ''})
                MERGE (evt)-[:EXPOSED]->(s)
                WITH evt
                UNWIND $dates AS date_value
                MERGE (d:Date {date: date_value})
                MERGE (evt)-[:HAPPENED_ON]->(d)
                """

                params = {
                    "alert_id": f"mem-{uuid4()}",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "risk_level": "High",
                    "summary": new_summary,
                    "applications": applications,
                    "secrets": secrets,
                    "dates": dates,
                }
                await asyncio.to_thread(graph_store.query, cypher, params)
        except Exception as graph_exc:
            print(f"[GraphRAG] Non-fatal graph ingestion error: {graph_exc}")
    except Exception as exc:
        print(f"[ingestion] memory ingestion error: {exc}")