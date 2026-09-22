"""文档文本清洗引擎测试（规则清洗层）

覆盖：页标记清除、占位行清除、孤儿碎片合并、CJK 空格规范化、
空行压缩，以及真实转换样本上的内容保全与幂等性。
"""

from collections import Counter
from pathlib import Path

import pytest

from app.services.text_cleaner import (
    CleanReport,
    CleanResult,
    clean_document_text,
    collapse_blank_lines,
    merge_orphan_fragments,
    remove_cjk_spaces,
    strip_page_markers,
    strip_placeholders,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


def _cjk_counter(text: str) -> Counter:
    return Counter(ch for ch in text if "\u4e00" <= ch <= "\u9fff")


class TestStripPageMarkers:
    def test_removes_equals_page_marker(self):
        text = "=== Page 1 ===\n正文内容\n=== Page 2 ===\n更多内容"
        result, count = strip_page_markers(text)
        assert "=== Page" not in result
        assert "正文内容" in result
        assert "更多内容" in result
        assert count == 2

    def test_removes_bracket_marker(self):
        text = "[P1]\n内容A\n[P2]\n内容B"
        result, count = strip_page_markers(text)
        assert "[P1]" not in result
        assert "[P2]" not in result
        assert "内容A" in result
        assert count == 2

    def test_removes_page_n_of_m(self):
        text = "内容\nPage 3 of 10\n结尾"
        result, count = strip_page_markers(text)
        assert "Page 3 of 10" not in result
        assert "内容" in result
        assert "结尾" in result
        assert count == 1

    def test_preserves_inline_page_word(self):
        text = "请参考 Page 配置说明\n落地页优化"
        result, count = strip_page_markers(text)
        assert "请参考 Page 配置说明" in result
        assert "落地页优化" in result
        assert count == 0

    def test_removes_inline_marker_in_collapsed_text(self):
        text = "内容A === Page 1 === 内容B"
        result, count = strip_page_markers(text)
        assert "=== Page" not in result
        assert "内容A" in result
        assert "内容B" in result
        assert count == 1

    def test_removes_inline_bracket_marker(self):
        text = "段落 [P3] 继续"
        result, count = strip_page_markers(text)
        assert "[P3]" not in result
        assert count == 1

    def test_removes_chinese_page_marker(self):
        text = "第1页\n内容\n第 2 页\n更多"
        result, count = strip_page_markers(text)
        assert count == 2
        assert "内容" in result
        assert "更多" in result

    def test_keeps_chinese_page_in_sentence(self):
        text = "详见第3页的说明表格"
        result, count = strip_page_markers(text)
        assert result == text
        assert count == 0

    def test_empty_input(self):
        result, count = strip_page_markers("")
        assert result == ""
        assert count == 0


class TestStripPlaceholders:
    def test_removes_standalone_table_placeholder(self):
        text = "前文\n表格\n检查项\n具体操作"
        result, count = strip_placeholders(text)
        lines = result.split("\n")
        assert "表格" not in lines
        assert "检查项" in lines
        assert count == 1

    def test_keeps_placeholder_in_longer_text(self):
        text = "数据表格说明\n表格如下"
        result, count = strip_placeholders(text)
        assert "数据表格说明" in result
        assert "表格如下" in result
        assert count == 0

    def test_removes_image_placeholder(self):
        text = "内容\n图片\n后续"
        result, count = strip_placeholders(text)
        assert "图片" not in result.split("\n")
        assert count == 1

    def test_removes_symbol_only_heading(self):
        text = "### >\n内容\n##\n-\n结尾"
        result, count = strip_placeholders(text)
        lines = result.split("\n")
        assert "### >" not in lines
        assert "##" not in lines
        assert "内容" in lines
        assert "结尾" in lines
        assert count == 2

    def test_keeps_real_heading(self):
        text = "### 真实标题\n内容"
        result, count = strip_placeholders(text)
        assert "### 真实标题" in result
        assert count == 0


class TestMergeOrphanFragments:
    def test_merges_single_char_orphan(self):
        text = "物理隔\n离"
        result, count = merge_orphan_fragments(text)
        assert result == "物理隔离"
        assert count == 1

    def test_merges_two_char_orphan(self):
        text = "链路日\n志项"
        result, count = merge_orphan_fragments(text)
        assert result == "链路日志项"
        assert count == 1

    def test_merges_trailing_orphan_after_multichar(self):
        text = "对话全\n链路日\n志"
        result, _ = merge_orphan_fragments(text)
        assert "链路日志" in result

    def test_no_merge_after_terminal_punctuation(self):
        text = "句子结束。\n离"
        result, count = merge_orphan_fragments(text)
        assert count == 0
        assert result.split("\n") == ["句子结束。", "离"]

    def test_no_merge_when_orphan_has_punctuation(self):
        text = "前置内容\n，离"
        result, count = merge_orphan_fragments(text)
        assert count == 0

    def test_no_merge_into_heading(self):
        text = "# 标题\n离"
        result, count = merge_orphan_fragments(text)
        assert count == 0
        assert "# 标题" in result

    def test_no_merge_into_table_row(self):
        text = "| 单元格 |\n离"
        result, count = merge_orphan_fragments(text)
        assert count == 0

    def test_keeps_three_char_line_separate(self):
        text = "向量层\n物理隔"
        result, count = merge_orphan_fragments(text)
        assert "向量层" in result.split("\n")
        assert count == 0

    def test_merges_content_into_bullet_marker(self):
        text = "-\n道具：负压防水展示墙\n-\n目的：让客户直观看到局限性"
        result, count = merge_orphan_fragments(text)
        assert "- 道具：负压防水展示墙" in result
        assert "- 目的：让客户直观看到局限性" in result
        assert count == 2

    def test_bullet_merge_skips_heading_line(self):
        text = "-\n# 标题"
        result, count = merge_orphan_fragments(text)
        assert "# 标题" in result.split("\n")
        assert count == 0

    def test_consecutive_bullet_markers_not_merged(self):
        text = "-\n-\n内容"
        result, count = merge_orphan_fragments(text)
        lines = result.split("\n")
        assert lines.count("-") == 1
        assert "- 内容" in lines
        assert count == 1


class TestRemoveCjkSpaces:
    def test_removes_space_between_cjk(self):
        assert remove_cjk_spaces("内部 问答") == "内部问答"

    def test_removes_space_latin_to_cjk(self):
        assert remove_cjk_spaces("scope 的文档") == "scope的文档"

    def test_removes_space_digit_to_cjk(self):
        assert remove_cjk_spaces("1 轮对话") == "1轮对话"

    def test_removes_space_cjk_to_latin(self):
        assert remove_cjk_spaces("命中 FAQ 库") == "命中FAQ库"

    def test_preserves_space_around_operator(self):
        assert remove_cjk_spaces("customer + public") == "customer + public"

    def test_preserves_comparison_spacing(self):
        assert remove_cjk_spaces("P95 < 300ms") == "P95 < 300ms"

    def test_preserves_pure_latin_sentence(self):
        assert remove_cjk_spaces("docker compose up") == "docker compose up"

    def test_no_change_on_empty(self):
        assert remove_cjk_spaces("") == ""


class TestCollapseBlankLines:
    def test_collapses_multiple_blank_lines(self):
        text = "段落A\n\n\n\n段落B"
        result, count = collapse_blank_lines(text)
        assert result == "段落A\n\n段落B"
        assert count >= 1

    def test_single_blank_line_preserved(self):
        text = "段落A\n\n段落B"
        result, count = collapse_blank_lines(text)
        assert result == "段落A\n\n段落B"
        assert count == 0

    def test_strips_leading_trailing_blank(self):
        text = "\n\n内容\n\n"
        result, _ = collapse_blank_lines(text)
        assert result == "内容"


class TestCleanDocumentText:
    def test_returns_clean_result(self):
        result = clean_document_text("=== Page 1 ===\n内容")
        assert isinstance(result, CleanResult)
        assert isinstance(result.report, CleanReport)
        assert "=== Page" not in result.text

    def test_report_tracks_original_and_cleaned_chars(self):
        text = "=== Page 1 ===\n正文"
        result = clean_document_text(text)
        assert result.report.original_chars == len(text)
        assert result.report.cleaned_chars == len(result.text)

    def test_full_pipeline_on_simple_input(self):
        text = "=== Page 1 ===\n表格\n检查项\n物理隔\n离\n\n\n\n结束"
        result = clean_document_text(text)
        assert "=== Page" not in result.text
        assert "表格" not in result.text.split("\n")
        assert "物理隔离" in result.text
        assert "检查项" in result.text
        assert "结束" in result.text

    def test_strips_bom_and_invisible_chars(self):
        text = "\ufeff第1页\n内容\u200b正文"
        result = clean_document_text(text)
        assert "\ufeff" not in result.text
        assert "\u200b" not in result.text
        assert "第1页" not in result.text
        assert "内容正文" in result.text


class TestRealFixtures:
    @pytest.fixture
    def sample_10(self) -> str:
        return (FIXTURES / "sample_10.md").read_text(encoding="utf-8")

    @pytest.fixture
    def sample_9(self) -> str:
        return (FIXTURES / "sample_9.md").read_text(encoding="utf-8")

    def test_removes_all_page_markers(self, sample_10):
        result = clean_document_text(sample_10)
        assert "=== Page" not in result.text

    def test_removes_table_placeholders(self, sample_10):
        result = clean_document_text(sample_10)
        lines = [ln.strip() for ln in result.text.split("\n")]
        assert "表格" not in lines

    def test_preserves_key_content(self, sample_10):
        result = clean_document_text(sample_10)
        for phrase in ["安全隔离专项验收", "向量层", "路由层", "跨库隔离泄漏率"]:
            assert phrase in result.text, f"丢失关键内容: {phrase}"

    def test_merges_orphan_fragments_in_sample(self, sample_10):
        result = clean_document_text(sample_10)
        assert "物理隔离" in result.text

    def test_cjk_content_preserved(self, sample_10):
        result = clean_document_text(sample_10)
        original = _cjk_counter(sample_10)
        cleaned = _cjk_counter(result.text)
        removed_placeholders = result.report.removed_placeholders
        expected = original - Counter({"表": removed_placeholders, "格": removed_placeholders})
        missing = expected - cleaned
        assert not missing, f"清洗丢失了 CJK 字符: {dict(missing)}"

    def test_idempotent(self, sample_10):
        once = clean_document_text(sample_10)
        twice = clean_document_text(once.text)
        assert twice.text == once.text

    def test_idempotent_sample_9(self, sample_9):
        once = clean_document_text(sample_9)
        twice = clean_document_text(once.text)
        assert twice.text == once.text

    def test_reduces_noise_chars(self, sample_10):
        result = clean_document_text(sample_10)
        assert len(result.text) < len(sample_10)
