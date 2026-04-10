import json
import os
from typing import Literal
from typing import Any

try:
    from langchain_ollama import ChatOllama
except Exception:
    from langchain_community.chat_models import ChatOllama
from langchain_community.embeddings import OllamaEmbeddings
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from langgraph.graph import END, StateGraph

try:
    from langchain_postgres import PGVector
except Exception:
    PGVector = None

from core.state import AgentState


class RouteDecision(BaseModel):
    selected_agent: Literal["memory_agent", "firewall_agent", "phishing_agent", "general_chat"]
    reasoning: str
    confidence: float = Field(ge=0.0, le=1.0)


def get_llm(temperature: float = 0.0, is_json: bool = False):
    if os.getenv("USE_CLOUD_LLM", "false").lower() == "true":
        from langchain_groq import ChatGroq
        # Groq fallback for CPU developers
        return ChatGroq(model="llama3-8b-8192", temperature=temperature)

    # Local Edge Inference
    return ChatOllama(
        base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
        model="qwen2.5:1.5b",
        temperature=temperature,
        format="json" if is_json else None,
    )


# Use it for the router
llm = get_llm(temperature=0.0, is_json=True)

_embedding_model = OllamaEmbeddings(
    base_url="http://127.0.0.1:11434", # FORCE THE IPV4 PORT
    model=os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
)
_vector_store = None
_vector_threshold = float(os.getenv("MEMORY_MATCH_THRESHOLD", "0.4"))


def _get_vector_store() -> Any:
    global _vector_store

    if _vector_store is not None:
        return _vector_store

    if PGVector is None:
        return None

    connection = os.getenv(
        "PGVECTOR_CONNECTION",
        os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:password@localhost:5432/privex"),
    )
    if "+asyncpg" in connection:
        connection = connection.replace("+asyncpg", "+psycopg")

    collection_name = os.getenv("PGVECTOR_COLLECTION", "approved_actions")

    try:
        _vector_store = PGVector(
            embeddings=_embedding_model,
            collection_name=collection_name,
            connection=connection,
            use_jsonb=True,
        )
    except Exception:
        _vector_store = None

    return _vector_store


def route_query(state: AgentState) -> dict:
    """Deterministically map user input to one sub-agent."""
    user_query = state.get("user_query", "")
    messages = [
        (
            "system",
            "You are a strict router. Choose one agent:\n"
            "memory_agent: search history, recall events, save memory\n"
            "firewall_agent: raw OCR with secrets like passwords, keys, tokens\n"
            "phishing_agent: suspicious emails, URLs, social engineering\n"
            "general_chat: normal conversation or unclear text\n\n"
            "You MUST output ONLY valid JSON in this exact format: "
            '{"selected_agent": "insert_agent_name_here", "reasoning": "brief explanation", "confidence": 0.9}',
        ),
        ("human", user_query),
    ]

    try:
        response = llm.invoke(messages)
        content = getattr(response, "content", response)
        if isinstance(content, list):
            content = "".join(str(part) for part in content)
        payload = json.loads(content)

        if "agent" in payload and "selected_agent" not in payload:
            payload["selected_agent"] = payload.pop("agent")

        decision = RouteDecision.model_validate(payload)
        return {"current_agent": decision.selected_agent}
    except Exception as exc:
        print(f"[router] route_query error: {exc}")
        return {"current_agent": "firewall_agent"}


def memory_agent_node(state: AgentState) -> dict:
    query = state.get("user_query", "")

    vector_store = _get_vector_store()
    if vector_store is None:
        return {
            "response": "My memory database is currently offline.",
            "human_approval_required": False,
        }

    try:
        docs = vector_store.similarity_search(query, k=5)
    except Exception:
        return {
            "response": "My memory database is currently offline.",
            "human_approval_required": False,
        }

    if not docs:
        return {
            "response": "I don't have any memories matching that request yet.",
            "human_approval_required": False,
        }

    formatted_context = "\n".join(
        f"[App: {(getattr(doc, 'metadata', {}) or {}).get('active_app')}] - {getattr(doc, 'page_content', '')}"
        for doc in docs
    )

    # 1. Use the fallback-aware LLM for conversation
    chat_llm = get_llm(temperature=0.3, is_json=False)

    system_text = (
        "You are Privex, a privacy-first AI assistant. Answer the user's question using ONLY the provided "
        "memory context. Do not invent information. If the answer is not in the context, explicitly state "
        "that you do not have a memory of it."
        f"\n\nMemory Context:\n{formatted_context}"
    )

    try:
        response = chat_llm.invoke([
            SystemMessage(content=system_text),
            HumanMessage(content=query),
        ])
        return {
            "response": response.content,
            "proposed_action": "search_local_memory", # Let the deterministic Risk Engine handle the boolean!
        }
    except Exception:
        return {
            "response": "I couldn't read memory context right now. Please try again.",
            "proposed_action": "search_local_memory",
        }


def firewall_agent_node(state: AgentState) -> dict:
    return {"proposed_action": "redact_and_alert"}


def phishing_agent_node(state: AgentState) -> dict:
    return {"proposed_action": "send_external_email"}


def general_chat_node(state: AgentState) -> dict:
    return {"proposed_action": "answer_general_chat"}


def risk_engine_node(state: AgentState) -> dict:
    """Pure Python, deterministic risk evaluation. NEVER USE AN LLM HERE."""
    action = state.get("proposed_action")

    # Hardcoded Risk Dictionary
    if action == "search_local_memory":
        return {
            "risk_level": "Low",
            "human_approval_required": False,
        }
    elif action == "redact_and_alert":
        return {
            "risk_level": "High",
            "human_approval_required": True,
        }
    elif action == "send_external_email":
        return {
            "risk_level": "High",
            "human_approval_required": True,
        }
    elif action == "answer_general_chat":
        return {
            "risk_level": "Low",
            "human_approval_required": False,
        }

    return {}


def route_to_subagent(state: AgentState) -> str:
    return state["current_agent"]


graph_builder = StateGraph(AgentState)

graph_builder.add_node("route_query", route_query)
graph_builder.add_node("memory_agent", memory_agent_node)
graph_builder.add_node("firewall_agent", firewall_agent_node)
graph_builder.add_node("phishing_agent", phishing_agent_node)
graph_builder.add_node("general_chat", general_chat_node)
graph_builder.add_node("risk_engine_node", risk_engine_node)

graph_builder.set_entry_point("route_query")

graph_builder.add_conditional_edges(
    "route_query",
    route_to_subagent,
    {
        "memory_agent": "memory_agent",
        "firewall_agent": "firewall_agent",
        "phishing_agent": "phishing_agent",
        "general_chat": "general_chat",
    },
)

graph_builder.add_edge("memory_agent", "risk_engine_node")
graph_builder.add_edge("firewall_agent", "risk_engine_node")
graph_builder.add_edge("phishing_agent", "risk_engine_node")
graph_builder.add_edge("general_chat", "risk_engine_node")
graph_builder.add_edge("risk_engine_node", END)

privex_app = graph_builder.compile()


if __name__ == "__main__":
    initial_state: AgentState = {
        "user_query": "Summarize my latest downloads",
        "current_agent": "",
        "proposed_action": "",
        "risk_level": "",
        "human_approval_required": False,
    }
    final_state = privex_app.invoke(initial_state)
    print(final_state)