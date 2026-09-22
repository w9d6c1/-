"""FAQ 精准匹配节点 测试 (TDD: RED)"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.documents import Document


class TestFAQNode:
    @pytest.mark.asyncio
    async def test_faq_hit_high_score(self):
        from app.agents.nodes.faq import faq_match_node
        from app.agents.state import create_initial_state

        state = create_initial_state("t1", "怎么打卡考勤")
        state["user_scopes"] = ["public", "internal"]

        with patch("app.agents.nodes.faq.embed_query", new=AsyncMock(return_value=[0.1] * 1024)):
            with patch("app.agents.nodes.faq.FAQ_VECTORS", [
                {
                    "content": "考勤打卡：每日9点前在OA系统完成打卡签到",
                    "vector": [0.1] * 1024,
                    "scope": "public",
                },
            ]):
                result = await faq_match_node(state)
                assert result["faq_hit"] is True
                assert result["faq_answer"] is not None

    @pytest.mark.asyncio
    async def test_faq_miss_low_score(self):
        from app.agents.nodes.faq import faq_match_node
        from app.agents.state import create_initial_state

        state = create_initial_state("t2", "今天天气怎么样")
        state["user_scopes"] = ["public"]

        # 与查询正交的向量 → 余弦相似度 ~0 → 未命中
        orthogonal = [0.1] * 512 + [-0.1] * 512
        with patch("app.agents.nodes.faq.embed_query", new=AsyncMock(return_value=[0.1] * 1024)):
            with patch("app.agents.nodes.faq.FAQ_VECTORS", [
                {"content": "考勤打卡：每日9点前完成", "vector": orthogonal, "scope": "public"},
            ]):
                result = await faq_match_node(state)
                assert result["faq_hit"] is False
                assert result["faq_answer"] is None

    @pytest.mark.asyncio
    async def test_faq_no_vectors(self):
        from app.agents.nodes.faq import faq_match_node
        from app.agents.state import create_initial_state

        state = create_initial_state("t3", "怎么打卡")
        state["user_scopes"] = ["public"]

        with patch("app.agents.nodes.faq.embed_query", new=AsyncMock(return_value=[0.1] * 1024)):
            with patch("app.agents.nodes.faq.FAQ_VECTORS", []):
                result = await faq_match_node(state)
                assert result["faq_hit"] is False

    @pytest.mark.asyncio
    async def test_faq_scope_filter(self):
        from app.agents.nodes.faq import faq_match_node
        from app.agents.state import create_initial_state

        state = create_initial_state("t4", "内部机密", user_role="dept_admin")
        state["user_scopes"] = ["public"]

        with patch("app.agents.nodes.faq.embed_query", new=AsyncMock(return_value=[0.1] * 1024)):
            with patch("app.agents.nodes.faq.FAQ_VECTORS", [
                {"content": "内部数据", "vector": [0.1] * 1024, "scope": "internal"},
            ]):
                result = await faq_match_node(state)
                assert result["faq_hit"] is False


class TestCosineSim:
    def test_cosine_identical(self):
        from app.agents.nodes.faq import _cosine_sim

        a = [1.0, 0.0, 0.0]
        b = [1.0, 0.0, 0.0]
        assert _cosine_sim(a, b) == pytest.approx(1.0)

    def test_cosine_orthogonal(self):
        from app.agents.nodes.faq import _cosine_sim

        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert _cosine_sim(a, b) == pytest.approx(0.0)
