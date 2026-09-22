"""上下文窗口管理测试 — trim_history 保留最近历史 + generate 节点历史截断。"""

import pytest
from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from app.agents.window import trim_history


def _h(text: str) -> HumanMessage:
    return HumanMessage(content=text)


def _a(text: str) -> AIMessage:
    return AIMessage(content=text)


class TestTrimHistory:
    def test_empty(self):
        assert trim_history([], 8000) == []

    def test_under_budget_keeps_all(self, monkeypatch):
        monkeypatch.setattr(
            "app.agents.window.count_tokens", lambda text, model="gpt-3.5-turbo": 10
        )
        msgs = [_h("q1"), _a("a1"), _h("q2")]
        assert trim_history(msgs, 8000) == msgs

    def test_over_budget_keeps_most_recent(self, monkeypatch):
        """超预算时从最新往回保留（旧实现保留最旧，方向相反）"""
        monkeypatch.setattr(
            "app.agents.window.count_tokens", lambda text, model="gpt-3.5-turbo": 100
        )
        msgs = [_h("q1"), _a("a1"), _h("q2"), _a("a2"), _h("q3")]
        kept = trim_history(msgs, 250)
        assert kept == [_h("q3")]

    def test_trim_aligns_to_human_start(self, monkeypatch):
        """截断窗口以 AI 消息开头时丢弃开头 AI，保证 Human 起始"""
        monkeypatch.setattr(
            "app.agents.window.count_tokens", lambda text, model="gpt-3.5-turbo": 20
        )
        msgs = [_h("q1"), _a("a1"), _h("q2"), _a("a2"), _h("q3")]
        kept = trim_history(msgs, 85)
        assert kept == [_h("q2"), _a("a2"), _h("q3")]
        assert isinstance(kept[0], HumanMessage)

    def test_last_message_always_kept(self, monkeypatch):
        """单条超预算也保留最后一条（当前问题不能丢）"""
        monkeypatch.setattr(
            "app.agents.window.count_tokens", lambda text, model="gpt-3.5-turbo": 100000
        )
        msgs = [_h("q1"), _h("超长问题")]
        assert trim_history(msgs, 8000) == [_h("超长问题")]


def _make_astream(contents, captured):
    async def _astream(messages):
        captured["messages"] = messages
        for c in contents:
            yield type("Chunk", (), {"content": c})()

    return _astream


class TestGenerateHistoryTrim:
    @pytest.mark.asyncio
    async def test_internal_generate_trims_long_history(self, monkeypatch):
        from app.agents.nodes.generate import generate_node
        from app.agents.state import create_initial_state

        captured: dict = {}
        mock_llm = AsyncMock()
        mock_llm.astream = _make_astream(["答案"], captured)
        monkeypatch.setattr(
            "app.agents.window.count_tokens", lambda text, model="gpt-3.5-turbo": 1000
        )

        state = create_initial_state(thread_id="t", query="最新问题")
        history = []
        for i in range(20):
            history.append(_h(f"旧问{i}"))
            history.append(_a(f"旧答{i}"))
        history.append(_h("最新问题"))
        state["messages"] = history
        state["context"] = "[文档1] 参考内容"

        with patch("app.agents.nodes.generate.create_llm", return_value=mock_llm):
            await generate_node(state)

        sent_history = captured["messages"][1:-1]
        assert len(sent_history) <= 8
        assert isinstance(sent_history[0], HumanMessage)
        assert sent_history[-1].content == "最新问题"

    @pytest.mark.asyncio
    async def test_customer_generate_trims_long_history(self, monkeypatch):
        from app.agents.customer.generate import customer_generate_node
        from app.agents.customer_graph import create_customer_state

        captured: dict = {}
        mock_llm = AsyncMock()
        mock_llm.astream = _make_astream(["答案"], captured)
        monkeypatch.setattr(
            "app.agents.window.count_tokens", lambda text, model="gpt-3.5-turbo": 1000
        )

        state = create_customer_state(thread_id="t", query="最新问题")
        history = []
        for i in range(20):
            history.append(_h(f"旧问{i}"))
            history.append(_a(f"旧答{i}"))
        history.append(_h("最新问题"))
        state["messages"] = history
        state["context"] = "[文档1] 参考内容"

        with patch("app.agents.customer.generate.create_llm", return_value=mock_llm):
            await customer_generate_node(state)

        sent_history = captured["messages"][1:-1]
        assert len(sent_history) <= 8
        assert sent_history[-1].content == "最新问题"
