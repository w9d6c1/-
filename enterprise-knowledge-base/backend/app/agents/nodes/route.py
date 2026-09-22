"""路由分发节点 — 按 user_scope 强制分流 🔒"""

import copy

from app.agents.state import AgentState


def route_node(state: AgentState) -> AgentState:
    result = copy.deepcopy(state)

    if state.get("is_blocked"):
        result["route"] = "reject"
        return result

    scopes = state.get("user_scopes", [])
    if not scopes:
        result["route"] = "reject"
        return result

    query = state.get("rewritten_query") or state.get("original_query", "")
    query_len = len(query)

    if query_len <= 15:
        result["route"] = "faq"
    else:
        result["route"] = "retrieve"

    return result
