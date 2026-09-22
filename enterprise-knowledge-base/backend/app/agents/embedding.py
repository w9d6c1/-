"""Embedding — SiliconFlow API 优先，本地 BGE 模型兜底

- 优先：SiliconFlow API (BAAI/bge-large-zh-v1.5, 1024 维)
- 兜底：本地 SentenceTransformer (使用 settings.embedding_model，默认 BAAI/bge-large-zh-v1.5)
- 单次批量上限 32 条，自动分批。
"""

import asyncio
import time

import httpx
from sentence_transformers import SentenceTransformer

from app.core.config import settings

BATCH_SIZE = 32

_siliconflow_client: httpx.AsyncClient | None = None
_local_model: SentenceTransformer | None = None
_local_model_lock = asyncio.Lock()

# SiliconFlow 连通性预检结果缓存：避免每次 embed 都 GET /models 往返一次。
_SILICONFLOW_OK: bool | None = None
_SILICONFLOW_CHECK_AT: float = 0.0
_SILICONFLOW_OK_TTL = 60.0
_SILICONFLOW_FAIL_TTL = 30.0


def _get_siliconflow_client() -> httpx.AsyncClient:
    global _siliconflow_client
    if _siliconflow_client is None:
        _siliconflow_client = httpx.AsyncClient(
            base_url=settings.siliconflow_base_url,
            headers={
                "Authorization": f"Bearer {settings.siliconflow_api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(3.0),
        )
    return _siliconflow_client


async def _get_local_model() -> SentenceTransformer:
    global _local_model
    if _local_model is not None:
        return _local_model
    async with _local_model_lock:
        if _local_model is not None:
            return _local_model
        model_path = settings.embedding_model
        _local_model = SentenceTransformer(model_path, device=settings.embedding_device)
        return _local_model


async def _embed_via_siliconflow(texts: list[str]) -> list[list[float]]:
    client = _get_siliconflow_client()
    results: list[list[float]] = []
    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        resp = await client.post(
            "/embeddings",
            json={
                "model": "BAAI/bge-large-zh-v1.5",
                "input": batch,
                "encoding_format": "float",
            },
        )
        resp.raise_for_status()
        body = resp.json()
        data = sorted(body["data"], key=lambda d: d["index"])
        results.extend([d["embedding"] for d in data])
    return results


async def _embed_via_local(texts: list[str]) -> list[list[float]]:
    model = await _get_local_model()
    embeddings = model.encode(texts, batch_size=BATCH_SIZE, show_progress_bar=False)
    return embeddings.tolist()


def _siliconflow_availability() -> bool | None:
    """返回缓存中的预检结论；超时或从未检查过则返回 None（需重新预检）。"""
    global _SILICONFLOW_OK, _SILICONFLOW_CHECK_AT
    if _SILICONFLOW_OK is None:
        return None
    ttl = _SILICONFLOW_OK_TTL if _SILICONFLOW_OK else _SILICONFLOW_FAIL_TTL
    if time.time() - _SILICONFLOW_CHECK_AT < ttl:
        return _SILICONFLOW_OK
    return None


def _remember_siliconflow_availability(ok: bool) -> None:
    global _SILICONFLOW_OK, _SILICONFLOW_CHECK_AT
    _SILICONFLOW_OK = ok
    _SILICONFLOW_CHECK_AT = time.time()


async def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []

    # SiliconFlow API 优先（带快速连通性预检，结果缓存 30~60s）
    if settings.siliconflow_api_key:
        availability = _siliconflow_availability()
        if availability is None:
            try:
                client = _get_siliconflow_client()
                resp = await client.get("/models", timeout=httpx.Timeout(2.0))
                resp.raise_for_status()
                _remember_siliconflow_availability(True)
                availability = True
            except Exception:
                _remember_siliconflow_availability(False)
                availability = False
        if availability:
            try:
                return await _embed_via_siliconflow(texts)
            except Exception:
                pass  # 静默回退到本地模型

    # 本地 BGE 模型兜底
    return await _embed_via_local(texts)


async def embed_query(query: str) -> list[float]:
    vectors = await embed_texts([query])
    return vectors[0]


# ── FAQ 专用（复用主模型） ──────────────────────────────

async def embed_faq_texts(texts: list[str]) -> list[list[float]]:
    return await embed_texts(texts)


async def embed_faq_query(query: str) -> list[float]:
    return await embed_query(query)


# ── 兼容旧接口 ─────────────────────────────────────────

QUERY_CACHE_SIZE = 1000


def create_embed_config():
    from dataclasses import dataclass

    @dataclass
    class EmbedConfig:
        model: str = settings.embedding_model
        device: str = settings.embedding_device

    return EmbedConfig()


def get_embedding_dimension() -> int:
    return 1024


def clear_query_cache() -> None:
    pass


def clear_faq_query_cache() -> None:
    pass
