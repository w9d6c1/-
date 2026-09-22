"""分类管理 — 树形结构 / 强制 scope / 禁用检索隔离 测试

覆盖验证标准:
1. 树形结构正常渲染 (GET /categories/tree 返回嵌套 children)
2. 分类强制绑定 scope，不可为空 (缺失/非法 scope -> 422)
3. 禁用分类下的知识不可被检索 (sync_document 对禁用分类文档跳过索引)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

from app.models.category import KnowledgeCategory
from app.models.document import DocChunk, KnowledgeDoc


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class TestCategoryScopeMandatory:
    @pytest.mark.asyncio
    async def test_create_without_scope_rejected(self, client: AsyncClient, token_factory):
        """scope 不可为空 — 缺失 scope 返回 422"""
        token = await token_factory("cat_scope1")
        resp = await client.post(
            "/api/admin/categories", json={"name": "no-scope"}, headers=_auth(token)
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_with_invalid_scope_rejected(self, client: AsyncClient, token_factory):
        """非法 scope 返回 422"""
        token = await token_factory("cat_scope2")
        resp = await client.post(
            "/api/admin/categories",
            json={"name": "bad-scope", "scope": "secret"},
            headers=_auth(token),
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_with_valid_scope_ok(self, client: AsyncClient, token_factory):
        """合法 scope 创建成功并回显"""
        token = await token_factory("cat_scope3")
        resp = await client.post(
            "/api/admin/categories",
            json={"name": "internal-cat", "scope": "internal"},
            headers=_auth(token),
        )
        assert resp.status_code == 201
        assert resp.json()["scope"] == "internal"


class TestCategoryTree:
    @pytest.mark.asyncio
    async def test_tree_returns_nested_children(self, client: AsyncClient, token_factory):
        """树形结构正常渲染 — 父分类的 children 含子分类"""
        token = await token_factory("cat_tree1")
        root = await client.post(
            "/api/admin/categories",
            json={"name": "root", "scope": "public"},
            headers=_auth(token),
        )
        root_id = root.json()["id"]
        child = await client.post(
            "/api/admin/categories",
            json={"name": "child", "scope": "public", "parent_id": root_id},
            headers=_auth(token),
        )
        child_id = child.json()["id"]

        resp = await client.get("/api/admin/categories/tree", headers=_auth(token))
        assert resp.status_code == 200
        tree = resp.json()
        root_node = next((n for n in tree if n["id"] == root_id), None)
        assert root_node is not None
        assert "children" in root_node
        assert any(c["id"] == child_id for c in root_node["children"])


class TestCategoryUpdate:
    @pytest.mark.asyncio
    async def test_disable_category(self, client: AsyncClient, token_factory):
        """禁用某分类 — status 变为 disabled"""
        token = await token_factory("cat_upd1")
        created = await client.post(
            "/api/admin/categories",
            json={"name": "to-disable", "scope": "public"},
            headers=_auth(token),
        )
        cid = created.json()["id"]
        resp = await client.put(
            f"/api/admin/categories/{cid}",
            json={"status": "disabled"},
            headers=_auth(token),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "disabled"

    @pytest.mark.asyncio
    async def test_update_scope(self, client: AsyncClient, token_factory):
        """编辑分类可修改 scope"""
        token = await token_factory("cat_upd2")
        created = await client.post(
            "/api/admin/categories",
            json={"name": "change-scope", "scope": "public"},
            headers=_auth(token),
        )
        cid = created.json()["id"]
        resp = await client.put(
            f"/api/admin/categories/{cid}",
            json={"scope": "customer"},
            headers=_auth(token),
        )
        assert resp.status_code == 200
        assert resp.json()["scope"] == "customer"

    @pytest.mark.asyncio
    async def test_update_scope_to_invalid_rejected(self, client: AsyncClient, token_factory):
        """scope 不可改为非法值"""
        token = await token_factory("cat_upd3")
        created = await client.post(
            "/api/admin/categories",
            json={"name": "bad-change-scope", "scope": "public"},
            headers=_auth(token),
        )
        cid = created.json()["id"]
        resp = await client.put(
            f"/api/admin/categories/{cid}",
            json={"scope": ""},
            headers=_auth(token),
        )
        assert resp.status_code == 422


class TestDisabledCategoryRetrievalGate:
    @pytest.mark.asyncio
    async def test_sync_skips_disabled_category(self, db_session):
        """禁用分类下的知识不可被检索 — sync_document 跳过禁用分类文档"""
        from app.retrieval.sync import sync_document

        cat = KnowledgeCategory(name="disabled-cat", scope="public", status="disabled")
        db_session.add(cat)
        await db_session.flush()

        doc = KnowledgeDoc(
            category_id=cat.id, title="disabled-doc", scope="public",
            plain_text="content content", chunk_count=1, status="online",
        )
        db_session.add(doc)
        await db_session.flush()
        db_session.add(DocChunk(doc_id=doc.id, chunk_index=0, content="content content", scope="public"))
        await db_session.commit()

        mock_es = AsyncMock()
        with patch("app.retrieval.es_client._es_client", mock_es):
            with patch("app.retrieval.sync.index_documents", new=AsyncMock(return_value=1)) as m_idx:
                count = await sync_document(db_session, doc_id=doc.id)
                assert count == 0
                m_idx.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_indexes_enabled_category(self, db_session):
        """启用分类下的文档正常索引"""
        from app.retrieval.sync import sync_document

        cat = KnowledgeCategory(name="enabled-cat", scope="public", status="enabled")
        db_session.add(cat)
        await db_session.flush()

        doc = KnowledgeDoc(
            category_id=cat.id, title="enabled-doc", scope="public",
            plain_text="content content", chunk_count=1, status="online",
            review_status="approved",
        )
        db_session.add(doc)
        await db_session.flush()
        db_session.add(DocChunk(doc_id=doc.id, chunk_index=0, content="content content", scope="public"))
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
            count = await sync_document(db_session, doc_id=doc.id)
            assert count >= 1


class TestCategorySubtreeDeindex:
    @pytest.mark.asyncio
    async def test_deindex_category_collects_subtree(self, db_session):
        """禁用父分类时，子孙分类下的文档一并下线索引"""
        from app.retrieval.sync import deindex_category

        root = KnowledgeCategory(name="root", scope="public", status="enabled")
        db_session.add(root)
        await db_session.flush()
        child = KnowledgeCategory(name="child", scope="public", status="enabled", parent_id=root.id)
        db_session.add(child)
        await db_session.flush()
        grand = KnowledgeCategory(name="grand", scope="public", status="enabled", parent_id=child.id)
        db_session.add(grand)
        await db_session.flush()

        for cat in (child, grand):
            db_session.add(KnowledgeDoc(
                category_id=cat.id, title=f"doc-{cat.id}", scope="public",
                plain_text="x", chunk_count=0, status="online",
            ))
        await db_session.commit()

        with patch("app.retrieval.sync.deindex_document", new=AsyncMock(return_value=1)) as m_deidx:
            count = await deindex_category(db_session, root.id)
            assert count == 2
            assert m_deidx.await_count == 2
