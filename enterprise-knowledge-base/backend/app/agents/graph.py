"""LangGraph 智能体图 — 内部问答智能体 (完整11节点 + PostgreSQL Checkpoint)"""

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.graph import END, StateGraph

from app.agents.nodes.auth import authenticate_node
from app.agents.nodes.citation import citation_node
from app.agents.nodes.context import assemble_context
from app.agents.nodes.faq import faq_match_node
from app.agents.nodes.generate import generate_node
from app.agents.nodes.logging import log_node
from app.agents.nodes.output import validate_output_node
from app.agents.nodes.retrieve import retrieve_node
from app.agents.nodes.rewrite import rewrite_node
from app.agents.nodes.route import route_node
from app.agents.nodes.tools import tool_decision_node
from app.agents.nodes.validate import validate_input_node
from app.agents.state import AgentState
from app.core.config import settings
from app.core.logging import logger

_checkpointer: AsyncPostgresSaver | None = None
_checkpointer_ctx: object | None = None


async def init_checkpointer() -> AsyncPostgresSaver | None:
    global _checkpointer, _checkpointer_ctx
    if _checkpointer is not None:
        return _checkpointer

    try:
        conn_string = settings.postgres_url.replace("+asyncpg", "")
        ctx = AsyncPostgresSaver.from_conn_string(conn_string)
        _checkpointer = await ctx.__aenter__()
        await _checkpointer.setup()
        _checkpointer_ctx = ctx
        logger.info("checkpointer_initialized")
    except Exception:
        logger.warning("checkpointer_init_failed", exc_info=True)
        _checkpointer = None
        _checkpointer_ctx = None

    return _checkpointer


async def shutdown_checkpointer() -> None:
    global _checkpointer, _checkpointer_ctx
    if _checkpointer_ctx is not None:
        try:
            await _checkpointer_ctx.__aexit__(None, None, None)
        except Exception:
            pass
        _checkpointer_ctx = None
        _checkpointer = None


def _after_validate(state: AgentState) -> str:
    route = state.get("route", "")
    if route == "sensitive_canned":
        return END
    return END if state.get("is_blocked") else "auth"


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


def _after_retrieve(state: AgentState) -> str:
    return "tools"


def _after_tools(state: AgentState) -> str:
    iteration = state.get("iteration", 0)
    if iteration >= 3:
        return "context"
    docs = state.get("retrieved_docs", [])
    if not docs:
        return "context"
    return "context"


def _after_output(state: AgentState) -> str:
    if state.get("needs_human"):
        return "log"
    return "log"


def _build_checkpointer():
    return _checkpointer


def build_internal_agent_graph(with_checkpointer: bool = True):
    workflow = StateGraph(AgentState)

    workflow.add_node("validate", validate_input_node)
    workflow.add_node("auth", authenticate_node)
    workflow.add_node("rewrite", rewrite_node)
    workflow.add_node("route", route_node)
    workflow.add_node("faq", faq_match_node)
    workflow.add_node("retrieve", retrieve_node)
    workflow.add_node("tools", tool_decision_node)
    workflow.add_node("context", assemble_context)
    workflow.add_node("generate", generate_node)
    workflow.add_node("citation", citation_node)
    workflow.add_node("output", validate_output_node)
    workflow.add_node("log", log_node)

    workflow.set_entry_point("validate")

    workflow.add_conditional_edges("validate", _after_validate, {"auth": "auth", END: END})
    workflow.add_edge("auth", "rewrite")
    workflow.add_edge("rewrite", "route")
    workflow.add_conditional_edges("route", _after_route, {"faq": "faq", "retrieve": "retrieve", END: END})
    workflow.add_conditional_edges("faq", _after_faq, {"generate": "generate", "retrieve": "retrieve"})
    workflow.add_edge("retrieve", "tools")
    workflow.add_conditional_edges("tools", _after_tools, {"context": "context"})
    workflow.add_edge("context", "generate")
    workflow.add_edge("generate", "citation")
    workflow.add_edge("citation", "output")
    workflow.add_conditional_edges("output", _after_output, {"log": "log"})
    workflow.add_edge("log", END)

    checkpointer = None
    if with_checkpointer:
        checkpointer = _build_checkpointer()

    if checkpointer:
        return workflow.compile(checkpointer=checkpointer)
    return workflow.compile()
