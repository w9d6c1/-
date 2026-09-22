"""日志记录节点 — structlog + error state"""

import copy
import logging

from app.agents.state import AgentState

logger = logging.getLogger("agent")


async def log_node(state: AgentState) -> AgentState:
    result = copy.deepcopy(state)

    try:
        logger.info(
            "agent_turn_complete",
            extra={
                "thread_id": state.get("thread_id"),
                "route": state.get("route"),
                "confidence": state.get("confidence"),
                "faq_hit": state.get("faq_hit"),
                "needs_human": state.get("needs_human"),
            },
        )
    except Exception:
        pass

    result["error"] = None
    return result
