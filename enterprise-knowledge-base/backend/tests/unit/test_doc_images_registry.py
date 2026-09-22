"""检索图片注册表与引用附图测试"""

import pytest
from unittest.mock import patch

from app.agents.nodes.citation import citation_node, insert_missing_image_markers
from app.retrieval.doc_images import build_image_registry
from app.retrieval.fusion import FusionResult


def _doc(doc_id: int, content: str = "内容", score: float = 0.8) -> FusionResult:
    return FusionResult(
        unique_id=f"{doc_id}_0",
        doc_id=doc_id,
        chunk_index=0,
        content=content,
        fused_score=score,
        scope="public",
        metadata={"title": f"文档{doc_id}", "source_type": "wechat", "original_url": "https://x.com"},
    )


class TestBuildImageRegistry:
    @pytest.mark.asyncio
    async def test_assigns_global_ids_in_doc_order(self):
        docs = [_doc(10), _doc(20)]
        images_by_doc = {
            10: [{"id": 1, "seq": 1, "url": "/api/public/images/1.jpg", "object_name": "x"}],
            20: [
                {"id": 2, "seq": 1, "url": "/api/public/images/2.jpg", "object_name": "y"},
                {"id": 3, "seq": 2, "url": "/api/public/images/3.jpg", "object_name": "z"},
            ],
        }
        with patch("app.retrieval.doc_images.load_images_for_docs", return_value=images_by_doc):
            registry = await build_image_registry(docs)

        assert [img["id"] for img in registry] == [1, 2, 3]
        assert registry[0]["doc_index"] == 1
        assert registry[1]["doc_index"] == 2
        assert registry[2]["doc_index"] == 2
        assert registry[2]["url"] == "/api/public/images/3.jpg"

    @pytest.mark.asyncio
    async def test_empty_docs_returns_empty(self):
        assert await build_image_registry([]) == []

    @pytest.mark.asyncio
    async def test_load_failure_returns_empty(self):
        with patch("app.retrieval.doc_images.load_images_for_docs", side_effect=Exception("boom")):
            assert await build_image_registry([_doc(1)]) == []


class TestCitationImages:
    def _state(self, answer: str, image_ids_by_doc: dict[int, list[int]]):
        doc_images = []
        for doc_index, ids in image_ids_by_doc.items():
            for i in ids:
                doc_images.append(
                    {"id": i, "doc_index": doc_index, "url": f"/api/public/images/{i}.jpg", "object_name": "x"}
                )
        return {
            "final_answer": answer,
            "retrieved_docs": [_doc(1, "A"), _doc(2, "B")],
            "context_doc_indices": [0, 1],
            "doc_images": doc_images,
        }

    def test_citation_attaches_images_for_matching_doc(self):
        state = self._state("根据[1]内容。", {1: [1, 2], 2: [3]})
        result = citation_node(state)
        citations = result["citations"]
        assert len(citations) == 1
        assert citations[0]["index"] == 1
        assert [img["id"] for img in citations[0]["images"]] == [1, 2]

    def test_citation_without_images_has_empty_list(self):
        state = self._state("根据[2]内容。", {1: [1, 2]})
        result = citation_node(state)
        assert result["citations"][0]["images"] == []

    def test_citation_node_auto_inserts_marker_when_missing(self):
        state = self._state("根据[1]内容。", {1: [1, 2], 2: [3]})
        result = citation_node(state)
        assert "[图1]" in result["final_answer"]
        # 插在 [1] 所在行行尾
        assert result["final_answer"].endswith("\n[图1]")

    def test_citation_node_keeps_existing_markers(self):
        state = self._state("根据[1]内容。\n[图2]", {1: [1, 2], 2: [3]})
        result = citation_node(state)
        assert "[图2]" in result["final_answer"]
        assert "[图1]" not in result["final_answer"]


class TestInsertMissingImageMarkers:
    def test_inserts_after_citation_line(self):
        imgs = {1: [{"id": 1}, {"id": 2}]}
        answer = insert_missing_image_markers("原理如下。\n详见[1]说明。", imgs, {1})
        assert "[图1]" in answer
        assert answer.endswith("\n[图1]")

    def test_no_change_when_marker_already_present(self):
        imgs = {1: [{"id": 1}]}
        answer = insert_missing_image_markers("见[图1]。\n详见[1]说明。", imgs, {1})
        assert answer == "见[图1]。\n详见[1]说明。"

    def test_no_change_when_cited_doc_has_no_images(self):
        answer = insert_missing_image_markers("详见[1]说明。", {}, {1})
        assert answer == "详见[1]说明。"

    def test_caps_at_three_insertions(self):
        imgs = {n: [{"id": n}] for n in range(1, 6)}
        answer = insert_missing_image_markers("参见[1][2][3][4][5]。", imgs, {1, 2, 3, 4, 5})
        assert answer.count("[图") == 3

    def test_one_image_per_doc(self):
        imgs = {1: [{"id": 1}, {"id": 2}, {"id": 3}]}
        answer = insert_missing_image_markers("详见[1]说明。", imgs, {1})
        assert answer.count("[图") == 1
