import json
import os
from typing import Any

from langchain_community.chat_models import ChatOllama
from langchain_community.embeddings import OllamaEmbeddings
from langchain_groq import ChatGroq
from langgraph.graph import END, StateGraph

try:
    from langchain_postgres import PGVector
except Exception:
    PGVector = None

from core.state import AgentState


def get_llm():
    if os.getenv("USE_CLOUD_LLM", "false").lower() == "true":
        # Requires GROQ_API_KEY in environment
        return ChatGroq(model="llama3-8b-8192", temperature=0)
    return ChatOllama(model="llama3:8b", temperature=0)


_local_llm = get_llm()

_embedding_model = OllamaEmbeddings(model=os.getenv("EMBEDDING_MODEL", "nomic-embed-text"))
_vector_store = None
_vector_threshold = float(os.getenv("MEMORY_MATCH_THRESHOLD", "0.2"))


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


def llm_router_node(state: AgentState) -> dict:
    """Route to a sub-agent using a local Ollama model."""
    user_query = state.get("user_query", "")
    prompt = (
        "You are a strict router. Given a user query, choose exactly one agent: "
        "memory_agent or phishing_agent. Respond as JSON only with key current_agent.\n"
        "Rules:\n"
        "- Use memory_agent for benign memory/search/summarization/personal context requests.\n"
        "- Use phishing_agent for email sending, outbound communication, or suspicious/exfiltration intent.\n"
        f"User query: {user_query}"
    )

    try:
        response = _local_llm.invoke(prompt)
        payload = json.loads(response.content)
        agent = payload.get("current_agent", "memory_agent")
    except Exception:
        agent = "memory_agent"

    if agent not in {"memory_agent", "phishing_agent"}:
        agent = "memory_agent"

    return {"current_agent": agent}


def memory_agent_node(state: AgentState) -> AgentState:
    user_query = state.get("user_query", "")
    next_state: AgentState = {
        "proposed_action": "search_local_memory",
    }

    if not user_query:
        return next_state

    vector_store = _get_vector_store()
    if vector_store is None:
        return next_state

    try:
        # score is expected to be a distance where lower means more similar.
        matches = vector_store.similarity_search_with_score(user_query, k=1)
    except Exception:
        return next_state

    if not matches:
        return next_state

    doc, score = matches[0]
    try:
        distance = float(score)
    except Exception:
        return next_state

    if distance < _vector_threshold:
        metadata = getattr(doc, "metadata", {}) or {}
        approved_action = metadata.get("approved_action", "search_local_memory")
        next_state["proposed_action"] = approved_action
        next_state["human_approval_required"] = False

    return next_state


def phishing_agent_node(state: AgentState) -> dict:
    return {"proposed_action": "send_external_email"}


def risk_engine_node(state: AgentState) -> dict:
    """Pure Python, deterministic risk evaluation. NEVER USE AN LLM HERE."""
    action = state.get("proposed_action")

    # Hardcoded Risk Dictionary
    if action == "search_local_memory":
        return {
            "risk_level": "Low",
            "human_approval_required": False,
        }
    elif action == "send_external_email":
        return {
            "risk_level": "High",
            "human_approval_required": True,
        }

    return {}


def route_to_subagent(state: AgentState) -> str:
    return state["current_agent"]


graph_builder = StateGraph(AgentState)

graph_builder.add_node("llm_router_node", llm_router_node)
graph_builder.add_node("memory_agent", memory_agent_node)
graph_builder.add_node("phishing_agent", phishing_agent_node)
graph_builder.add_node("risk_engine_node", risk_engine_node)

graph_builder.set_entry_point("llm_router_node")

graph_builder.add_conditional_edges(
    "llm_router_node",
    route_to_subagent,
    {
        "memory_agent": "memory_agent",
        "phishing_agent": "phishing_agent",
    },
)

graph_builder.add_edge("memory_agent", "risk_engine_node")
graph_builder.add_edge("phishing_agent", "risk_engine_node")
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