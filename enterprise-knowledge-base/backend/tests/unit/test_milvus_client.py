"""Milvus Dense 检索 测试 — MilvusClient API + source_type 条件透传（兼容 2.4 服务端）"""

import pytest
from unittest.mock import MagicMock, patch

from app.retrieval.milvus_client import (
    MilvusConfig,
    create_milvus_config,
    get_collection_name,
    insert_vectors,
    dense_search,
    _collection_fields,
    _has_source_type,
    _collection_fields_cache,
)


class TestMilvusConfig:
    def test_create_from_settings(self):
        cfg = create_milvus_config()
        assert cfg.host == "milvus"
        assert cfg.port == 19530
        assert cfg.dimension == 1024

    def test_custom_config(self):
        cfg = MilvusConfig(host="test-milvus", port=19531, dimension=768)
        assert cfg.host == "test-milvus"
        assert cfg.dimension == 768


class TestCollectionName:
    def test_public_scope(self):
        assert get_collection_name("public") == "coll_public"

    def test_internal_scope(self):
        assert get_collection_name("internal") == "coll_internal"

    def test_customer_scope(self):
        assert get_collection_name("customer") == "coll_customer"

    def test_default_scope(self):
        assert get_collection_name(None) == "coll_public"


class TestInsertVectors:
    @pytest.mark.asyncio
    async def test_insert_writes_source_type_when_field_present(self):
        from langchain_core.documents import Document

        docs = [
            Document(
                page_content="向量测试一",
                metadata={"doc_id": 1, "chunk_index": 0, "scope": "public", "title": "测试", "source_type": "wechat"},
            ),
        ]
        mock_client = MagicMock()
        mock_client.insert.return_value = {"insert_count": 1}

        with patch("app.retrieval.milvus_client._ensure_collection", return_value="coll_public"), \
             patch("app.retrieval.milvus_client._get_client", return_value=mock_client), \
             patch("app.retrieval.milvus_client._has_source_type", return_value=True):
            count = await insert_vectors(docs, [[0.1] * 1024], scope="public")
            assert count == 1
            row = mock_client.insert.call_args.kwargs["data"][0]
            assert row["source_type"] == "wechat"

    @pytest.mark.asyncio
    async def test_insert_omits_source_type_when_field_absent(self):
        from langchain_core.documents import Document

        docs = [
            Document(
                page_content="旧集合",
                metadata={"doc_id": 2, "chunk_index": 0, "scope": "internal", "title": "t", "source_type": "wechat"},
            ),
        ]
        mock_client = MagicMock()
        mock_client.insert.return_value = {"insert_count": 1}

        with patch("app.retrieval.milvus_client._ensure_collection", return_value="coll_internal"), \
             patch("app.retrieval.milvus_client._get_client", return_value=mock_client), \
             patch("app.retrieval.milvus_client._has_source_type", return_value=False):
            await insert_vectors(docs, [[0.1] * 1024], scope="internal")
            row = mock_client.insert.call_args.kwargs["data"][0]
            assert "source_type" not in row

    @pytest.mark.asyncio
    async def test_insert_defaults_source_type_internal(self):
        from langchain_core.documents import Document

        docs = [
            Document(page_content="无来源", metadata={"doc_id": 3, "chunk_index": 0, "scope": "public", "title": "t"}),
        ]
        mock_client = MagicMock()
        mock_client.insert.return_value = {"insert_count": 1}

        with patch("app.retrieval.milvus_client._ensure_collection", return_value="coll_public"), \
             patch("app.retrieval.milvus_client._get_client", return_value=mock_client), \
             patch("app.retrieval.milvus_client._has_source_type", return_value=True):
            await insert_vectors(docs, [[0.1] * 1024], scope="public")
            row = mock_client.insert.call_args.kwargs["data"][0]
            assert row["source_type"] == "internal"


class TestDenseSearch:
    @pytest.mark.asyncio
    async def test_search_requests_source_type_when_present(self):
        mock_client = MagicMock()
        mock_client.search.return_value = [
            [
                {
                    "id": "1_0",
                    "distance": 0.95,
                    "entity": {
                        "content": "检索内容",
                        "doc_id": 1,
                        "chunk_index": 0,
                        "scope": "public",
                        "title": "文档标题",
                        "source_type": "official_website",
                    },
                },
            ]
        ]

        with patch("app.retrieval.milvus_client._ensure_collection", return_value="coll_public"), \
             patch("app.retrieval.milvus_client._get_client", return_value=mock_client), \
             patch("app.retrieval.milvus_client._has_source_type", return_value=True):
            results = await dense_search([0.1] * 1024, scope="public", top_k=5)
            assert len(results) == 1
            assert results[0].doc_id == 1
            assert results[0].content == "检索内容"
            assert results[0].metadata["source_type"] == "official_website"
            assert "source_type" in mock_client.search.call_args.kwargs["output_fields"]

    @pytest.mark.asyncio
    async def test_search_omits_field_but_defaults_metadata_when_absent(self):
        mock_client = MagicMock()
        mock_client.search.return_value = [
            [
                {"id": "1_0", "distance": 0.9, "entity": {"content": "x", "doc_id": 1, "chunk_index": 0, "scope": "internal", "title": "t"}},
            ]
        ]
        with patch("app.retrieval.milvus_client._ensure_collection", return_value="coll_internal"), \
             patch("app.retrieval.milvus_client._get_client", return_value=mock_client), \
             patch("app.retrieval.milvus_client._has_source_type", return_value=False):
            results = await dense_search([0.1] * 1024, scope="internal", top_k=5)
            assert "source_type" not in mock_client.search.call_args.kwargs["output_fields"]
            assert results[0].metadata["source_type"] == "internal"

    @pytest.mark.asyncio
    async def test_search_empty_result(self):
        mock_client = MagicMock()
        mock_client.search.return_value = [[]]

        with patch("app.retrieval.milvus_client._ensure_collection", return_value="coll_public"), \
             patch("app.retrieval.milvus_client._get_client", return_value=mock_client), \
             patch("app.retrieval.milvus_client._has_source_type", return_value=True):
            results = await dense_search([0.1] * 1024, scope="public", top_k=5)
            assert results == []


class TestCollectionFields:
    def setup_method(self):
        _collection_fields_cache.clear()

    def teardown_method(self):
        _collection_fields_cache.clear()

    def test_collection_fields_caches_describe(self):
        mock_client = MagicMock()
        mock_client.describe_collection.return_value = {"fields": [{"name": "id"}, {"name": "source_type"}]}
        first = _collection_fields(mock_client, "coll_a")
        second = _collection_fields(mock_client, "coll_a")
        assert first == {"id", "source_type"}
        assert second == {"id", "source_type"}
        mock_client.describe_collection.assert_called_once()

    def test_has_source_type_true(self):
        mock_client = MagicMock()
        mock_client.describe_collection.return_value = {"fields": [{"name": "source_type"}]}
        assert _has_source_type(mock_client, "coll_b") is True

    def test_has_source_type_false(self):
        mock_client = MagicMock()
        mock_client.describe_collection.return_value = {"fields": [{"name": "id"}]}
        assert _has_source_type(mock_client, "coll_c") is False

    def test_describe_failure_yields_empty(self):
        mock_client = MagicMock()
        mock_client.describe_collection.side_effect = RuntimeError("boom")
        assert _collection_fields(mock_client, "coll_d") == set()
        assert _has_source_type(mock_client, "coll_d") is False
