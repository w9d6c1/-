"""客服智能体 — 受限 scope + 转人工决策 + 输入/输出安全校验"""

import copy

from langgraph.graph import END, StateGraph

from app.agents.customer.faq import customer_faq_match_node
from app.agents.customer.generate import customer_generate_node
from app.agents.customer.retrieve import customer_retrieve_node
from app.agents.nodes.context import assemble_context
from app.agents.nodes.output import validate_output_node
from app.agents.nodes.validate import validate_input_node
from app.agents.state import AgentState


def create_customer_state(
    thread_id: str,
    query: str,
    user_id: int | None = None,
    user_role: str = "readonly",
    user_department: str | None = None,
) -> AgentState:
    from langchain_core.messages import HumanMessage

    return AgentState(
        messages=[HumanMessage(content=query)],
        thread_id=thread_id,
        user_id=user_id,
        user_role=user_role,
        user_department=user_department,
        user_scopes=["public", "customer"],
        original_query=query,
        rewritten_query="",
        is_blocked=False,
        block_reason="",
        faq_hit=False,
        faq_answer=None,
        retrieved_docs=[],
        context="",
        final_answer="",
        is_compliant=True,
        compliance_issues=[],
        confidence=0.0,
        needs_human=False,
        human_reason="",
        route="",
        iteration=0,
        error=None,
    )


_HUMAN_KEYWORDS = [
    "转人工", "人工客服", "人工服务", "找人工", "客服电话",
    "投诉", "退款", "维权", "12315",
]
_SENSITIVE_KEYWORDS = ["投诉", "退款", "维权", "泄露", "诈骗"]


def _strip_internal_scopes(state: AgentState) -> AgentState:
    """剥离 internal scope，仅保留 public + customer"""
    result = copy.deepcopy(state)
    scopes = state.get("user_scopes", [])
    safe_scopes = [s for s in scopes if s != "internal"]
    if not safe_scopes:
        safe_scopes = ["public"]
    result["user_scopes"] = safe_scopes
    return result


def customer_route_node(state: AgentState) -> AgentState:
    result = _strip_internal_scopes(state)

    scopes = result.get("user_scopes", [])
    if not scopes:
        result["route"] = "reject"
        return result

    query = state.get("rewritten_query") or state.get("original_query", "")
    if not query or not query.strip():
        result["route"] = "reject"
        return result

    if len(query) <= 15:
        result["route"] = "faq"
    else:
        result["route"] = "retrieve"

    return result


def human_handoff_node(state: AgentState) -> AgentState:
    result = copy.deepcopy(state)
    query = state.get("original_query", "")
    confidence = state.get("confidence", 1.0)
    human_reasons: list[str] = []

    if confidence < 0.5:
        human_reasons.append(f"low_confidence:{confidence:.2f}")

    for kw in _HUMAN_KEYWORDS:
        if kw in query:
            human_reasons.append(f"user_keyword:{kw}")
            break

    for kw in _SENSITIVE_KEYWORDS:
        if kw in query:
            human_reasons.append(f"sensitive_topic:{kw}")
            break

    if human_reasons:
        result["needs_human"] = True
        result["human_reason"] = "; ".join(human_reasons)
    else:
        result["needs_human"] = False
        result["human_reason"] = ""

    return result


def _after_validate(state: AgentState) -> str:
    return END if state.get("is_blocked") else "route"


def _after_route(state: AgentState) -> str:
    route = state.get("route", "")
    if route == "reject":
        return END
    if route == "faq":
        return "faq"
    return "retrieve"


def _after_faq(state: AgentState) -> str:
    if state.get("faq_hit"):
        return "generate"
    return "retrieve"


def build_customer_agent_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("validate", validate_input_node)
    workflow.add_node("route", customer_route_node)
    workflow.add_node("faq", customer_faq_match_node)
    workflow.add_node("retrieve", customer_retrieve_node)
    workflow.add_node("context", assemble_context)
    workflow.add_node("generate", customer_generate_node)
    workflow.add_node("output", validate_output_node)
    workflow.add_node("handoff", human_handoff_node)

    workflow.set_entry_point("validate")

    workflow.add_conditional_edges("validate", _after_validate, {"route": "route", END: END})
    workflow.add_conditional_edges("route", _after_route, {"faq": "faq", "retrieve": "retrieve", END: END})
    workflow.add_conditional_edges("faq", _after_faq, {"generate": "generate", "retrieve": "retrieve"})
    workflow.add_edge("retrieve", "context")
    workflow.add_edge("context", "generate")
    workflow.add_edge("generate", "output")
    workflow.add_edge("output", "handoff")
    workflow.add_edge("handoff", END)

    from app.agents.graph import _checkpointer
    if _checkpointer:
        return workflow.compile(checkpointer=_checkpointer)
    return workflow.compile()
