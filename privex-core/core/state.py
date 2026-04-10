from typing import NotRequired, TypedDict


class AgentState(TypedDict):
    """Shared state for deterministic routing and risk evaluation."""

    user_query: str
    current_agent: str
    proposed_action: str
    risk_level: str
    human_approval_required: bool
    response: NotRequired[str]