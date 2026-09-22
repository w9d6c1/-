"""ES BM25 检索 测试 (TDD: RED)"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.retrieval.es_client import (
    ESConfig,
    ESResult,
    create_es_config,
    get_index_name,
    bm25_search,
    index_documents,
)


class TestESConfig:
    def test_create_from_settings(self):
        cfg = create_es_config()
        assert cfg.host == "elasticsearch"
        assert cfg.port == 9200
        assert "elasticsearch:9200" in cfg.url

    def test_custom_config(self):
        cfg = ESConfig(host="test-host", port=9200)
        assert cfg.host == "test-host"
        assert cfg.url == "http://test-host:9200"


class TestIndexName:
    def test_public_scope(self):
        assert get_index_name("public") == "idx_bm25_public"

    def test_internal_scope(self):
        assert get_index_name("internal") == "idx_bm25_internal"

    def test_customer_scope(self):
        assert get_index_name("customer") == "idx_bm25_customer"

    def test_default_scope(self):
        assert get_index_name(None) == "idx_bm25_public"


class TestBM25Search:
    @pytest.mark.asyncio
    async def test_search_returns_results(self):
        mock_es = AsyncMock()
        mock_es.search.return_value = {
            "hits": {
                "total": {"value": 2},
                "hits": [
                    {
                        "_id": "100_0",
                        "_score": 2.5,
                        "_source": {
                            "content": "考勤制度说明",
                            "doc_id": 100,
                            "chunk_index": 0,
                            "scope": "public",
                            "title": "考勤手册",
                        },
                    },
                ],
            }
        }

        with patch("app.retrieval.es_client._es_client", mock_es):
            results = await bm25_search("考勤", scope="public", top_k=5)
            assert len(results) == 1
            assert results[0].doc_id == 100
            assert results[0].chunk_index == 0
            assert results[0].score == 2.5
            assert "考勤" in results[0].content

    @pytest.mark.asyncio
    async def test_search_empty_result(self):
        mock_es = AsyncMock()
        mock_es.search.return_value = {
            "hits": {"total": {"value": 0}, "hits": []}
        }

        with patch("app.retrieval.es_client._es_client", mock_es):
            results = await bm25_search("不存在的内容", scope="public", top_k=5)
            assert len(results) == 0
            assert results == []

    @pytest.mark.asyncio
    async def test_search_with_scope_filter(self):
        mock_es = AsyncMock()
        mock_es.search.return_value = {
            "hits": {"total": {"value": 1}, "hits": [
                {"_id": "200_0", "_score": 1.0, "_source": {"content": "内部", "doc_id": 200, "chunk_index": 0, "scope": "internal", "title": "内部文档"}},
            ]}
        }

        with patch("app.retrieval.es_client._es_client", mock_es):
            results = await bm25_search("内部", scope="internal", top_k=3)
            assert len(results) == 1
            assert results[0].scope == "internal"


class TestIndexDocuments:
    @pytest.mark.asyncio
    async def test_index_bulk_write(self):
        from langchain_core.documents import Document

        docs = [
            Document(page_content="测试内容一", metadata={"doc_id": 1, "chunk_index": 0, "scope": "public", "title": "测试"}),
            Document(page_content="测试内容二", metadata={"doc_id": 1, "chunk_index": 1, "scope": "public", "title": "测试"}),
        ]

        mock_es = AsyncMock()
        mock_es.bulk.return_value = {
            "errors": False,
            "items": [
                {"index": {"result": "created"}},
                {"index": {"result": "created"}},
            ],
        }

        with patch("app.retrieval.es_client._es_client", mock_es):
            count = await index_documents(docs)
            assert count == 2
            mock_es.bulk.assert_called_once()
            operations = mock_es.bulk.call_args.kwargs["operations"]
            doc_bodies = [op for op in operations if "content" in op]
            assert len(doc_bodies) == 2
            assert all(op["source_type"] == "internal" for op in doc_bodies)


class TestBM25SourceType:
    @pytest.mark.asyncio
    async def test_search_returns_source_type(self):
        mock_es = AsyncMock()
        mock_es.search.return_value = {
            "hits": {"total": {"value": 1}, "hits": [
                {"_id": "300_0", "_score": 1.5, "_source": {"content": "公众号文章", "doc_id": 300, "chunk_index": 0, "scope": "public", "title": "t", "source_type": "wechat"}},
            ]}
        }
        with patch("app.retrieval.es_client._es_client", mock_es):
            results = await bm25_search("文章", scope="public", top_k=5)
            assert results[0].metadata["source_type"] == "wechat"

    @pytest.mark.asyncio
    async def test_search_defaults_source_type_internal(self):
        mock_es = AsyncMock()
        mock_es.search.return_value = {
            "hits": {"total": {"value": 1}, "hits": [
                {"_id": "301_0", "_score": 1.0, "_source": {"content": "旧文档", "doc_id": 301, "chunk_index": 0, "scope": "public", "title": "t"}},
            ]}
        }
        with patch("app.retrieval.es_client._es_client", mock_es):
            results = await bm25_search("旧", scope="public", top_k=5)
            assert results[0].metadata["source_type"] == "internal"


class TestEnsureSourceTypeMapping:
    @pytest.mark.asyncio
    async def test_put_mapping_when_index_exists(self):
        from app.retrieval.es_client import ensure_source_type_mapping

        mock_es = AsyncMock()
        mock_es.indices.exists.return_value = True
        with patch("app.retrieval.es_client._es_client", mock_es):
            ok = await ensure_source_type_mapping("public")
            assert ok is True
            mock_es.indices.put_mapping.assert_awaited_once()
            kwargs = mock_es.indices.put_mapping.call_args.kwargs
            assert kwargs["index"] == "idx_bm25_public"
            assert kwargs["properties"]["source_type"]["type"] == "keyword"

    @pytest.mark.asyncio
    async def test_skip_when_index_missing(self):
        from app.retrieval.es_client import ensure_source_type_mapping

        mock_es = AsyncMock()
        mock_es.indices.exists.return_value = False
        with patch("app.retrieval.es_client._es_client", mock_es):
            ok = await ensure_source_type_mapping("public")
            assert ok is False
            mock_es.indices.put_mapping.assert_not_awaited()
