"""RRF 双路融合 测试 (TDD: RED)"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from app.retrieval.fusion import (
    FusionResult,
    reciprocal_rank_fusion,
    deduplicate_by_id,
    hybrid_retrieve,
)
from app.retrieval.es_client import ESResult
from app.retrieval.milvus_client import MilvusResult


def make_es(doc_id, chunk_idx, score, content="test"):
    return ESResult(doc_id=doc_id, chunk_index=chunk_idx, score=score, content=content, scope="public")


def make_mv(doc_id, chunk_idx, score, content="test"):
    return MilvusResult(doc_id=doc_id, chunk_index=chunk_idx, score=score, content=content, scope="public")


class TestRRF:
    def test_rrf_merges_two_lists(self):
        bm25 = [make_es(1, 0, 3.0), make_es(2, 0, 2.0)]
        dense = [make_mv(1, 0, 0.95), make_mv(3, 0, 0.80)]
        results = reciprocal_rank_fusion(bm25, dense, k=60)
        assert len(results) >= 3
        ids = {r.unique_id for r in results}
        assert "1_0" in ids
        assert "2_0" in ids
        assert "3_0" in ids

    def test_rrf_sorts_by_fused_score(self):
        bm25 = [make_es(1, 0, 5.0), make_es(2, 0, 1.0)]
        dense = [make_mv(2, 0, 0.99), make_mv(1, 0, 0.50)]
        results = reciprocal_rank_fusion(bm25, dense, k=60)
        assert results[0].fused_score >= results[-1].fused_score

    def test_rrf_both_empty(self):
        results = reciprocal_rank_fusion([], [], k=60)
        assert results == []

    def test_rrf_one_empty(self):
        bm25 = [make_es(1, 0, 3.0)]
        results = reciprocal_rank_fusion(bm25, [], k=60)
        assert len(results) == 1
        assert results[0].unique_id == "1_0"


class TestDedup:
    def test_dedup_keeps_higher_score(self):
        r1 = FusionResult(unique_id="1_0", doc_id=1, chunk_index=0, content="a", fused_score=0.9, scope="public")
        r2 = FusionResult(unique_id="1_0", doc_id=1, chunk_index=0, content="a", fused_score=0.95, scope="public")
        results = deduplicate_by_id([r1, r2])
        assert len(results) == 1
        assert results[0].fused_score == 0.95

    def test_dedup_preserves_distinct(self):
        r1 = FusionResult(unique_id="1_0", doc_id=1, chunk_index=0, content="a", fused_score=0.9, scope="public")
        r2 = FusionResult(unique_id="2_1", doc_id=2, chunk_index=1, content="b", fused_score=0.8, scope="public")
        results = deduplicate_by_id([r1, r2])
        assert len(results) == 2


class TestHybridRetrieve:
    @pytest.mark.asyncio
    async def test_hybrid_combines_both(self):
        bm25 = [make_es(1, 0, 3.0), make_es(2, 0, 2.5)]
        dense = [make_mv(1, 0, 0.95), make_mv(3, 0, 0.85)]

        with patch("app.retrieval.fusion.bm25_search", new=AsyncMock(return_value=bm25)):
            with patch("app.retrieval.fusion.dense_search", new=AsyncMock(return_value=dense)):
                with patch("app.retrieval.fusion.embed_query", return_value=[0.1] * 1024):
                    results = await hybrid_retrieve("测试查询", scope="public", top_k=5)
                    assert len(results) >= 2
                    assert all(isinstance(r, FusionResult) for r in results)
