"""retrieve + tools + context 节点 测试 (TDD: RED)"""

from unittest.mock import AsyncMock, patch

import pytest


class TestRetrieveNode:
    @pytest.mark.asyncio
    async def test_retrieve_node_populates_docs(self):
        from app.agents.nodes.retrieve import retrieve_node
        from app.agents.state import create_initial_state
        from app.retrieval.fusion import FusionResult

        state = create_initial_state("t1", "考勤制度查询")
        state["rewritten_query"] = "考勤制度查询"
        state["user_scopes"] = ["public", "internal"]

        mock_docs = [
            FusionResult(unique_id="1_0", doc_id=1, chunk_index=0, content="考勤说明", fused_score=0.9, scope="public"),
            FusionResult(unique_id="2_0", doc_id=2, chunk_index=0, content="请假流程", fused_score=0.7, scope="public"),
        ]

        with patch("app.agents.nodes.retrieve.hybrid_retrieve", new=AsyncMock(return_value=mock_docs)):
            with patch("app.agents.nodes.retrieve.rerank", new=AsyncMock(return_value=mock_docs)):
                result = await retrieve_node(state)
                assert len(result["retrieved_docs"]) > 0

    @pytest.mark.asyncio
    async def test_retrieve_node_empty_query(self):
        from app.agents.nodes.retrieve import retrieve_node
        from app.agents.state import create_initial_state

        state = create_initial_state("t2", "")
        result = await retrieve_node(state)
        assert result["retrieved_docs"] == []


class TestToolsNode:
    @pytest.mark.asyncio
    async def test_tool_decision_no_tools_needed(self):
        from app.agents.nodes.tools import tool_decision_node
        from app.agents.state import create_initial_state

        state = create_initial_state("t3", "考勤制度")
        result = await tool_decision_node(state)
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_tool_decision_preserves_state(self):
        from app.agents.nodes.tools import tool_decision_node
        from app.agents.state import create_initial_state

        state = create_initial_state("t4", "简单问题")
        result = await tool_decision_node(state)
        assert result["original_query"] == "简单问题"


class TestContextNode:
    def test_assemble_context_appends_docs(self):
        from app.agents.nodes.context import assemble_context
        from app.agents.state import create_initial_state
        from app.retrieval.fusion import FusionResult

        state = create_initial_state("t5", "考勤制度")
        state["retrieved_docs"] = [
            FusionResult(unique_id="1_0", doc_id=1, chunk_index=0, content="考勤：每日9点前打卡", fused_score=0.9, scope="public", metadata={"title": "考勤手册"}),
            FusionResult(unique_id="2_0", doc_id=2, chunk_index=0, content="请假：OA系统提交", fused_score=0.7, scope="public", metadata={"title": "请假指南"}),
        ]

        result = assemble_context(state)
        assert len(result["context"]) > 0
        assert "考勤" in result["context"]
        assert "请假" in result["context"]

    def test_assemble_context_empty_docs(self):
        from app.agents.nodes.context import assemble_context
        from app.agents.state import create_initial_state

        state = create_initial_state("t6", "测试")
        result = assemble_context(state)
        assert result["context"] == ""

    def test_assemble_context_token_limit(self):
        from app.agents.nodes.context import assemble_context
        from app.agents.state import create_initial_state
        from app.retrieval.fusion import FusionResult

        state = create_initial_state("t7", "长文档查询")
        long_content = "测试内容" * 500
        state["retrieved_docs"] = [
            FusionResult(unique_id="1_0", doc_id=1, chunk_index=0, content=long_content, fused_score=0.9, scope="public", metadata={"title": "长文档"}),
        ]

        result = assemble_context(state)
        assert len(result["context"]) > 0
        assert len(result["context"]) < 10000

    def test_format_doc_with_citation(self):
        from app.agents.nodes.context import _format_doc
        from app.retrieval.fusion import FusionResult
        doc = FusionResult(unique_id="1_0", doc_id=1, chunk_index=0, content="考勤制度", fused_score=0.9, scope="public", metadata={"title": "考勤手册"})
        formatted = _format_doc(doc, index=1, image_ids=[])
        assert "考勤制度" in formatted
        assert "[文档1]" in formatted
        assert "来源" not in formatted

    def test_format_doc_with_images(self):
        from app.agents.nodes.context import _format_doc
        from app.retrieval.fusion import FusionResult
        doc = FusionResult(unique_id="1_0", doc_id=1, chunk_index=0, content="配图内容", fused_score=0.9, scope="public", metadata={"title": "含图手册"})
        formatted = _format_doc(doc, index=2, image_ids=[1, 3])
        assert "考勤" not in formatted
        assert "[文档2]" in formatted
        assert "[图1]" in formatted
        assert "[图3]" in formatted



class TestCitationNode:
    def test_citation_node_basic(self):
        from app.agents.nodes.citation import citation_node
        from app.retrieval.fusion import FusionResult

        state: dict = {
            "final_answer": "根据[1]和[2]的记载，考勤制度如下。",
            "retrieved_docs": [
                FusionResult(unique_id="1_0", doc_id=1, chunk_index=0, content="考勤制度", fused_score=0.9, scope="public", metadata={"title": "考勤手册", "source_type": "internal"}),
                FusionResult(unique_id="2_0", doc_id=2, chunk_index=0, content="请假流程", fused_score=0.7, scope="public", metadata={"title": "请假指南", "source_type": "internal"}),
            ],
            "context_doc_indices": [0, 1],
        }

        result = citation_node(state)
        citations = result["citations"]
        assert len(citations) == 2
        assert citations[0]["index"] == 1
        assert citations[0]["title"] == "考勤手册"
        assert citations[0]["is_internal"] is True
        assert citations[1]["index"] == 2
        assert citations[1]["title"] == "请假指南"

    def test_citation_node_empty_answer(self):
        from app.agents.nodes.citation import citation_node

        state: dict = {
            "final_answer": "",
            "retrieved_docs": [],
            "context_doc_indices": [],
        }

        result = citation_node(state)
        assert result["citations"] == []

    def test_citation_node_filters_invalid_markers(self):
        from app.agents.nodes.citation import citation_node
        from app.retrieval.fusion import FusionResult

        state: dict = {
            "final_answer": "参考[1]和[5]的说明。",
            "retrieved_docs": [
                FusionResult(unique_id="1_0", doc_id=1, chunk_index=0, content="考勤制度", fused_score=0.9, scope="public", metadata={"title": "考勤手册", "source_type": "internal"}),
                FusionResult(unique_id="2_0", doc_id=2, chunk_index=0, content="请假流程", fused_score=0.7, scope="public", metadata={"title": "请假指南", "source_type": "internal"}),
            ],
            "context_doc_indices": [0],  # only doc 0, marker [5] should be ignored
        }

        result = citation_node(state)
        citations = result["citations"]
        assert len(citations) == 1
        assert citations[0]["index"] == 1

    def test_citation_node_external_source(self):
        from app.agents.nodes.citation import citation_node
        from app.retrieval.fusion import FusionResult

        state: dict = {
            "final_answer": "根据[1]可知。",
            "retrieved_docs": [
                FusionResult(unique_id="1_0", doc_id=1, chunk_index=0, content="公众号文章内容", fused_score=0.9, scope="public", metadata={
                    "title": "微信文章标题",
                    "source_type": "wechat",
                    "source_name": "公司公众号",
                    "original_url": "https://mp.weixin.qq.com/s/test",
                }),
            ],
            "context_doc_indices": [0],
        }

        result = citation_node(state)
        citations = result["citations"]
        assert len(citations) == 1
        assert citations[0]["platform"] == "wechat"
        assert citations[0]["source_name"] == "公司公众号"
        assert citations[0]["url"] == "https://mp.weixin.qq.com/s/test"
        assert citations[0]["is_internal"] is False

    def test_citation_node_no_markers_in_answer(self):
        from app.agents.nodes.citation import citation_node
        from app.retrieval.fusion import FusionResult

        state: dict = {
            "final_answer": "这是一个没有引用标记的回答。",
            "retrieved_docs": [
                FusionResult(unique_id="1_0", doc_id=1, chunk_index=0, content="考勤制度", fused_score=0.9, scope="public", metadata={"title": "考勤手册", "source_type": "internal"}),
            ],
            "context_doc_indices": [0],
        }

        result = citation_node(state)
        assert result["citations"] == []

    def test_citation_node_sorted_by_index(self):
        from app.agents.nodes.citation import citation_node
        from app.retrieval.fusion import FusionResult

        state: dict = {
            "final_answer": "先看[3]，再看[1]，最后[2]。",
            "retrieved_docs": [
                FusionResult(unique_id="1_0", doc_id=1, chunk_index=0, content="A", fused_score=0.9, scope="public", metadata={"title": "文档A", "source_type": "internal"}),
                FusionResult(unique_id="2_0", doc_id=2, chunk_index=0, content="B", fused_score=0.8, scope="public", metadata={"title": "文档B", "source_type": "internal"}),
                FusionResult(unique_id="3_0", doc_id=3, chunk_index=0, content="C", fused_score=0.7, scope="public", metadata={"title": "文档C", "source_type": "internal"}),
            ],
            "context_doc_indices": [0, 1, 2],
        }

        result = citation_node(state)
        citations = result["citations"]
        assert len(citations) == 3
        assert [c["index"] for c in citations] == [1, 2, 3]
