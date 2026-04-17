import json
import os
import re
from typing import Literal

from langchain_community.chat_models import ChatOllama
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from langgraph.graph import END, StateGraph

from core.state import AgentState
from core.graph_store import get_graph_store
from core.vector_store import get_vector_store as _get_vector_store


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


def route_query(state: AgentState) -> dict:
    """Deterministically map user input to one sub-agent."""
    user_query = state.get("user_query", "")
    messages = [
        (
            "system",
            "You are a strict conversational router. Choose one agent based on the user's input:\n\n"
            "memory_agent: Choose this for ANY question about the past, history, or what the user was doing. EVEN IF the user asks about 'secrets', 'passwords', or 'keys', if it is framed as a question, route it here.\n"
            "firewall_agent: Choose this ONLY IF the input is a raw, unstructured OCR text dump that looks like a screen capture containing a secret.\n"
            "phishing_agent: Choose this for analyzing suspicious emails or URLs.\n"
            "general_chat: Choose this for normal conversation, greetings, or unclear text.\n\n"
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
        print(f"🧭 [Router] User asked: '{user_query}' -> Routed to: {decision.selected_agent}")
        return {"current_agent": decision.selected_agent}
    except Exception as exc:
        print(f"❌ [Router] FATAL ERROR: {exc}")
        return {"current_agent": "firewall_agent"}


def memory_agent_node(state: AgentState) -> dict:
    query = state.get("user_query", "")
    keywords = [tok.lower() for tok in re.findall(r"[A-Za-z0-9_]+", query) if len(tok) > 2][:10]
    print(f"🧠 [Memory Agent] Extracted Graph Keywords: {keywords}")

    vector_store = _get_vector_store()
    docs = []
    if vector_store is not None:
        try:
            docs = vector_store.similarity_search(query, k=5)
        except Exception:
            docs = []

    graph_rows = []
    try:
        graph_store = get_graph_store()
        if graph_store is not None:
            graph_cypher = """
            MATCH (evt:Alert)
            OPTIONAL MATCH (evt)-[:OCCURRED_IN]->(app:Application)
            OPTIONAL MATCH (evt)-[:EXPOSED]->(sec:Secret)
            OPTIONAL MATCH (evt)-[:HAPPENED_ON]->(d:Date)
            RETURN evt.timestamp AS timestamp,
                   app.name AS application,
                   sec.type AS secret_type,
                   d.date AS event_date,
                   evt.summary AS summary
                 ORDER BY CASE WHEN sec.type = 'Unknown' THEN 1 ELSE 0 END ASC, timestamp DESC
                 LIMIT 60
            """
            graph_rows = graph_store.query(graph_cypher, {}) or []
    except Exception as exc:
        print(f"❌ [Memory Agent] GRAPH QUERY FAILED: {exc}")

    print(f"📊 [Memory Agent] Retrieval Stats -> Vector Docs: {len(docs)} | Graph Rows: {len(graph_rows)}")

    has_context = bool(docs or graph_rows)
    if not has_context:
        return {
            "response": "I don't have any memories matching that request yet.",
            "human_approval_required": False,
        }

    vector_context = "\n".join(
        f"[App: {(getattr(doc, 'metadata', {}) or {}).get('active_app')}] - {getattr(doc, 'page_content', '')}"
        for doc in docs
    )

    graph_context = "\n".join(
        f"[Graph | App: {row.get('application') or 'Unknown'} | Secret: {row.get('secret_type') or 'Unknown'} | Date: {row.get('event_date') or 'Unknown'}] - {row.get('summary') or 'No summary'}"
        for row in graph_rows
    )

    formatted_context = "\n\n".join(
        part for part in [
            f"Vector Context:\n{vector_context}" if vector_context else "",
            f"Graph Context:\n{graph_context}" if graph_context else "",
        ] if part
    )

    print("\n🚨 --- WHAT THE LLM SEES (GRAPH CONTEXT) --- 🚨")
    print(formatted_context)
    print("🚨 ----------------------------------------- 🚨\n")

    # 1. Use the fallback-aware LLM for conversation
    chat_llm = get_llm(temperature=0.3, is_json=False)

    system_text = (
        "You are Privex, a highly precise, privacy-first AI. Answer the user's question using ONLY the Memory Context below.\n"
        "RULE 1: A 'secret' strictly refers to specific cryptographic keys or credentials (e.g., AWS Key, Database Password, GitHub Token).\n"
        "RULE 2: If a row says 'Secret: Unknown', 'Secret: none', or 'Secret: secret', IT IS A FALSE POSITIVE. Ignore it completely when looking for secrets.\n"
        "RULE 3: If the user asks about ANY topic, event, application, or secret that is NOT explicitly mentioned in the Memory Context, do NOT guess, hypothesize, or list other platforms. You MUST reply EXACTLY with: 'I have no memory of this in my current context.'\n\n"
        f"Memory Context:\n{formatted_context}"
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
    except Exception as e:
        print(f"❌ [Memory Agent] LLM GENERATION FAILED: {type(e).__name__} - {e}")
        import traceback
        traceback.print_exc()
        return {
            "response": "I am having trouble connecting to my memory bank.",
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