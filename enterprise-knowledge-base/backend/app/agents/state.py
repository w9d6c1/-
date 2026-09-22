"""AgentState — LangGraph 状态定义"""

from langchain_core.messages import BaseMessage, HumanMessage
from typing_extensions import TypedDict

from app.retrieval.fusion import FusionResult


class AgentState(TypedDict, total=False):
    messages: list[BaseMessage]
    thread_id: str
    user_id: int | None
    user_role: str
    user_department: str | None
    user_scopes: list[str]
    original_query: str
    rewritten_query: str
    is_blocked: bool
    block_reason: str
    faq_hit: bool
    faq_answer: str | None
    faq_direct: bool
    retrieved_docs: list[FusionResult]
    doc_images: list[dict]
    context: str
    context_doc_indices: list[int]
    citations: list[dict]
    final_answer: str
    is_compliant: bool
    compliance_issues: list[str]
    confidence: float
    needs_human: bool
    human_reason: str
    route: str
    iteration: int
    error: str | None
    channel: str


def create_initial_state(
    thread_id: str,
    query: str,
    user_id: int | None = None,
    user_role: str = "readonly",
    user_department: str | None = None,
    user_scopes: list[str] | None = None,
    channel: str = "",
) -> AgentState:
    return AgentState(
        messages=[HumanMessage(content=query)],
        thread_id=thread_id,
        user_id=user_id,
        user_role=user_role,
        user_department=user_department,
        user_scopes=user_scopes or ["public"],
        original_query=query,
        rewritten_query="",
        is_blocked=False,
        block_reason="",
        faq_hit=False,
        faq_answer=None,
        retrieved_docs=[],
        context="",
        context_doc_indices=[],
        citations=[],
        final_answer="",
        is_compliant=True,
        compliance_issues=[],
        confidence=0.0,
        needs_human=False,
        human_reason="",
        route="",
        iteration=0,
        error=None,
        channel=channel,
    )
