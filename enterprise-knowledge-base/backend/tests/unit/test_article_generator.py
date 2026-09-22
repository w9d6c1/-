"""单元测试 — 文章生成引擎"""

from unittest.mock import AsyncMock, patch

import pytest

from app.articles.generator import (
    DEFAULT_ANGLES,
    _count_words,
    _extract_image_placements,
    _truncate_content,
    generate_batch,
    generate_single_article,
    plan_angles,
    retrieve_knowledge,
)

# ── 容器内跳过：路径解析依赖宿主仓库根目录 ──
from pathlib import Path as _Path
_PROJECT = _Path(__file__).resolve().parent.parent.parent.parent
pytestmark = pytest.mark.skipif(
    not (_PROJECT / "backend" / "app").exists(),
    reason=f"需从宿主仓库根目录运行（{_PROJECT}/backend/app 不存在）",
)


class TestRetrieveKnowledge:
    @pytest.mark.asyncio
    async def test_retrieve_per_angle(self):
        """验证对每个角度分别检索"""
        angles = DEFAULT_ANGLES[:2]

        async def fake_retrieve(query, scope="public", top_k=8):
            return [type("R", (), {"content": f"result for {query}", "doc_id": 1, "chunk_index": 0, "fused_score": 0.9})]

        with patch("app.articles.generator.hybrid_retrieve", side_effect=fake_retrieve):
            results = await retrieve_knowledge(angles)
            assert len(results) == 2
            assert "technical_detail" in results
            assert "case_study" in results

    @pytest.mark.asyncio
    async def test_retrieve_handles_failure(self):
        """检索失败时返回空列表，不中断流程"""
        angles = DEFAULT_ANGLES[:1]

        async def fake_retrieve_fail(query, scope="public", top_k=8):
            raise RuntimeError("ES down")

        with patch("app.articles.generator.hybrid_retrieve", side_effect=fake_retrieve_fail):
            results = await retrieve_knowledge(angles)
            assert results["technical_detail"] == []


class TestPlanAngles:
    @pytest.mark.asyncio
    async def test_returns_default_angles_on_llm_failure(self):
        """LLM 调用失败时退回默认角度"""
        with patch("app.articles.generator.call_llm_with_retry", side_effect=RuntimeError("LLM down")):
            angles = await plan_angles("地下室防水", count=3)
            assert len(angles) == 3
            for a in angles:
                assert "key" in a
                assert "label" in a

    @pytest.mark.asyncio
    async def test_parses_llm_json_response(self):
        """正确解析 LLM 返回的 JSON 角度数组"""
        fake_response = '''```json
[
    {"key": "tech", "label": "技术解析", "retrieval_query": "电渗透原理", "tone": "professional", "target_audience": "工程师"},
    {"key": "case", "label": "案例分析", "retrieval_query": "施工案例", "tone": "case_story", "target_audience": "业主"}
]
```'''
        with patch("app.articles.generator.call_llm_with_retry", new_callable=AsyncMock, return_value=fake_response):
            angles = await plan_angles("地下室防水", count=2)
            assert len(angles) == 2
            assert angles[0]["key"] == "tech"
            assert angles[1]["label"] == "案例分析"


class TestGenerateSingleArticle:
    @pytest.mark.asyncio
    async def test_generates_title_and_content(self):
        """生成文章包含标题和正文"""
        fake_title = "电渗透防潮技术深度解析"
        fake_content = "## 技术原理\n\n电渗透防潮技术是一种..." + "详细内容" * 50

        call_count = [0]

        async def fake_llm(llm, messages, max_retries=3, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return fake_title
            return fake_content

        angle = DEFAULT_ANGLES[0]
        with patch("app.articles.generator.call_llm_with_retry", side_effect=fake_llm):
            result = await generate_single_article(
                topic="电渗透防潮",
                angle=angle,
                retrieved_context=[],
            )
            assert result["title"] == fake_title
            assert result["content"] == fake_content
            assert result["angle"] == "technical_detail"
            assert result["word_count"] > 0

    @pytest.mark.asyncio
    async def test_fallback_title_on_error(self):
        """标题生成失败时使用默认标题（正文仍正常生成）"""
        call_count = [0]

        async def fake_llm(llm, messages, max_retries=3, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:  # 标题生成失败
                raise RuntimeError("LLM timeout")
            return "## 正文\n\n电渗透防潮是一种..." + "内容" * 50

        angle = DEFAULT_ANGLES[0]
        with patch("app.articles.generator.call_llm_with_retry", side_effect=fake_llm):
            result = await generate_single_article(
                topic="电渗透防潮",
                angle=angle,
                retrieved_context=[],
            )
            assert "电渗透防潮" in result["title"]
            assert "技术原理解析" in result["title"]
            assert result["word_count"] > 0

    @pytest.mark.asyncio
    async def test_word_count_within_range_skips_repair(self):
        """字数在目标区间内时不触发扩写修复（仅标题+正文两次调用）"""
        calls = []

        async def fake_llm(llm, messages, max_retries=3, **kwargs):
            calls.append(1)
            if len(calls) == 1:
                return "达标标题"
            return "达标正文内容充实专业。" * 150  # 1650 字，位于 1200-3000

        angle = DEFAULT_ANGLES[0]
        with patch("app.articles.generator.call_llm_with_retry", side_effect=fake_llm):
            result = await generate_single_article(
                topic="电渗透防潮",
                angle=angle,
                retrieved_context=[],
            )
            assert 1200 <= result["word_count"] <= 3000
            assert len(calls) == 2

    @pytest.mark.asyncio
    async def test_word_count_repair_enriches_short_content(self):
        """字数不足时自动调用扩写修复，最终字数达标"""
        calls = []

        async def fake_llm(llm, messages, max_retries=3, **kwargs):
            calls.append(1)
            if len(calls) == 1:
                return "短标题"
            if len(calls) == 2:
                return "短正文" * 100  # 400 字 < 1200，触发修复
            return "扩写后的完整正文，内容丰富详实。" * 120  # >= 1200

        angle = DEFAULT_ANGLES[0]
        with patch("app.articles.generator.call_llm_with_retry", side_effect=fake_llm):
            result = await generate_single_article(
                topic="电渗透防潮",
                angle=angle,
                retrieved_context=[],
            )
            assert result["word_count"] >= 1200
            assert len(calls) == 3

    @pytest.mark.asyncio
    async def test_word_count_truncates_overflow(self):
        """字数严重超限时截断到 max_words 内"""
        calls = []

        async def fake_llm(llm, messages, max_retries=3, **kwargs):
            calls.append(1)
            if len(calls) == 1:
                return "标题"
            return "超长正文内容。" * 300  # 2100 字 > 1500 上限

        angle = DEFAULT_ANGLES[0]
        with patch("app.articles.generator.call_llm_with_retry", side_effect=fake_llm):
            result = await generate_single_article(
                topic="电渗透防潮",
                angle=angle,
                retrieved_context=[],
                min_words=1000,
                max_words=1500,
            )
            assert result["word_count"] <= 1500


class TestGenerateBatch:
    @pytest.mark.asyncio
    async def test_generates_correct_count(self):
        """批量生成返回指定数量的文章"""
        fake_article = {
            "title": "测试文章",
            "content": "正文内容" * 50,
            "word_count": 200,
            "angle": "technical_detail",
        }

        with patch("app.articles.generator.retrieve_knowledge", new_callable=AsyncMock, return_value={"technical_detail": []}):
            with patch("app.articles.generator.plan_angles", new_callable=AsyncMock, return_value=DEFAULT_ANGLES[:2]):
                with patch("app.articles.generator.generate_single_article", new_callable=AsyncMock, return_value=fake_article):
                    articles = await generate_batch("测试主题", article_count=2)
                    assert len(articles) == 2
                    for a in articles:
                        assert a["title"] == "测试文章"
                        assert a["content"] == "正文内容" * 50

    @pytest.mark.asyncio
    async def test_handles_partial_failure(self):
        """单篇失败不影响其他文章"""
        fail_angle = DEFAULT_ANGLES[0]

        async def fake_generate(topic, angle, retrieved_context, photo_descriptions="", **kwargs):
            if angle["key"] == fail_angle["key"]:
                raise RuntimeError("生成失败")
            return {"title": f"{angle['label']}文章", "content": "正文", "word_count": 100, "angle": angle["key"]}

        with patch("app.articles.generator.retrieve_knowledge", new_callable=AsyncMock, return_value={"technical_detail": [], "case_study": []}):
            with patch("app.articles.generator.plan_angles", new_callable=AsyncMock, return_value=DEFAULT_ANGLES[:2]):
                with patch("app.articles.generator.generate_single_article", side_effect=fake_generate):
                    articles = await generate_batch("测试主题", article_count=2)
                    assert len(articles) == 2
                    # 第一篇是失败标记
                    assert "生成失败" in articles[0]["content"]
                    # 第二篇是正常的
                    assert articles[1]["word_count"] == 100

    @pytest.mark.asyncio
    async def test_re_retrieves_for_planned_angles(self):
        """规划角度后按最终角度补检索，保证知识上下文不为空（回归）"""
        planned = [{
            "key": "dealer_angle",
            "label": "招商角度",
            "retrieval_query": "经销商招商检索词",
            "tone": "persuasive",
            "target_audience": "经销商",
        }]
        fake_article = {
            "title": "招商文章",
            "content": "正文内容" * 50,
            "word_count": 200,
            "angle": "dealer_angle",
        }
        retrieve_calls: list[list[str]] = []

        async def fake_retrieve(angles, scope="public", top_k=8):
            retrieve_calls.append([a["key"] for a in angles])
            return {"dealer_angle": [type("R", (), {"content": "经销商知识", "doc_id": 1, "chunk_index": 0, "fused_score": 0.9})]}

        with (
            patch("app.articles.generator.retrieve_knowledge", side_effect=fake_retrieve),
            patch("app.articles.generator.plan_angles", new_callable=AsyncMock, return_value=planned),
            patch("app.articles.generator.generate_single_article", new_callable=AsyncMock, return_value=fake_article) as mock_gen,
        ):
            articles = await generate_batch("招商政策", article_count=1, account_type="dealer")
            assert len(articles) == 1
            # 第二次检索应针对规划后的角度
            assert len(retrieve_calls) == 2
            assert "dealer_angle" in retrieve_calls[-1]
            ctx_arg = mock_gen.call_args.kwargs["retrieved_context"]
            assert len(ctx_arg) == 1


class TestPostProcess:
    def test_count_words_strips_markers_and_whitespace(self):
        text = "第一段内容。\n\n[IMAGE: 照片1: 配图建议: 施工细节]\n\n第二段内容。"
        assert _count_words(text) == 12

    def test_count_words_empty(self):
        assert _count_words("") == 0
        assert _count_words("   \n  ") == 0

    def test_truncate_content_limits_length(self):
        content = "测试段落内容足够长。" * 300  # 3600 字
        out = _truncate_content(content, 1200)
        assert len(out) <= 1200
        assert out.endswith("。")

    def test_truncate_drops_unclosed_marker(self):
        content = "正文" * 600 + "[IMAGE: 照片1: 配图建议: 被截断的描述"
        out = _truncate_content(content, 1200)
        assert "[IMAGE:" not in out

    def test_extract_image_placements_numbered_mapping(self):
        names = ["a.jpg", "b.jpg"]
        content = (
            "第一段。[IMAGE: 照片2: 配图建议: 电极细节]\n\n"
            "第二段。[IMAGE: 照片1: 配图建议: 主机全貌]\n\n"
            "第三段。[IMAGE: 配图建议: 旧格式无编号]"
        )
        placements = _extract_image_placements(content, names)
        assert placements[0]["object_name"] == "b.jpg"
        assert placements[0]["caption"] == "电极细节"
        assert placements[1]["object_name"] == "a.jpg"
        assert placements[1]["caption"] == "主机全貌"
        # 旧格式按出现顺序回退分配
        assert placements[2]["object_name"] == "a.jpg"
        assert placements[2]["caption"] == "旧格式无编号"

    def test_extract_image_placements_out_of_range_number(self):
        names = ["a.jpg"]
        content = "[IMAGE: 照片9: 配图建议: 越界编号]"
        placements = _extract_image_placements(content, names)
        assert placements[0]["object_name"] is None
        assert placements[0]["caption"] == "越界编号"

    def test_extract_image_placements_no_photos(self):
        placements = _extract_image_placements("[IMAGE: 配图建议: 无照片]", [])
        assert placements[0]["object_name"] is None
