"""文档清洗 LLM 增强层测试（mock LLM，验证护栏与回退）"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.text_cleaner import clean_document_text
from app.services.text_cleaner_llm import (
    LENGTH_DEVIATION_LIMIT,
    llm_enhance_clean,
    split_into_segments,
)

DIRTY_TEXT = "=== Page 1 ===\n表格\n安全验收\n物理隔\n离"


def _mock_llm(response_text: str):
    llm = SimpleNamespace()
    llm.ainvoke = AsyncMock(return_value=SimpleNamespace(content=response_text))
    return llm


class TestSplitIntoSegments:
    def test_splits_by_heading(self):
        text = "# 章节一\n内容A\n# 章节二\n内容B"
        segments = split_into_segments(text, max_chars=1000)
        assert len(segments) == 2
        assert "章节一" in segments[0]
        assert "章节二" in segments[1]

    def test_no_heading_single_segment(self):
        text = "段落一\n段落二\n段落三"
        segments = split_into_segments(text, max_chars=1000)
        assert segments == [text]

    def test_splits_oversized_segment(self):
        text = "# 大章节\n" + ("长内容段落。\n" * 500)
        segments = split_into_segments(text, max_chars=200)
        assert len(segments) > 1
        assert all(len(s) <= 200 for s in segments)

    def test_empty_text(self):
        assert split_into_segments("", max_chars=100) == []


class TestLlmEnhanceClean:
    async def test_disabled_returns_rule_result(self):
        result = await llm_enhance_clean(DIRTY_TEXT, use_llm=False)
        expected = clean_document_text(DIRTY_TEXT)
        assert result.text == expected.text

    async def test_missing_api_key_falls_back(self):
        with patch("app.services.text_cleaner_llm.settings") as mock_settings:
            mock_settings.llm_api_key = ""
            result = await llm_enhance_clean(DIRTY_TEXT, use_llm=True)
        expected = clean_document_text(DIRTY_TEXT)
        assert result.text == expected.text

    async def test_llm_output_used_when_valid(self):
        enhanced = "安全验收说明\n物理隔离"
        with patch("app.services.text_cleaner_llm.settings") as mock_settings, patch(
            "app.services.text_cleaner_llm.create_llm", return_value=_mock_llm(enhanced)
        ):
            mock_settings.llm_api_key = "sk-test"
            result = await llm_enhance_clean(DIRTY_TEXT, use_llm=True)
        assert result.text == enhanced
        assert result.report.llm_enhanced is True

    async def test_llm_exception_falls_back_to_rules(self):
        llm = SimpleNamespace()
        llm.ainvoke = AsyncMock(side_effect=RuntimeError("API down"))
        with patch("app.services.text_cleaner_llm.settings") as mock_settings, patch(
            "app.services.text_cleaner_llm.create_llm", return_value=llm
        ):
            mock_settings.llm_api_key = "sk-test"
            result = await llm_enhance_clean(DIRTY_TEXT, use_llm=True)
        expected = clean_document_text(DIRTY_TEXT)
        assert result.text == expected.text
        assert result.report.llm_enhanced is False

    async def test_length_guard_rejects_hallucination(self):
        base = clean_document_text(DIRTY_TEXT)
        hallucinated = base.text + "大量虚构内容" * 50
        with patch("app.services.text_cleaner_llm.settings") as mock_settings, patch(
            "app.services.text_cleaner_llm.create_llm", return_value=_mock_llm(hallucinated)
        ):
            mock_settings.llm_api_key = "sk-test"
            result = await llm_enhance_clean(DIRTY_TEXT, use_llm=True)
        assert result.text == base.text
        assert result.report.llm_enhanced is False

    async def test_length_guard_rejects_truncation(self):
        with patch("app.services.text_cleaner_llm.settings") as mock_settings, patch(
            "app.services.text_cleaner_llm.create_llm", return_value=_mock_llm("安全")
        ):
            mock_settings.llm_api_key = "sk-test"
            result = await llm_enhance_clean(DIRTY_TEXT, use_llm=True)
        base = clean_document_text(DIRTY_TEXT)
        assert result.text == base.text

    async def test_length_deviation_limit_sane(self):
        assert 0 < LENGTH_DEVIATION_LIMIT <= 1.0
