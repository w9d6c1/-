"""公开图片端点测试 — 前缀/扩展名白名单与路径安全"""

import pytest


class TestPublicImageEndpoint:
    @pytest.mark.asyncio
    async def test_rejects_non_article_prefix(self, client):
        resp = await client.get("/api/public/images/other/x.jpg")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_rejects_disallowed_extension(self, client):
        resp = await client.get("/api/public/images/article-images/wechat/a/evil.txt")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_rejects_svg_extension(self, client):
        resp = await client.get("/api/public/images/article-images/wechat/a/x.svg")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_rejects_path_traversal(self, client):
        resp = await client.get("/api/public/images/article-images/wechat/a/..%2F..%2Fsecret.txt")
        assert resp.status_code in (400, 403, 404)

    @pytest.mark.asyncio
    async def test_missing_object_returns_404(self, client):
        # 合法路径但 MinIO 对象不存在（测试环境无 MinIO → 404）
        resp = await client.get("/api/public/images/article-images/wechat/a/notexist.jpg")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_article_photos_prefix_allowed(self, client):
        # article-photos/ 为发布配图前缀，应放行（对象缺失 → 404，而非 403 拦截）
        resp = await client.get(
            "/api/public/images/article-photos/12/notexist.jpg"
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_article_photos_rejects_disallowed_extension(self, client):
        resp = await client.get("/api/public/images/article-photos/12/evil.txt")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_article_photos_rejects_path_traversal(self, client):
        resp = await client.get(
            "/api/public/images/article-photos/12/..%2F..%2Fsecret.txt"
        )
        assert resp.status_code in (400, 403, 404)
