"""集成测试 — 文章批量生成 API 全链路

遵循: tests/integration/test_feedback_flow.py 模式
使用 SQLite 内存数据库 + httpx.AsyncClient + ASGITransport
通过 token_factory 创建带任意角色的用户（注册接口强制 readonly）
"""

import pytest


class TestArticlesAPICRUD:
    """CRUD 链路 + 权限验证"""

    @pytest.mark.asyncio
    async def test_create_and_get_batch(self, client, token_factory):
        """创建批次并查询详情"""
        token = await token_factory("art_crud", role="operator")
        h = {"Authorization": f"Bearer {token}"}

        resp = await client.post("/api/admin/articles/batches", json={
            "topic": "地下室防水施工要点",
            "article_count": 3,
        }, headers=h)
        assert resp.status_code == 201
        data = resp.json()
        assert data["topic"] == "地下室防水施工要点"
        assert data["article_count"] == 3
        assert data["status"] == "draft"
        batch_id = data["id"]

        resp = await client.get(f"/api/admin/articles/batches/{batch_id}", headers=h)
        assert resp.status_code == 200
        detail = resp.json()
        assert detail["id"] == batch_id
        assert detail["topic"] == "地下室防水施工要点"

    @pytest.mark.asyncio
    async def test_list_batches_paginated(self, client, token_factory):
        """批次列表支持分页"""
        token = await token_factory("art_list", role="operator")
        h = {"Authorization": f"Bearer {token}"}

        await client.post("/api/admin/articles/batches", json={"topic": "批1"}, headers=h)
        await client.post("/api/admin/articles/batches", json={"topic": "批2"}, headers=h)

        resp = await client.get("/api/admin/articles/batches?page=1&page_size=10", headers=h)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 2
        assert len(data["items"]) >= 2

    @pytest.mark.asyncio
    async def test_delete_batch(self, client, token_factory):
        """删除批次成功"""
        token = await token_factory("art_del", role="operator")
        h = {"Authorization": f"Bearer {token}"}

        resp = await client.post("/api/admin/articles/batches", json={"topic": "待删除"}, headers=h)
        bid = resp.json()["id"]

        resp = await client.delete(f"/api/admin/articles/batches/{bid}", headers=h)
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        resp = await client.get(f"/api/admin/articles/batches/{bid}", headers=h)
        assert resp.status_code == 404

    # ── Permission ──

    @pytest.mark.asyncio
    async def test_readonly_cannot_create_batch(self, client, token_factory):
        """只读用户无法创建批次"""
        token = await token_factory("art_ro", role="readonly")
        h = {"Authorization": f"Bearer {token}"}

        resp = await client.post("/api/admin/articles/batches", json={
            "topic": "测试", "article_count": 1,
        }, headers=h)
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_readonly_can_read_batches(self, client, token_factory):
        """只读用户可以查看批次"""
        # 先由 operator 创建
        op_token = await token_factory("art_op2", role="operator")
        resp = await client.post("/api/admin/articles/batches", json={
            "topic": "公开批次",
        }, headers={"Authorization": f"Bearer {op_token}"})
        assert resp.status_code == 201
        bid = resp.json()["id"]

        # 只读用户读取
        ro_token = await token_factory("art_ro2", role="readonly")
        resp = await client.get(f"/api/admin/articles/batches/{bid}",
                                headers={"Authorization": f"Bearer {ro_token}"})
        assert resp.status_code == 200

    # ── Photo Upload ──

    @pytest.mark.asyncio
    async def test_upload_photo_validation(self, client, token_factory):
        """照片上传格式校验"""
        token = await token_factory("art_up", role="operator")
        h = {"Authorization": f"Bearer {token}"}

        resp = await client.post("/api/admin/articles/batches", json={"topic": "图片测试"}, headers=h)
        bid = resp.json()["id"]

        # 模拟上传非图片文件
        from io import BytesIO
        fake_file = BytesIO(b"not an image")
        resp = await client.post(
            f"/api/admin/articles/batches/{bid}/upload-photos",
            files=[("files", ("test.txt", fake_file, "text/plain"))],
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400

    # ── Export ──

    @pytest.mark.asyncio
    async def test_export_article_not_found(self, client, token_factory):
        """导出不存在的文章返回 404"""
        token = await token_factory("art_ex", role="operator")
        h = {"Authorization": f"Bearer {token}"}
        resp = await client.get("/api/admin/articles/articles/99999/export?format=md", headers=h)
        assert resp.status_code == 404

    # ── Platforms ──

    @pytest.mark.asyncio
    async def test_list_platforms(self, client, token_factory):
        """获取平台列表"""
        token = await token_factory("art_pl", role="readonly")
        resp = await client.get("/api/admin/articles/platforms",
                                headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        platforms = resp.json()
        assert len(platforms) == 9
        wechat = next((p for p in platforms if p["platform"] == "wechat_mp"), None)
        assert wechat is not None
        assert wechat["method"] == "direct_api"

    # ── Generation (status code test only) ──

    @pytest.mark.asyncio
    async def test_generate_nonexistent_batch(self, client, token_factory):
        """不存在的批次生成返回 404"""
        token = await token_factory("art_gen", role="operator")
        h = {"Authorization": f"Bearer {token}"}
        resp = await client.post("/api/admin/articles/batches/99999/generate", headers=h)
        assert resp.status_code == 404


class TestStreamProgress:
    """SSE 进度流：静默期心跳 + 终态收尾"""

    @pytest.mark.asyncio
    async def test_stream_completed_terminates(self, client, token_factory, db_session):
        """批次已完成时，流应立即推送 completed 并结束"""
        from app.articles.models import ArticleBatch
        from app.articles.service import ArticleService
        from app.api.articles import _stream_events

        token = await token_factory("art_sse1", role="operator")
        h = {"Authorization": f"Bearer {token}"}
        resp = await client.post("/api/admin/articles/batches", json={
            "topic": "SSE终态", "article_count": 2,
        }, headers=h)
        bid = resp.json()["id"]

        batch = await db_session.get(ArticleBatch, bid)
        batch.status = "completed"
        await db_session.commit()

        svc = ArticleService(db_session)
        events = [ev async for ev in _stream_events(bid, db_session, svc)]
        text = "".join(events)
        assert '"type": "completed"' in text

    @pytest.mark.asyncio
    async def test_stream_emits_heartbeat_during_silence(
        self, client, token_factory, db_session, monkeypatch
    ):
        """长静默生成期（状态/数量不变）应持续推送心跳，避免被代理空闲超时掐断"""
        from app.articles.models import ArticleBatch
        from app.articles.service import ArticleService
        from app.api.articles import _stream_events

        async def no_sleep(_sec):
            return None

        monkeypatch.setattr("app.api.articles.asyncio.sleep", no_sleep)

        token = await token_factory("art_sse2", role="operator")
        h = {"Authorization": f"Bearer {token}"}
        resp = await client.post("/api/admin/articles/batches", json={
            "topic": "SSE心跳", "article_count": 2,
        }, headers=h)
        bid = resp.json()["id"]

        batch = await db_session.get(ArticleBatch, bid)
        batch.status = "generating"
        await db_session.commit()

        svc = ArticleService(db_session)
        gen = _stream_events(bid, db_session, svc, heartbeat_interval=1)

        # 静默期（保持 generating）：推进多轮，期间应出现心跳帧
        collected: list[str] = []
        for _ in range(5):
            try:
                collected.append(await anext(gen))
            except StopAsyncIteration:
                break
        heartbeats = [e for e in collected if '"type": "progress"' in e and "生成中" in e]
        assert heartbeats, "静默期应推送心跳帧"

        # 完成生成 → 流应推送 completed 并结束
        batch.status = "completed"
        await db_session.commit()
        while True:
            try:
                ev = await anext(gen)
                collected.append(ev)
                if '"type": "completed"' in ev:
                    break
            except StopAsyncIteration:
                break
        assert any('"type": "completed"' in e for e in collected)

    @pytest.mark.asyncio
    async def test_stream_error_when_batch_missing(self, db_session):
        """批次不存在时推送 error 并结束"""
        from app.articles.service import ArticleService
        from app.api.articles import _stream_events

        svc = ArticleService(db_session)
        gen = _stream_events(99999, db_session, svc)
        ev = await anext(gen)
        assert '"type": "error"' in ev
        with pytest.raises(StopAsyncIteration):
            await anext(gen)


class TestAccountTypeFlow:
    """目标账号类型（用户/设计师/经销商）透传"""

    @pytest.mark.asyncio
    async def test_create_batch_with_account_type(self, client, token_factory):
        token = await token_factory("art_at", role="operator")
        h = {"Authorization": f"Bearer {token}"}
        resp = await client.post("/api/admin/articles/batches", json={
            "topic": "经销商招商政策",
            "article_count": 3,
            "account_type": "dealer",
        }, headers=h)
        assert resp.status_code == 201
        data = resp.json()
        assert data["account_type"] == "dealer"

    @pytest.mark.asyncio
    async def test_create_batch_without_account_type_is_null(self, client, token_factory):
        token = await token_factory("art_at2", role="operator")
        h = {"Authorization": f"Bearer {token}"}
        resp = await client.post("/api/admin/articles/batches", json={
            "topic": "通用主题",
        }, headers=h)
        assert resp.status_code == 201
        assert resp.json()["account_type"] is None

    @pytest.mark.asyncio
    async def test_topics_generate_passes_company_direction(self, client, token_factory):
        from unittest.mock import patch

        token = await token_factory("art_tg", role="operator")
        h = {"Authorization": f"Bearer {token}"}
        captured: dict = {}

        async def fake_recommend(db, max_topics=8, company_direction=""):
            captured["company_direction"] = company_direction
            return {
                "recommendations": [{
                    "hot_title": "热点A",
                    "source": "baidu",
                    "reason": "契合方向",
                    "suggested_topic": "招商加盟机会解读",
                    "titles": ["标题1"],
                }],
                "hot_count": 1,
                "message": "",
            }

        with patch("app.articles.hot_topics.recommend_titles", new=fake_recommend):
            resp = await client.post("/api/admin/articles/topics/generate", json={
                "company_direction": "招商加盟",
            }, headers=h)
        assert resp.status_code == 200
        data = resp.json()
        assert captured["company_direction"] == "招商加盟"
        assert data["recommendations"][0]["suggested_topic"] == "招商加盟机会解读"

    @pytest.mark.asyncio
    async def test_photos_match_weighted_endpoint(self, client, token_factory):
        from unittest.mock import AsyncMock, patch

        token = await token_factory("art_wm", role="operator")
        h = {"Authorization": f"Bearer {token}"}

        fake_match = AsyncMock(return_value=[{
            "photo_id": 1,
            "object_name": "photo-library/1/x.jpg",
            "filename": "x.jpg",
            "tags": ["地下室"],
            "description": "场景",
            "confidence": 0.9,
            "reason": "契合",
            "weights": {"tag_keyword": 0.8, "semantic": 0.9, "freshness": 1.0, "anti_reuse": 1.0},
        }])

        with patch(
            "app.articles.photo_service.PhotoService.match_photos_weighted",
            new=fake_match,
        ):
            resp = await client.post("/api/admin/articles/photos/match-weighted", json={
                "topic": "地下室电渗透",
                "template_instruction": "按招商政策结构组织",
                "count": 3,
            }, headers=h)
        assert resp.status_code == 200
        data = resp.json()
        assert data["matches"][0]["photo_id"] == 1
        assert "weights" in data["matches"][0]

    @pytest.mark.asyncio
    async def test_templates_filter_by_account_type(self, client, token_factory):
        token = await token_factory("art_tmpl", role="operator")
        h = {"Authorization": f"Bearer {token}"}
        resp = await client.get("/api/admin/articles/templates?account_type=dealer", headers=h)
        assert resp.status_code == 200
        templates = resp.json()
        names = {t["name"] for t in templates}
        assert "招商政策解读型（经销商）" in names
        assert "营销转化（经销商）" in names
