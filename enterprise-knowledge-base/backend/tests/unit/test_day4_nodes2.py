"""generate + output + log 节点 测试 (TDD: RED)"""

import pytest
from unittest.mock import MagicMock, patch


def _make_astream(contents: list[str]):
    async def _stream(messages):
        for c in contents:
            yield MagicMock(content=c)
    return _stream


class TestGenerateNode:
    @pytest.mark.asyncio
    async def test_generate_with_context(self):
        from app.agents.nodes.generate import generate_node
        from app.agents.state import create_initial_state

        state = create_initial_state("t1", "考勤制度")
        state["rewritten_query"] = "考勤制度查询"
        state["context"] = "[文档1] 考勤：每日9点前打卡\n[来源: 考勤手册]"

        mock_llm = MagicMock()
        mock_llm.astream = _make_astream(["根据考勤手册，员工需每日9点前完成打卡。"])

        with patch("app.agents.nodes.generate.create_llm", return_value=mock_llm):
            result = await generate_node(state)
            assert len(result["final_answer"]) > 0

    @pytest.mark.asyncio
    async def test_generate_no_context(self):
        from app.agents.nodes.generate import generate_node
        from app.agents.state import create_initial_state
        from app.core.config import settings

        state = create_initial_state("t2", "你好")
        with patch("app.agents.nodes.generate.create_llm") as mock_llm:
            result = await generate_node(state)
        assert result["final_answer"] == settings.no_answer_reply
        mock_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_generate_citation_format(self):
        from app.agents.nodes.generate import generate_node
        from app.agents.state import create_initial_state

        state = create_initial_state("t3", "考勤")
        state["rewritten_query"] = "考勤查询"
        state["context"] = "[文档1] 考勤制度\n[来源: 考勤手册]"

        mock_llm = MagicMock()
        mock_llm.astream = _make_astream(["答案 [来源: 考勤手册]"])

        with patch("app.agents.nodes.generate.create_llm", return_value=mock_llm):
            result = await generate_node(state)
            assert "[来源" in result["final_answer"]

    @pytest.mark.asyncio
    async def test_generate_faq_hit_skips_llm(self):
        """FAQ 命中时直接返回维护好的答案，不调用 LLM（提速）"""
        from app.agents.nodes.generate import generate_node
        from app.agents.state import create_initial_state

        state = create_initial_state("t_faq", "公司工作时间")
        state["faq_hit"] = True
        state["faq_answer"] = "工作时间为周一至周五 9:00-18:00。"

        with patch("app.agents.nodes.generate.create_llm") as mock_llm:
            result = await generate_node(state)

        assert result["faq_direct"] is True
        assert "9:00-18:00" in result["final_answer"]
        mock_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_generate_faq_direct_disabled_uses_llm(self):
        """FAQ_DIRECT_ANSWER=false 时仍走 LLM 生成"""
        from app.agents.nodes.generate import generate_node
        from app.agents.state import create_initial_state

        state = create_initial_state("t_faq2", "公司工作时间")
        state["faq_hit"] = True
        state["faq_answer"] = "工作时间为周一至周五 9:00-18:00。"
        state["context"] = f"参考FAQ答案：\n{state['faq_answer']}"

        mock_llm = MagicMock()
        mock_llm.astream = _make_astream(["基于FAQ，工作时间为 9:00-18:00。"])

        with patch("app.agents.nodes.generate.create_llm", return_value=mock_llm) as mock_create:
            with patch("app.agents.nodes.generate.settings.faq_direct_answer", False):
                result = await generate_node(state)

        assert result.get("faq_direct") is not True
        assert "9:00-18:00" in result["final_answer"]
        mock_create.assert_called_once()


class TestOutputNode:
    def test_filter_sensitive_words(self):
        from app.agents.nodes.output import filter_sensitive_words

        text = "这是正常内容"
        patterns = ["违禁词"]
        result = filter_sensitive_words(text, patterns)
        assert result == "这是正常内容"

    def test_filter_sensitive_words_blocks(self):
        from app.agents.nodes.output import filter_sensitive_words

        text = "包含违禁词的信息"
        patterns = ["违禁词"]
        result = filter_sensitive_words(text, patterns)
        assert "违禁词" not in result
        assert "***" in result

    def test_compute_confidence_high(self):
        from app.agents.nodes.output import compute_confidence

        assert compute_confidence(faq_hit=True, avg_retrieval_score=0.0) >= 0.9

    def test_compute_confidence_low(self):
        from app.agents.nodes.output import compute_confidence

        confidence = compute_confidence(faq_hit=False, avg_retrieval_score=0.3)
        assert confidence < 0.5

    def test_validate_output_node_compliant(self):
        from app.agents.nodes.output import validate_output_node
        from app.agents.state import create_initial_state

        state = create_initial_state("t4", "测试")
        state["final_answer"] = "这是合规的答案"
        state["faq_hit"] = True

        result = validate_output_node(state)
        assert result["is_compliant"] is True
        assert result["needs_human"] is False

    def test_validate_output_low_confidence_triggers_human(self):
        from app.agents.nodes.output import validate_output_node
        from app.agents.state import create_initial_state

        state = create_initial_state("t5", "测试")
        state["final_answer"] = "一个不太确定的答案"
        state["faq_hit"] = False
        state["retrieved_docs"] = []

        result = validate_output_node(state)
        assert result["needs_human"] is True


class TestLogNode:
    @pytest.mark.asyncio
    async def test_log_node_no_error(self):
        from app.agents.nodes.logging import log_node
        from app.agents.state import create_initial_state

        state = create_initial_state("t6", "测试")
        state["final_answer"] = "答案"
        result = await log_node(state)
        assert result["error"] is None
