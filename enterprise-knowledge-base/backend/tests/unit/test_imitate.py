"""单元测试 — 模仿创作：字数控制 + 编号配图标记"""

from unittest.mock import patch

import pytest

from app.articles.imitate import imitate_article


class TestImitateArticle:
    @pytest.mark.asyncio
    async def test_honors_word_range(self):
        """模仿文章字数落在目标区间内，不触发修复调用（标题+正文两次）"""
        calls = []

        async def fake_llm(llm, messages, max_retries=3, **kwargs):
            calls.append(1)
            if len(calls) == 1:
                return "模仿标题"
            return "模仿正文内容充实专业。" * 150  # 1650 字

        with patch("app.articles.imitate.call_llm_with_retry", side_effect=fake_llm):
            result = await imitate_article(
                topic="电渗透防潮",
                style_analysis={"tone": "专业权威"},
                min_words=1200,
                max_words=3000,
            )
        assert 1200 <= result["word_count"] <= 3000
        assert len(calls) == 2

    @pytest.mark.asyncio
    async def test_repairs_short_content(self):
        """字数不足时调用扩写修复（第 3 次调用），最终达标"""
        calls = []

        async def fake_llm(llm, messages, max_retries=3, **kwargs):
            calls.append(1)
            if len(calls) == 1:
                return "标题"
            if len(calls) == 2:
                return "太短的正文" * 60  # 300 字
            return "扩写后的完整模仿正文，内容详实。" * 150  # >= 1200

        with (
            patch("app.articles.imitate.call_llm_with_retry", side_effect=fake_llm),
            patch("app.articles.generator.call_llm_with_retry", side_effect=fake_llm),
        ):
            result = await imitate_article(
                topic="电渗透防潮",
                style_analysis={},
                min_words=1200,
                max_words=3000,
            )
        assert result["word_count"] >= 1200
        assert len(calls) == 3

    @pytest.mark.asyncio
    async def test_numbered_markers_mapped_to_photos(self):
        """配图标记按照片编号精确映射，不再顺序循环"""
        calls = []

        async def fake_llm(llm, messages, max_retries=3, **kwargs):
            calls.append(1)
            if len(calls) == 1:
                return "标题"
            body = (
                "第一段。[IMAGE: 照片2: 配图建议: 电极安装]\n\n"
                "第二段。[IMAGE: 照片1: 配图建议: 主机全貌]\n\n"
            )
            return body + "充实内容。" * 300  # 够长，不触发修复

        with patch("app.articles.imitate.call_llm_with_retry", side_effect=fake_llm):
            result = await imitate_article(
                topic="电渗透防潮",
                style_analysis={},
                photo_object_names=["p1.jpg", "p2.jpg"],
                min_words=1200,
                max_words=3000,
            )
        assert result["image_placement"][0]["object_name"] == "p2.jpg"
        assert result["image_placement"][1]["object_name"] == "p1.jpg"
