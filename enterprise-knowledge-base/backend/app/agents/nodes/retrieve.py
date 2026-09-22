"""混合检索节点 — 双路召回 → RRF → Reranker + Redis 缓存"""

import asyncio
import copy
import json

from app.agents.cache import build_cache_key, get_cache
from app.agents.state import AgentState
from app.retrieval.doc_images import build_image_registry
from app.retrieval.fusion import FusionResult, hybrid_retrieve
from app.retrieval.reranker import rerank

_RETRIEVE_TIMEOUT = 15


async def retrieve_node(state: AgentState) -> AgentState:
    result = copy.deepcopy(state)
    query = state.get("rewritten_query") or state.get("original_query", "")
    if not query:
        result["retrieved_docs"] = []
        return result

    scopes = state.get("user_scopes", ["public"])
    role = state.get("user_role", "readonly")
    scope_key = "+".join(sorted(scopes))
    cache_key = build_cache_key(query, scope_key, role)

    try:
        cache = get_cache()
        cached = await cache.get(cache_key)
        if cached and "docs" in cached:
            docs = [_cached_to_fusion(d) for d in cached["docs"]]
            result["retrieved_docs"] = docs
            result["doc_images"] = await build_image_registry(docs)
            return result
    except Exception:
        pass

    all_docs: list[FusionResult] = []

    async def _retrieve_scope(scope: str) -> list[FusionResult]:
        try:
            return await asyncio.wait_for(
                hybrid_retrieve(query, scope=scope, top_k=10),
                timeout=_RETRIEVE_TIMEOUT,
            )
        except (asyncio.TimeoutError, Exception):
            return []

    scope_results = await asyncio.gather(*(_retrieve_scope(s) for s in scopes))
    for docs in scope_results:
        all_docs.extend(docs)

    all_docs.sort(key=lambda d: d.fused_score, reverse=True)

    if all_docs:
        try:
            all_docs = await rerank(query, all_docs, top_k=5)
        except Exception:
            all_docs = all_docs[:5]

    try:
        cache = get_cache()
        serializable = [_fusion_to_dict(d) for d in all_docs]
        await cache.set(cache_key, {"docs": serializable}, ttl=300)
    except Exception:
        pass

    result["retrieved_docs"] = all_docs
    result["doc_images"] = await build_image_registry(all_docs)
    return result


def _fusion_to_dict(doc: FusionResult) -> dict:
    return {
        "unique_id": doc.unique_id,
        "doc_id": doc.doc_id,
        "chunk_index": doc.chunk_index,
        "content": doc.content,
        "fused_score": doc.fused_score,
        "scope": doc.scope,
        "metadata": doc.metadata,
    }


def _cached_to_fusion(data: dict) -> FusionResult:
    return FusionResult(
        unique_id=data["unique_id"],
        doc_id=data["doc_id"],
        chunk_index=data["chunk_index"],
        content=data["content"],
        fused_score=data["fused_score"],
        scope=data["scope"],
        metadata=data.get("metadata", {}),
    )
