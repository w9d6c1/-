"""客服 FAQ 匹配节点 — 仅匹配 public/customer scope"""

import copy

import numpy as np

from app.agents.embedding import embed_faq_query as embed_query
from app.agents.llm import clean_response
from app.agents.nodes.faq import (
    FAQ_MATCH_THRESHOLD,
    _best_faq_match,
    _normalize_rows,
    get_faq_vectors,
)
from app.agents.state import AgentState

_CUSTOMER_SCOPES = {"public", "customer"}


async def customer_faq_match_node(state: AgentState) -> AgentState:
    result = copy.deepcopy(state)
    result["faq_hit"] = False
    result["faq_answer"] = None

    query = state.get("rewritten_query") or state.get("original_query", "")
    if not query:
        return result

    vectors = get_faq_vectors()
    if not vectors:
        return result

    query_vec = await embed_query(query)

    matrix = _normalize_rows(np.asarray([e["vector"] for e in vectors], dtype=np.float32))
    scopes_list = [e["scope"] for e in vectors]
    best_score, best_answer = _best_faq_match(
        query_vec, vectors, matrix, scopes_list, _CUSTOMER_SCOPES
    )

    if best_score >= FAQ_MATCH_THRESHOLD and best_answer is not None:
        result["faq_hit"] = True
        result["faq_answer"] = best_answer
        result["context"] = f"参考FAQ答案：\n{clean_response(best_answer)}"

    return result
