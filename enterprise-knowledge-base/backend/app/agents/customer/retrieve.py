"""客服检索节点 — 仅 customer + public scope"""

import asyncio
import copy

from app.agents.state import AgentState
from app.retrieval.doc_images import build_image_registry
from app.retrieval.fusion import hybrid_retrieve
from app.retrieval.reranker import rerank


async def customer_retrieve_node(state: AgentState) -> AgentState:
    result = copy.deepcopy(state)
    query = state.get("rewritten_query") or state.get("original_query", "")
    if not query:
        result["retrieved_docs"] = []
        return result

    scopes = [s for s in state.get("user_scopes", ["public"]) if s != "internal"]
    if not scopes:
        scopes = ["public"]

    all_docs: list = []
    for scope in scopes:
        try:
            docs = await asyncio.wait_for(
                hybrid_retrieve(query, scope=scope, top_k=10),
                timeout=15,
            )
            all_docs.extend(docs)
        except (asyncio.TimeoutError, Exception):
            continue

    all_docs.sort(key=lambda d: d.fused_score, reverse=True)

    if all_docs:
        try:
            all_docs = await rerank(query, all_docs, top_k=5)
        except Exception:
            all_docs = all_docs[:5]

    result["retrieved_docs"] = all_docs
    result["doc_images"] = await build_image_registry(all_docs)
    return result
