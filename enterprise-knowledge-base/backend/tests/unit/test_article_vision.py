"""单元测试 — 视觉分析模块"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.articles.vision import (
    OpenAICompatibleVisionProvider,
    analyze_photos,
    get_vision_provider,
)


class TestVisionProvider:
    @pytest.mark.asyncio
    async def test_openai_compatible_analyze(self):
        """验证 OpenAI 兼容视觉 API 的请求格式"""
        provider = OpenAICompatibleVisionProvider(
            base_url="https://api.example.com/v1",
            api_key="test-key",
            model="test-vision",
        )

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "照片描述：施工现场"}}]
        }

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_resp):
            result = await provider.analyze("aW1hZ2VfZGF0YQ==", "描述这张照片")
            assert result == "照片描述：施工现场"

    def test_get_provider_returns_none_without_key(self):
        """API key 为空时工厂函数返回 None"""
        with patch("app.articles.vision.settings") as mock_settings:
            mock_settings.vision_model_api_key = ""
            provider = get_vision_provider()
            assert provider is None


class TestAnalyzePhotos:
    @pytest.mark.asyncio
    async def test_skip_when_no_api_key(self):
        """无 API key 时返回占位描述"""
        with patch("app.articles.vision.get_vision_provider", return_value=None):
            result = await analyze_photos(["photo1.jpg", "photo2.jpg"], "地下室防水")
            assert "地下室防水" in result
            assert "2 张" in result

    @pytest.mark.asyncio
    async def test_analyze_photos_success(self):
        """正常流程：下载 → base64 → 分析 → 汇总"""
        mock_provider = AsyncMock()
        mock_provider.analyze.return_value = "施工现场描述"

        mock_minio = MagicMock()
        mock_response = MagicMock()
        mock_response.read.return_value = b"fake_image_data"
        mock_minio.get_object.return_value = mock_response

        with patch("app.articles.vision.get_vision_provider", return_value=mock_provider):
            with patch("app.articles.vision.get_minio_client", return_value=mock_minio):
                result = await analyze_photos(["photo1.jpg"], "地下室防水")
                assert "photo1.jpg" in result
                assert "施工现场描述" in result
                assert mock_provider.analyze.called

    @pytest.mark.asyncio
    async def test_handles_photo_download_failure(self):
        """单张照片下载失败不影响其他"""
        mock_provider = AsyncMock()
        mock_provider.analyze.return_value = "描述"

        mock_minio = MagicMock()

        call_count = [0]

        def fake_get_object(bucket, name):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("MinIO connection error")
            resp = MagicMock()
            resp.read.return_value = b"data"
            return resp

        mock_minio.get_object.side_effect = fake_get_object

        with patch("app.articles.vision.get_vision_provider", return_value=mock_provider):
            with patch("app.articles.vision.get_minio_client", return_value=mock_minio):
                result = await analyze_photos(["bad.jpg", "good.jpg"], "测试")
                assert "bad.jpg" in result
                assert "图片分析失败" in result
                assert "good.jpg" in result

    @pytest.mark.asyncio
    async def test_analyze_photos_uses_numbered_descriptions(self):
        """分析结果按照片顺序带编号，与正文配图标记编号对齐"""
        mock_provider = AsyncMock()
        mock_provider.analyze.return_value = "电极安装特写"

        mock_minio = MagicMock()
        resp = MagicMock()
        resp.read.return_value = b"data"
        mock_minio.get_object.return_value = resp

        with patch("app.articles.vision.get_vision_provider", return_value=mock_provider):
            with patch("app.articles.vision.get_minio_client", return_value=mock_minio):
                result = await analyze_photos(["a.jpg", "b.jpg"], "地下室防水")
        assert "【照片 1：a.jpg】" in result
        assert "【照片 2：b.jpg】" in result

    @pytest.mark.asyncio
    async def test_analyze_photos_prompt_forbids_fabrication(self):
        """视觉分析 prompt 含防编造约束"""
        mock_provider = AsyncMock()
        captured: dict = {}

        async def fake_analyze(img, prompt):
            captured["prompt"] = prompt
            return "描述"

        mock_provider.analyze.side_effect = fake_analyze

        mock_minio = MagicMock()
        resp = MagicMock()
        resp.read.return_value = b"data"
        mock_minio.get_object.return_value = resp

        with patch("app.articles.vision.get_vision_provider", return_value=mock_provider):
            with patch("app.articles.vision.get_minio_client", return_value=mock_minio):
                await analyze_photos(["a.jpg"], "地下室防水")
        assert "严禁推测" in captured["prompt"]
        assert "无法确认" in captured["prompt"]
