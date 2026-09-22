"""BGE-Reranker 重排序测试 — 对齐 SiliconFlow HTTP API（httpx.AsyncClient → /rerank）"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.retrieval.fusion import FusionResult


def _make(uid, doc_id, chk, content, score):
    return FusionResult(unique_id=uid, doc_id=doc_id, chunk_index=chk, content=content, fused_score=score, scope="public")


class TestRerankerConfig:
    def test_reranker_config_from_settings(self):
        from app.retrieval.reranker import RerankerConfig, create_reranker_config

        cfg = create_reranker_config()
        assert cfg.model == "BAAI/bge-reranker-v2-m3"
        assert cfg.device == "cpu"


class TestRerank:
    @pytest.mark.asyncio
    async def test_rerank_returns_sorted_by_score(self):
        from app.retrieval.reranker import rerank

        docs = [
            _make("1_0", 1, 0, "考勤制度说明", 0.9),
            _make("2_0", 2, 0, "天气预报", 0.8),
            _make("3_0", 3, 0, "打卡流程", 0.7),
        ]
        mock = MagicMock()
        mock.post = AsyncMock(return_value=MagicMock(json=MagicMock(return_value={
            "results": [
                {"index": 0, "relevance_score": 0.95},
                {"index": 1, "relevance_score": 0.10},
                {"index": 2, "relevance_score": 0.85},
            ]
        }), raise_for_status=MagicMock()))
        with patch("app.retrieval.reranker._http_client", mock):
            results = await rerank("考勤打卡", docs, top_k=3)
        assert len(results) == 3
        assert results[0].rerank_score >= results[-1].rerank_score

    @pytest.mark.asyncio
    async def test_rerank_top_k_truncation(self):
        from app.retrieval.reranker import rerank

        docs = [_make(f"{i}_0", i, 0, f"文档{i}", 0.5) for i in range(1, 11)]
        mock = MagicMock()
        mock.post = AsyncMock(return_value=MagicMock(json=MagicMock(return_value={
            "results": [{"index": i, "relevance_score": 0.5} for i in range(10)]
        }), raise_for_status=MagicMock()))
        with patch("app.retrieval.reranker._http_client", mock):
            results = await rerank("查询", docs, top_k=5)
        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_rerank_empty_input(self):
        from app.retrieval.reranker import rerank
        assert await rerank("查询", [], top_k=5) == []

    @pytest.mark.asyncio
    async def test_rerank_fallback_on_client_error(self):
        from app.retrieval.reranker import rerank

        docs = [
            _make("1_0", 1, 0, "考勤制度", 0.9),
            _make("2_0", 2, 0, "请假流程", 0.8),
        ]
        mock = MagicMock()
        mock.post = AsyncMock(side_effect=RuntimeError("connection refused"))
        with patch("app.retrieval.reranker._http_client", mock):
            results = await rerank("考勤", docs, top_k=3)
        assert len(results) == 2
        # fallback uses fused_score as rerank_score
        assert results[0].rerank_score == 0.9
        assert results[1].rerank_score == 0.8
