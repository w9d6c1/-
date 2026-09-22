"""单元测试 — 发布服务"""

from unittest.mock import AsyncMock, patch

import pytest

from app.articles.publisher import (
    _resolve_markers_to_photos,
    export_docx,
    export_html,
    export_markdown,
    list_platforms,
    prepare_publish_content,
    publish_via_bridge,
    publish_via_wechatsync,
)


class TestPlatformRegistry:
    def test_list_all_platforms(self):
        """验证平台注册表完整性

        wechat_mp 走 direct_api 独立分支（publish_to_wechat_mp），不在此注册表内。
        """
        platforms = list_platforms()
        ids = {p["platform"] for p in platforms}
        expected = {
            "toutiao", "baijia", "zhihu", "wangyi", "csdn", "jianshu",
            "weibo", "xiaohongshu", "yidianhao", "douyin_tuwen",
        }
        assert ids == expected
        assert all(p["method"] == "wechatsync" for p in platforms)
        assert all(p["available"] is True for p in platforms)


class TestExport:
    def test_export_markdown(self):
        """导出 Markdown 文件内容正确"""
        data = export_markdown("测试文章", "## 正文\n\n内容")
        text = data.decode("utf-8")
        assert text.startswith("# 测试文章")
        assert "正文" in text

    def test_export_html(self):
        """导出 HTML 包含完整文档结构"""
        data = export_html("测试文章", "## 正文\n\n段落内容")
        text = data.decode("utf-8")
        assert "<!DOCTYPE html>" in text
        assert "<title>测试文章</title>" in text
        assert "段落内容" in text

    def test_export_docx(self):
        """导出 DOCX 返回非空字节"""
        md = "## 引言\n\n这是一篇关于电渗透防潮技术的文章。\n\n## 技术原理\n\n电渗透技术利用电场作用..."
        data = export_docx("测试文章", md)
        assert len(data) > 0
        # DOCX 本质是 ZIP，前 2 字节应为 PK
        assert data[:2] == b"PK"


class TestImageMarkers:
    def test_export_markdown_numbered_marker(self):
        """新编号格式 [IMAGE: 照片N: 配图建议: xxx] 在 MD 导出中按编号映射到对应图片"""
        # placements 模拟 generator 按编号映射后的输出：照片2→b.jpg、照片1→a.jpg
        content = (
            "第一段。\n\n[IMAGE: 照片2: 配图建议: 电极安装细节]\n\n"
            "第二段。\n\n[IMAGE: 照片1: 配图建议: 主机全貌]"
        )
        placements = [
            {"object_name": "photo-library/2/b.jpg", "caption": "电极安装细节"},
            {"object_name": "photo-library/1/a.jpg", "caption": "主机全貌"},
        ]
        text = export_markdown("标题", content, placements).decode("utf-8")
        assert "photo-library/2/b.jpg" in text
        assert "photo-library/1/a.jpg" in text
        assert "[IMAGE:" not in text

    def test_export_markdown_old_format_backward_compat(self):
        """旧格式标记仍被识别（向后兼容）"""
        content = "[IMAGE: 配图建议: 施工现场]\n\n正文"
        placements = [{"object_name": "photo-library/9/x.jpg", "caption": "施工现场"}]
        text = export_markdown("标题", content, placements).decode("utf-8")
        assert "photo-library/9/x.jpg" in text

    def test_resolve_markers_positional_beats_duplicate_caption(self):
        """重复 caption 时按位置取图，避免全部错配第一张"""
        content = (
            "[IMAGE: 照片1: 配图建议: 重复说明]\n\n"
            "[IMAGE: 照片2: 配图建议: 重复说明]"
        )
        placements = [
            {"object_name": "a.jpg", "caption": "重复说明"},
            {"object_name": "b.jpg", "caption": "重复说明"},
        ]
        photos = _resolve_markers_to_photos(content, placements, download=False)
        assert photos[0]["object_name"] == "a.jpg"
        assert photos[1]["object_name"] == "b.jpg"


class TestPreparePublishContent:
    def test_resolves_numbered_markers_to_url_and_base64(self):
        """发布前解析：[IMAGE: 照片N...] → Markdown 公开 URL + HTML base64 内嵌"""
        content = (
            "第一段。\n\n[IMAGE: 照片1: 配图建议: 电极安装细节]\n\n第二段。"
        )
        placements = [
            {"object_name": "article-photos/12/a.jpg", "caption": "电极安装细节"},
        ]
        with patch("app.articles.publisher._download_photo", return_value=b"\xff\xd8fake"):
            result = prepare_publish_content("标题", content, placements)

        assert "[IMAGE:" not in result["markdown"]
        assert (
            "![电极安装细节](https://localhost/api/public/images/article-photos/12/a.jpg)"
            in result["markdown"]
        )
        assert "[IMAGE:" not in result["html"]
        assert "data:image/jpeg;base64," in result["html"]
        assert result["has_photos"] is True

    def test_no_placement_keeps_content(self):
        """无配图时正文原样返回，html 走普通 Markdown→HTML 转换"""
        result = prepare_publish_content("标题", "正文内容无照片", None)
        assert result["markdown"] == "正文内容无照片"
        assert "正文内容无照片" in result["html"]
        assert result["has_photos"] is False

    def test_missing_photo_falls_back_to_caption(self):
        """MinIO 下载失败时标记回退为说明文字而非保留裸标记"""
        content = "[IMAGE: 照片1: 配图建议: 施工细节]\n\n正文"
        placements = [{"object_name": "article-photos/1/b.png", "caption": "施工细节"}]
        with patch("app.articles.publisher._download_photo", return_value=None):
            result = prepare_publish_content("标题", content, placements)
        assert "[IMAGE:" not in result["markdown"]
        assert "施工细节" in result["markdown"]
        assert "data:" not in result["html"]


class TestBridge:
    @pytest.mark.asyncio
    async def test_bridge_sends_markdown_and_content(self):
        """桥接器请求同时携带 Markdown(URL) 与 HTML(base64)，兼容各平台扩展"""
        captured: dict = {}

        class FakeResp:
            status_code = 200

            def json(self):
                return {"success": True, "url": None}

        class FakeClient:
            def __init__(self, timeout=None):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def post(self, url, json=None):
                captured["url"] = url
                captured["json"] = json
                return FakeResp()

        with patch("app.articles.publisher.httpx.AsyncClient", FakeClient), patch(
            "app.articles.publisher._download_photo", return_value=b"img"
        ):
            result = await publish_via_bridge(
                "标题",
                "正文 [IMAGE: 照片1: 配图建议: 现场]",
                "zhihu",
                account_group="2113",
                token="tok",
                image_placement=[{"object_name": "article-photos/12/a.jpg", "caption": "现场"}],
            )

        assert result["success"] is True
        body = captured["json"]
        assert body["platform"] == "zhihu"
        assert body["group"] == "2113"
        assert "article-photos/12/a.jpg" in body["markdown"]
        assert "![现场]" in body["markdown"]
        assert "data:image/jpeg;base64,aW1n" in body["content"]


class TestWechatsync:
    @pytest.mark.asyncio
    async def test_cli_not_found(self):
        """wechatsync CLI 未安装时返回友好错误"""
        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
            result = await publish_via_wechatsync("测试标题", "正文", "zhihu")
            assert result["success"] is False
            assert "未安装" in result["error"]

    @pytest.mark.asyncio
    async def test_cli_success(self):
        """CLI 发布成功"""
        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate.return_value = (b"published ok", b"")

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_proc):
            result = await publish_via_wechatsync("标题", "正文", "toutiao")
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_cli_failure(self):
        """CLI 发布失败"""
        mock_proc = AsyncMock()
        mock_proc.returncode = 1
        mock_proc.communicate.return_value = (b"", b"auth error")

        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock, return_value=mock_proc):
            result = await publish_via_wechatsync("标题", "正文", "toutiao")
            assert result["success"] is False
            assert "auth error" in result["error"]
