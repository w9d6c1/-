"""文档加载器 测试 (TDD: RED)"""

import pytest

from app.knowledge.loader import (
    DocumentMeta,
    load_text,
    load_doc_chunks,
    load_by_scope,
)


class TestDocumentMeta:
    def test_document_meta_defaults(self):
        meta = DocumentMeta(source="test.md")
        assert meta.source == "test.md"
        assert meta.scope == "public"
        assert meta.doc_id == 0
        assert meta.chunk_index == 0

    def test_document_meta_full(self):
        meta = DocumentMeta(
            source="doc.pdf",
            scope="internal",
            doc_id=42,
            chunk_index=3,
            title="员工手册",
            department="技术部",
        )
        assert meta.source == "doc.pdf"
        assert meta.scope == "internal"
        assert meta.doc_id == 42
        assert meta.chunk_index == 3
        assert meta.title == "员工手册"
        assert meta.department == "技术部"

    def test_document_meta_to_lc_metadata(self):
        meta = DocumentMeta(source="test.txt", scope="public", doc_id=1, chunk_index=0)
        lc_meta = meta.to_langchain_meta()
        assert lc_meta["source"] == "test.txt"
        assert lc_meta["scope"] == "public"
        assert lc_meta["doc_id"] == 1
        assert lc_meta["chunk_index"] == 0


class TestLoadText:
    def test_load_text_produces_documents(self):
        content = "第一章\n\n这是第一章的内容。" * 30
        meta = DocumentMeta(source="test.md", scope="public", title="测试文档")
        docs = load_text(content, meta, chunk_size=300, chunk_overlap=50)
        assert len(docs) > 0
        for doc in docs:
            assert hasattr(doc, "page_content")
            assert hasattr(doc, "metadata")
            assert doc.metadata["source"] == "test.md"
            assert doc.metadata["scope"] == "public"
            assert doc.metadata["title"] == "测试文档"

    def test_load_text_short_content(self):
        content = "短文本"
        meta = DocumentMeta(source="short.txt")
        docs = load_text(content, meta)
        assert len(docs) == 1
        assert docs[0].page_content == "短文本"

    def test_load_text_empty_content(self):
        meta = DocumentMeta(source="empty.txt")
        docs = load_text("", meta)
        assert len(docs) == 0


class TestLoadDocChunks:
    @pytest.mark.asyncio
    async def test_load_doc_chunks_yields_documents(self, db_session):
        """从 DocChunk 表加载并转换为 LangChain Document"""
        from app.models.document import KnowledgeDoc, DocChunk

        doc = KnowledgeDoc(
            id=100,
            category_id=1,
            title="测试文档",
            scope="internal",
            plain_text="测试内容测试内容",
            word_count=10,
            chunk_count=2,
            chunk_strategy="fixed",
            chunk_size=200,
            department="技术部",
        )
        db_session.add(doc)
        await db_session.flush()

        ch1 = DocChunk(doc_id=doc.id, chunk_index=0, content="第一块内容", scope="internal")
        ch2 = DocChunk(doc_id=doc.id, chunk_index=1, content="第二块内容", scope="internal")
        db_session.add_all([ch1, ch2])
        await db_session.commit()

        docs = await load_doc_chunks(db_session, doc_id=100)
        assert len(docs) == 2
        assert docs[0].metadata["doc_id"] == 100
        assert docs[0].metadata["chunk_index"] == 0
        assert docs[1].metadata["chunk_index"] == 1
        assert docs[0].metadata["title"] == "测试文档"
        assert docs[0].metadata["department"] == "技术部"
        assert docs[0].metadata["scope"] == "internal"

    @pytest.mark.asyncio
    async def test_load_doc_chunks_empty(self, db_session):
        docs = await load_doc_chunks(db_session, doc_id=999)
        assert len(docs) == 0


class TestLoadByScope:
    @pytest.mark.asyncio
    async def test_load_by_scope_filters_correctly(self, db_session):
        from app.models.document import KnowledgeDoc, DocChunk

        # internal doc
        doc1 = KnowledgeDoc(id=101, category_id=1, title="内部文档", scope="internal", plain_text="内部", status="online")
        doc1.chunk_count = 1
        db_session.add(doc1)
        await db_session.flush()
        ch1 = DocChunk(doc_id=doc1.id, chunk_index=0, content="内部内容", scope="internal")
        db_session.add(ch1)

        # public doc
        doc2 = KnowledgeDoc(id=102, category_id=1, title="公开文档", scope="public", plain_text="公开", status="online")
        doc2.chunk_count = 1
        db_session.add(doc2)
        await db_session.flush()
        ch2 = DocChunk(doc_id=doc2.id, chunk_index=0, content="公开内容", scope="public")
        db_session.add(ch2)
        await db_session.commit()

        internal_docs = await load_by_scope(db_session, scope="internal")
        assert len(internal_docs) == 1
        assert internal_docs[0].metadata["scope"] == "internal"

        public_docs = await load_by_scope(db_session, scope="public")
        assert len(public_docs) == 1
        assert public_docs[0].metadata["scope"] == "public"

        all_docs = await load_by_scope(db_session, scope=None)
        assert len(all_docs) == 2


class TestSourceTypePassthrough:
    def test_document_meta_source_defaults(self):
        meta = DocumentMeta(source="t.md")
        assert meta.source_type == "internal"
        assert meta.source_name is None
        assert meta.original_url is None
        assert meta.publish_time is None

    def test_to_lc_metadata_carries_source_fields(self):
        from datetime import datetime

        pt = datetime(2026, 7, 31, 9, 0, 0)
        meta = DocumentMeta(
            source="t.md",
            source_type="wechat",
            source_name="公司官方公众号",
            original_url="https://mp.weixin.qq.com/s/xxx",
            publish_time=pt,
        )
        lc = meta.to_langchain_meta()
        assert lc["source_type"] == "wechat"
        assert lc["source_name"] == "公司官方公众号"
        assert lc["original_url"] == "https://mp.weixin.qq.com/s/xxx"
        assert lc["publish_time"] == pt.isoformat()

    def test_to_lc_metadata_source_defaults_internal(self):
        lc = DocumentMeta(source="t.md").to_langchain_meta()
        assert lc["source_type"] == "internal"
        assert lc["source_name"] == ""
        assert lc["original_url"] == ""
        assert lc["publish_time"] == ""

    @pytest.mark.asyncio
    async def test_load_doc_chunks_carries_source_type(self, db_session):
        from datetime import datetime

        from app.models.document import KnowledgeDoc, DocChunk

        doc = KnowledgeDoc(
            id=110,
            category_id=1,
            title="公众号文章",
            scope="public",
            plain_text="内容",
            word_count=2,
            chunk_count=1,
            source_type="wechat",
            source_name="公司官方公众号",
            original_url="https://mp.weixin.qq.com/s/abc",
            publish_time=datetime(2026, 7, 1, 10, 0, 0),
        )
        db_session.add(doc)
        await db_session.flush()
        db_session.add(DocChunk(doc_id=doc.id, chunk_index=0, content="内容", scope="public"))
        await db_session.commit()

        docs = await load_doc_chunks(db_session, doc_id=110)
        assert len(docs) == 1
        assert docs[0].metadata["source_type"] == "wechat"
        assert docs[0].metadata["source_name"] == "公司官方公众号"
        assert docs[0].metadata["original_url"] == "https://mp.weixin.qq.com/s/abc"
        assert docs[0].metadata["publish_time"] == "2026-07-01T10:00:00"

    @pytest.mark.asyncio
    async def test_load_by_scope_carries_source_type(self, db_session):
        from app.models.document import KnowledgeDoc, DocChunk

        doc = KnowledgeDoc(
            id=111,
            category_id=1,
            title="官网公告",
            scope="public",
            plain_text="公告",
            status="online",
            source_type="official_website",
        )
        doc.chunk_count = 1
        db_session.add(doc)
        await db_session.flush()
        db_session.add(DocChunk(doc_id=doc.id, chunk_index=0, content="公告", scope="public"))
        await db_session.commit()

        docs = await load_by_scope(db_session, scope="public")
        assert len(docs) == 1
        assert docs[0].metadata["source_type"] == "official_website"
