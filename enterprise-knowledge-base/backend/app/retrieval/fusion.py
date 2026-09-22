"""RRF 双路融合 — BM25 + Dense → 统一排名"""

from dataclasses import dataclass, field

from app.agents.embedding import embed_query
from app.retrieval.es_client import ESResult, bm25_search
from app.retrieval.milvus_client import MilvusResult, dense_search


@dataclass
class FusionResult:
    unique_id: str
    doc_id: int
    chunk_index: int
    content: str
    fused_score: float
    scope: str
    rerank_score: float = 0.0
    metadata: dict = field(default_factory=dict)


def reciprocal_rank_fusion(
    bm25_results: list[ESResult],
    dense_results: list[MilvusResult],
    k: int = 60,
) -> list[FusionResult]:
    score_map: dict[str, float] = {}
    content_map: dict[str, str] = {}
    meta_map: dict[str, dict] = {}
    scope_map: dict[str, str] = {}

    for rank, r in enumerate(bm25_results):
        uid = f"{r.doc_id}_{r.chunk_index}"
        score_map[uid] = score_map.get(uid, 0) + 1.0 / (k + rank + 1)
        content_map[uid] = r.content
        meta_map[uid] = r.metadata
        scope_map[uid] = r.scope

    for rank, r in enumerate(dense_results):
        uid = f"{r.doc_id}_{r.chunk_index}"
        score_map[uid] = score_map.get(uid, 0) + 1.0 / (k + rank + 1)
        if uid not in content_map:
            content_map[uid] = r.content
            meta_map[uid] = r.metadata
            scope_map[uid] = r.scope

    results: list[FusionResult] = []
    for uid, score in score_map.items():
        doc_id_str, chunk_str = uid.split("_", 1)
        results.append(FusionResult(
            unique_id=uid,
            doc_id=int(doc_id_str),
            chunk_index=int(chunk_str),
            content=content_map.get(uid, ""),
            fused_score=score,
            scope=scope_map.get(uid, "public"),
            metadata=meta_map.get(uid, {}),
        ))

    results.sort(key=lambda r: r.fused_score, reverse=True)
    return results


def deduplicate_by_id(results: list[FusionResult]) -> list[FusionResult]:
    seen: dict[str, FusionResult] = {}
    for r in results:
        if r.unique_id not in seen or r.fused_score > seen[r.unique_id].fused_score:
            seen[r.unique_id] = r
    deduped = list(seen.values())
    deduped.sort(key=lambda r: r.fused_score, reverse=True)
    return deduped


async def hybrid_retrieve(
    query: str,
    scope: str = "public",
    top_k: int = 10,
) -> list[FusionResult]:
    query_vec = await embed_query(query)

    bm25_task = bm25_search(query, scope=scope, top_k=top_k)
    dense_task = dense_search(query_vec, scope=scope, top_k=top_k)

    bm25_results = await bm25_task
    dense_results = await dense_task

    fused = reciprocal_rank_fusion(bm25_results, dense_results)
    fused = deduplicate_by_id(fused)
    return fused[:top_k]
