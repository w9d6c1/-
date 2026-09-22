"""向量同步服务 测试 (TDD: RED)"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.document import KnowledgeDoc, DocChunk


class TestSyncDocument:
    @pytest.mark.asyncio
    async def test_sync_single_doc_writes_both_stores(self, db_session):
        from app.retrieval.sync import sync_document

        doc = KnowledgeDoc(
            id=200, category_id=1, title="同步测试文档",
            scope="public", plain_text="同步测试内容同步测试内容",
            word_count=20, chunk_count=1, chunk_strategy="fixed",
            status="online", review_status="approved",
        )
        db_session.add(doc)
        await db_session.flush()

        ch = DocChunk(doc_id=doc.id, chunk_index=0, content="同步测试内容", scope="public")
        db_session.add(ch)
        await db_session.commit()

        mock_es = AsyncMock()
        mock_es.bulk.return_value = {"errors": False, "items": [{"index": {"result": "created"}}]}

        mock_col = MagicMock()
        mock_col.insert.return_value = {"insert_count": 1}

        with patch("app.retrieval.es_client._es_client", mock_es), \
             patch("app.retrieval.milvus_client._ensure_collection", return_value="coll_public"), \
             patch("app.retrieval.milvus_client._get_client", return_value=mock_col), \
             patch("app.retrieval.sync.embed_texts", return_value=[[0.1] * 1024]), \
             patch("app.retrieval.sync.create_bm25_index", new=AsyncMock()):
            count = await sync_document(db_session, doc_id=200)
            assert count >= 1

    @pytest.mark.asyncio
    async def test_sync_nonexistent_doc(self, db_session):
        from app.retrieval.sync import sync_document

        count = await sync_document(db_session, doc_id=99999)
        assert count == 0

    @pytest.mark.asyncio
    async def test_sync_updates_timestamps(self, db_session):
        from app.retrieval.sync import sync_document

        doc = KnowledgeDoc(
            id=201, category_id=1, title="时间戳测试",
            scope="public", plain_text="内容", chunk_count=1,
            status="online", review_status="approved",
        )
        db_session.add(doc)
        await db_session.flush()
        ch = DocChunk(doc_id=doc.id, chunk_index=0, content="内容", scope="public")
        db_session.add(ch)
        await db_session.commit()

        mock_es = AsyncMock()
        mock_es.bulk.return_value = {"errors": False, "items": [{"index": {"result": "created"}}]}
        mock_col = MagicMock()
        mock_col.insert.return_value = {"insert_count": 1}

        with patch("app.retrieval.es_client._es_client", mock_es), \
             patch("app.retrieval.milvus_client._ensure_collection", return_value="coll_public"), \
             patch("app.retrieval.milvus_client._get_client", return_value=mock_col), \
             patch("app.retrieval.sync.embed_texts", return_value=[[0.1] * 1024]), \
             patch("app.retrieval.sync.create_bm25_index", new=AsyncMock()):
            await sync_document(db_session, doc_id=201)
            await db_session.refresh(ch)
            assert ch.vector_id is not None
            assert ch.bm25_id is not None
            assert ch.last_sync_at is not None


class TestDeindexDocument:
    @pytest.mark.asyncio
    async def test_deindex_removes_from_both(self):
        from app.retrieval.sync import deindex_document

        with patch("app.retrieval.sync.es_delete_all", new=AsyncMock(return_value=3)):
            with patch("app.retrieval.sync.mv_delete_all", new=AsyncMock(return_value=3)):
                result = await deindex_document(doc_id=200)
                assert result == 6


class TestSyncSourceType:
    @pytest.mark.asyncio
    async def test_sync_writes_source_type_to_both_stores(self, db_session):
        from app.retrieval.sync import sync_document

        doc = KnowledgeDoc(
            id=202, category_id=1, title="公众号同步",
            scope="public", plain_text="内容", chunk_count=1,
            status="online", review_status="approved",
            source_type="wechat", source_name="公司官方公众号",
        )
        db_session.add(doc)
        await db_session.flush()
        db_session.add(DocChunk(doc_id=doc.id, chunk_index=0, content="内容", scope="public"))
        await db_session.commit()

        mock_es = AsyncMock()
        mock_es.bulk.return_value = {"errors": False, "items": [{"index": {"result": "created"}}]}
        mock_col = MagicMock()
        mock_col.insert.return_value = {"insert_count": 1}

        with patch("app.retrieval.es_client._es_client", mock_es), \
             patch("app.retrieval.milvus_client._ensure_collection", return_value="coll_public"), \
             patch("app.retrieval.milvus_client._get_client", return_value=mock_col), \
             patch("app.retrieval.milvus_client._has_source_type", return_value=True), \
             patch("app.retrieval.sync.embed_texts", return_value=[[0.1] * 1024]), \
             patch("app.retrieval.sync.create_bm25_index", new=AsyncMock()):
            await sync_document(db_session, doc_id=202)

        es_ops = mock_es.bulk.call_args.kwargs["operations"]
        es_body = [op for op in es_ops if "content" in op][0]
        assert es_body["source_type"] == "wechat"

        mv_row = mock_col.insert.call_args.kwargs["data"][0]
        assert mv_row["source_type"] == "wechat"
