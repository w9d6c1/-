"""集成测试 — 智能体 SSE 流式端点 (内部 + 客服)"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class _FakeGraph:
    """模拟 LangGraph:aget_state 无历史, astream_events 按脚本生成事件。"""

    def __init__(self, events=None, raise_on_stream=False):
        self._events = events or []
        self._raise = raise_on_stream
        self.aget_state = AsyncMock(return_value=None)
        self.aupdate_state = AsyncMock()

    async def astream_events(self, state, version="v2", config=None):
        if self._raise:
            raise RuntimeError("simulated graph failure")
        for event in self._events:
            yield event


def _token_event(content: str):
    return {
        "event": "on_chat_model_stream",
        "data": {"chunk": SimpleNamespace(content=content)},
    }


def _done_event(answer: str, **extra):
    output = {
        "final_answer": answer,
        "confidence": extra.get("confidence", 0.9),
        "needs_human": extra.get("needs_human", False),
        "faq_hit": extra.get("faq_hit", False),
        "citations": [],
        "doc_images": [],
    }
    return {"event": "on_chain_end", "data": {"output": output}, "name": "output"}


def _parse_events(body: str) -> list[dict]:
    events = []
    for line in body.splitlines():
        if line.startswith("data: ") and line[6:] != "[DONE]":
            events.append(json.loads(line[6:]))
    return events


class TestInternalChatStream:
    @pytest.mark.asyncio
    async def test_streams_tokens_and_done(self, client):
        graph = _FakeGraph(events=[_token_event("你"), _token_event("好"), _done_event("你好世界")])
        with patch("app.api.agent._agent_graph", graph):
            resp = await client.post(
                "/api/agent/internal/chat/stream", json={"message": "打招呼"}
            )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]
        events = _parse_events(resp.text)
        assert [e["type"] for e in events] == ["token", "token", "done"]
        assert events[0]["content"] == "你"
        assert events[2]["answer"] == "你好世界"
        assert resp.text.rstrip().endswith("data: [DONE]")

    @pytest.mark.asyncio
    async def test_done_event_emitted_once(self, client):
        graph = _FakeGraph(
            events=[
                _token_event("a"),
                _done_event("答案"),
                _done_event("第二次答案"),
            ]
        )
        with patch("app.api.agent._agent_graph", graph):
            resp = await client.post(
                "/api/agent/internal/chat/stream", json={"message": "重复 done"}
            )
        events = _parse_events(resp.text)
        done = [e for e in events if e["type"] == "done"]
        assert len(done) == 1

    @pytest.mark.asyncio
    async def test_stream_error_yields_friendly_event(self, client):
        graph = _FakeGraph(raise_on_stream=True)
        with patch("app.api.agent._agent_graph", graph):
            resp = await client.post(
                "/api/agent/internal/chat/stream", json={"message": "故障"}
            )
        events = _parse_events(resp.text)
        assert events[-1]["type"] == "error"
        assert events[-1]["message"] == "系统内部错误"

    @pytest.mark.asyncio
    async def test_empty_result_returns_default_done(self, client):
        graph = _FakeGraph(events=[])
        with patch("app.api.agent._agent_graph", graph):
            resp = await client.post(
                "/api/agent/internal/chat/stream", json={"message": "空结果"}
            )
        events = _parse_events(resp.text)
        assert events[-1]["type"] == "done"
        assert "未找到相关信息" in events[-1]["answer"]


class TestCustomerChatStream:
    @pytest.mark.asyncio
    async def test_customer_stream_parses_events(self, client):
        graph = _FakeGraph(events=[_token_event("客服"), _done_event("客服回答")])
        with patch("app.api.agent._customer_graph", graph):
            resp = await client.post(
                "/api/agent/customer/chat/stream", json={"message": "咨询"}
            )
        events = _parse_events(resp.text)
        assert [e["type"] for e in events] == ["token", "done"]
        assert events[-1]["answer"] == "客服回答"

    @pytest.mark.asyncio
    async def test_customer_stream_error_event(self, client):
        graph = _FakeGraph(raise_on_stream=True)
        with patch("app.api.agent._customer_graph", graph):
            resp = await client.post(
                "/api/agent/customer/chat/stream", json={"message": "故障"}
            )
        events = _parse_events(resp.text)
        assert events[-1]["type"] == "error"
