"""查询改写 测试 (TDD: RED)"""

from app.knowledge.rewriter import (
    expand_synonyms,
    normalize_query,
    rewrite_query,
)


MOCK_SYNONYM_MAP: dict[str, list[str]] = {
    "打卡": ["签到", "考勤"],
    "OA": ["办公系统", "审批系统"],
    "请假": ["休假", "调休"],
    "IT": ["信息技术", "技术部"],
}


class TestNormalizeQuery:
    def test_normalize_strips_whitespace(self):
        assert normalize_query("  你好 世界  ") == "你好 世界"

    def test_normalize_lowercase(self):
        assert normalize_query("Hello World") == "hello world"

    def test_normalize_removes_punctuation(self):
        assert normalize_query("你好！世界？") == "你好世界"

    def test_normalize_empty_string(self):
        assert normalize_query("") == ""

    def test_normalize_only_punctuation(self):
        assert normalize_query("！？。，") == ""


class TestExpandSynonyms:
    def test_expand_known_synonym(self):
        result = expand_synonyms("怎么打卡", MOCK_SYNONYM_MAP)
        assert "打卡" in result
        assert "签到" in result
        assert "考勤" in result

    def test_expand_no_synonym(self):
        result = expand_synonyms("今天天气怎么样", MOCK_SYNONYM_MAP)
        assert result == "今天天气怎么样"

    def test_expand_multiple_synonyms(self):
        result = expand_synonyms("OA请假流程", MOCK_SYNONYM_MAP)
        assert "办公系统" in result or "审批系统" in result

    def test_expand_empty_query(self):
        result = expand_synonyms("", MOCK_SYNONYM_MAP)
        assert result == ""

    def test_expand_empty_synonym_map(self):
        result = expand_synonyms("怎么打卡", {})
        assert result == "怎么打卡"


class TestRewriteQuery:
    def test_rewrite_with_synonyms(self):
        result = rewrite_query("打卡流程", MOCK_SYNONYM_MAP)
        assert len(result) >= len("打卡流程")

    def test_rewrite_no_history_no_synonym(self):
        result = rewrite_query("天气预报", MOCK_SYNONYM_MAP)
        assert "天气" in result

    def test_rewrite_empty_query(self):
        result = rewrite_query("", MOCK_SYNONYM_MAP)
        assert result == ""

    def test_rewrite_normalizes_first(self):
        result = rewrite_query("  Hello   World!  ", MOCK_SYNONYM_MAP)
        assert result == "hello world"


class TestExpandAndRewrite:
    def test_end_to_end(self):
        syn_map: dict[str, list[str]] = {"考核": ["绩效", "评估"]}
        result = rewrite_query("员工考核标准", syn_map)
        assert "考核" in result
        assert "绩效" in result

    def test_only_synonym_expansion(self):
        syn_map: dict[str, list[str]] = {"密码": ["口令"]}
        result = expand_synonyms("修改密码", syn_map)
        assert "密码" in result
        assert "口令" in result
