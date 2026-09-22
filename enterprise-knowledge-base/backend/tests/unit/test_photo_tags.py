"""单元测试 — 照片 AI 打标：限流重试 + 失败降级 + 失败保留原标签"""

import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.articles.photo_service import PhotoService


def _service() -> PhotoService:
    return PhotoService(db=None)


async def _no_sleep(_sec):
    return None


class TestAnalyzePhotoRetry:
    @pytest.mark.asyncio
    async def test_retries_then_succeeds_on_429(self):
        """前两次 429 限流，第三次成功 → 返回标签并重试 3 次"""
        provider = AsyncMock()
        provider.analyze.side_effect = [
            RuntimeError("Client error '429 Too Many Requests'"),
            RuntimeError("Client error '429 Too Many Requests'"),
            json.dumps({"tags": ["地下室", "电渗透"], "description": "地下室电渗透施工"}),
        ]

        with patch("app.articles.vision.get_vision_provider", return_value=provider):
            with patch("app.articles.photo_service.asyncio.sleep", new=_no_sleep):
                tags, desc = await _service()._analyze_photo(b"fake-img", "test.jpg")

        assert tags == ["地下室", "电渗透"]
        assert "电渗透施工" in desc
        assert provider.analyze.await_count == 3

    @pytest.mark.asyncio
    async def test_returns_empty_after_all_retries_fail(self):
        """一直失败（如持续 429）→ 返回空标签 + 文件名描述，共重试 3 次"""
        provider = AsyncMock()
        provider.analyze.side_effect = RuntimeError("429 Too Many Requests")

        with patch("app.articles.vision.get_vision_provider", return_value=provider):
            with patch("app.articles.photo_service.asyncio.sleep", new=_no_sleep):
                tags, desc = await _service()._analyze_photo(b"fake-img", "test.jpg")

        assert tags == []
        assert desc == "test.jpg"
        assert provider.analyze.await_count == 3

    @pytest.mark.asyncio
    async def test_single_success_no_retry(self):
        """首次成功 → 不重试"""
        provider = AsyncMock()
        provider.analyze.return_value = json.dumps({"tags": ["屋顶"], "description": "屋顶卷材施工"})

        with patch("app.articles.vision.get_vision_provider", return_value=provider):
            tags, desc = await _service()._analyze_photo(b"fake-img", "test.jpg")

        assert tags == ["屋顶"]
        assert provider.analyze.await_count == 1

    @pytest.mark.asyncio
    async def test_no_provider_returns_empty(self):
        """未配置 vision key → 直接返回空标签，不调用 analyze"""
        with patch("app.articles.vision.get_vision_provider", return_value=None):
            tags, desc = await _service()._analyze_photo(b"fake-img", "test.jpg")
        assert tags == []
        assert desc == "test.jpg"

    @pytest.mark.asyncio
    async def test_strips_markdown_fence(self):
        """模型返回带 ``` 包裹的 JSON 时能正确解析"""
        provider = AsyncMock()
        provider.analyze.return_value = '```json\n{"tags": ["堵漏"], "description": "堵漏施工"}\n```'

        with patch("app.articles.vision.get_vision_provider", return_value=provider):
            tags, desc = await _service()._analyze_photo(b"fake-img", "test.jpg")
        assert tags == ["堵漏"]
        assert desc == "堵漏施工"


class TestSuggestTagsPreserve:
    @pytest.mark.asyncio
    async def test_preserves_existing_tags_on_failure(self, db_session):
        """视觉分析失败（如 429）时，suggest_tags 保留原标签与描述，不清空"""
        from app.articles.models import Photo

        photo = Photo(
            object_name="photo-library/1/a.jpg",
            filename="a.jpg",
            tags=["地下室", "电渗透"],
            description="原始描述",
            user_id=1,
        )
        db_session.add(photo)
        await db_session.commit()
        await db_session.refresh(photo)
        pid = photo.id

        async def no_sleep(_sec):
            return None

        provider = AsyncMock()
        provider.analyze.side_effect = RuntimeError("429 Too Many Requests")

        mock_minio = MagicMock()
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"fake"
        mock_minio.get_object.return_value = mock_resp

        svc = PhotoService(db_session)
        with patch("app.articles.vision.get_vision_provider", return_value=provider):
            with patch("app.articles.photo_service.asyncio.sleep", new=no_sleep):
                with patch("app.articles.photo_service.get_minio_client", return_value=mock_minio):
                    tags = await svc.suggest_tags(pid)

        assert tags == ["地下室", "电渗透"]
        await db_session.refresh(photo)
        assert photo.tags == ["地下室", "电渗透"]
        assert photo.description == "原始描述"

    @pytest.mark.asyncio
    async def test_overwrites_on_success(self, db_session):
        """视觉分析成功时，suggest_tags 用新结果覆盖"""
        from app.articles.models import Photo

        photo = Photo(
            object_name="photo-library/2/b.jpg",
            filename="b.jpg",
            tags=["旧标签"],
            description="旧描述",
            user_id=1,
        )
        db_session.add(photo)
        await db_session.commit()
        await db_session.refresh(photo)
        pid = photo.id

        provider = AsyncMock()
        provider.analyze.return_value = json.dumps({"tags": ["外墙"], "description": "新描述"})

        mock_minio = MagicMock()
        mock_resp = MagicMock()
        mock_resp.read.return_value = b"fake"
        mock_minio.get_object.return_value = mock_resp

        svc = PhotoService(db_session)
        with patch("app.articles.vision.get_vision_provider", return_value=provider):
            with patch("app.articles.photo_service.get_minio_client", return_value=mock_minio):
                tags = await svc.suggest_tags(pid)

        assert tags == ["外墙"]
        await db_session.refresh(photo)
        assert photo.tags == ["外墙"]
        assert photo.description == "新描述"


class TestSanitizeTags:
    def test_drops_long_phrase_tags(self):
        """丢弃 >=9 字的长句/标语标签（如广告语），保留短标签"""
        raw = ["室内", "环境场景", "特莱顿电渗透要打造好房子"]
        assert _service()._sanitize_tags(raw) == ["室内", "环境场景"]

    def test_keeps_short_tags_and_caps_at_six(self):
        """保留 2-8 字标签，去重，最多 6 个"""
        raw = ["电渗透", "电极", "电渗透", "注浆", "地下室", "外墙", "屋顶", "地面"]
        result = _service()._sanitize_tags(raw)
        assert result == ["电渗透", "电极", "注浆", "地下室", "外墙", "屋顶"]
        assert len(result) == 6

    def test_strips_whitespace_and_filters_non_string(self):
        """去除标签首尾空白，丢弃非字符串/单字符/空值"""
        raw = [" 电渗透 ", "", "堵漏", 123, "地", None]
        assert _service()._sanitize_tags(raw) == ["电渗透", "堵漏"]

    @pytest.mark.asyncio
    async def test_applied_in_analyze_photo(self):
        """_analyze_photo 解析后经过清洗，长句标签不会入库"""
        provider = AsyncMock()
        provider.analyze.return_value = json.dumps(
            {"tags": ["室内", "特莱顿电渗透要打造好房子"], "description": "室内环境"}
        )
        with patch("app.articles.vision.get_vision_provider", return_value=provider):
            tags, desc = await _service()._analyze_photo(b"fake-img", "test.jpg")
        assert tags == ["室内"]
        assert desc == "室内环境"
