"""Reranker 重排序 — SiliconFlow API (bge-reranker-v2-m3)"""

import copy
from dataclasses import dataclass

import httpx

from app.core.config import settings
from app.retrieval.fusion import FusionResult

_http_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(
            base_url=settings.siliconflow_base_url,
            headers={
                "Authorization": f"Bearer {settings.siliconflow_api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(30.0),
        )
    return _http_client


@dataclass
class RerankerConfig:
    model: str
    device: str


def create_reranker_config() -> RerankerConfig:
    return RerankerConfig(
        model=settings.reranker_model,
        device=settings.reranker_device,
    )


async def rerank(
    query: str,
    results: list[FusionResult],
    top_k: int = 5,
) -> list[FusionResult]:
    if not results:
        return []

    documents = [r.content for r in results]
    try:
        client = _get_client()
        resp = await client.post(
            "/rerank",
            json={
                "model": settings.reranker_model,
                "query": query,
                "documents": documents,
            },
        )
        resp.raise_for_status()
        body = resp.json()
        scored = {r["index"]: r["relevance_score"] for r in body["results"]}
    except Exception:
        reranked = [copy.copy(r) for r in results]
        for r in reranked:
            r.rerank_score = r.fused_score
        reranked.sort(key=lambda r: r.rerank_score, reverse=True)
        return reranked[:top_k]

    reranked: list[FusionResult] = []
    for i, r in enumerate(results):
        new_r = copy.copy(r)
        new_r.rerank_score = float(scored.get(i, r.fused_score))
        reranked.append(new_r)

    reranked.sort(key=lambda r: r.rerank_score, reverse=True)
    return reranked[:top_k]
