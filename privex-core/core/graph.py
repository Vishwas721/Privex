import random

from langgraph.graph import END, StateGraph

from core.state import AgentState


def llm_router_node(state: AgentState) -> dict:
    """Simulate LLM routing by selecting a sub-agent."""
    return {"current_agent": random.choice(["memory_agent", "phishing_agent"])}


def memory_agent_node(state: AgentState) -> dict:
    return {"proposed_action": "search_local_memory"}


def phishing_agent_node(state: AgentState) -> dict:
    return {"proposed_action": "send_external_email"}


def risk_engine_node(state: AgentState) -> dict:
    """Pure Python, deterministic risk evaluation."""
    action = state.get("proposed_action")

    if action == "search_local_memory":
        return {
            "risk_level": "Low", 
            "human_approval_required": False
        }
    elif action == "send_external_email":
        return {
            "risk_level": "High", 
            "human_approval_required": True
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