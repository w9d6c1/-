"""采集层跨平台去重测试"""

from app.collector.dedup import (
    content_fingerprint,
    content_hash,
    content_similar,
    hamming_distance,
    is_duplicate,
    normalize_text,
    title_similarity,
)

_TEXT_A = "特莱顿电渗透脉冲防潮系统通过电场作用阻止水分毛细渗透，适用于地下室与隧道工程。"
_TEXT_A_VARIANT = "特莱顿电渗透脉冲防潮系统通过电场作用阻止水分毛细渗透，适用于地下室与隧道工程！"
_TEXT_B = "公司年度培训计划涵盖安全生产、职业技能与管理制度三大模块，每季度组织一次考核。"


class TestNormalize:
    def test_removes_whitespace_and_lowercases(self):
        assert normalize_text("  Hello  World ") == "helloworld"

    def test_empty(self):
        assert normalize_text("") == ""
        assert normalize_text(None) == ""


class TestContentHash:
    def test_same_content_different_whitespace(self):
        assert content_hash("你好 世界") == content_hash("你好世界")

    def test_different_content(self):
        assert content_hash(_TEXT_A) != content_hash(_TEXT_B)

    def test_is_sha256_hex(self):
        h = content_hash(_TEXT_A)
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


class TestSimHash:
    def test_identical_text_zero_distance(self):
        fp1 = content_fingerprint(_TEXT_A)
        fp2 = content_fingerprint(_TEXT_A)
        assert fp1 == fp2
        assert hamming_distance(fp1, fp2) == 0

    def test_near_identical_small_distance(self):
        fp1 = content_fingerprint(_TEXT_A)
        fp2 = content_fingerprint(_TEXT_A_VARIANT)
        assert hamming_distance(fp1, fp2) <= 3

    def test_different_text_large_distance(self):
        fp1 = content_fingerprint(_TEXT_A)
        fp2 = content_fingerprint(_TEXT_B)
        assert hamming_distance(fp1, fp2) > 6

    def test_empty_text_fingerprint_zero(self):
        assert content_fingerprint("") == 0


class TestContentSimilar:
    def test_near_identical_is_similar(self):
        assert content_similar(_TEXT_A, _TEXT_A_VARIANT) is True

    def test_different_is_not_similar(self):
        assert content_similar(_TEXT_A, _TEXT_B) is False

    def test_empty_not_similar(self):
        assert content_similar("", _TEXT_A) is False


class TestTitleSimilarity:
    def test_identical_title(self):
        assert title_similarity("产品发布说明", "产品发布说明") == 1.0

    def test_similar_title_high_ratio(self):
        assert title_similarity("产品发布说明", "产品发布说明（修订）") > 0.6

    def test_different_title_low_ratio(self):
        assert title_similarity("产品发布", "员工考勤制度") < 0.5

    def test_empty_title(self):
        assert title_similarity("", "标题") == 0.0


class TestIsDuplicate:
    def test_same_content_is_duplicate(self):
        assert is_duplicate("标题A", _TEXT_A, "标题B", _TEXT_A_VARIANT) is True

    def test_different_content_not_duplicate(self):
        assert is_duplicate("标题A", _TEXT_A, "标题B", _TEXT_B) is False

    def test_same_title_similar_content_is_duplicate(self):
        title = "电渗透防潮系统技术说明"
        assert is_duplicate(title, _TEXT_A, title, _TEXT_A_VARIANT) is True

    def test_empty_text_not_duplicate(self):
        assert is_duplicate("标题", "", "标题", _TEXT_A) is False
