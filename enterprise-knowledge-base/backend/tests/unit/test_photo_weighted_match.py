"""单元测试 — 照片权重匹配（LLM 语义分 + 规则权重）"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.articles.models import Photo
from app.articles.photo_service import PhotoService


def _make_photo(
    tags: list[str],
    created_at: datetime | None = None,
    description: str = "",
) -> Photo:
    return Photo(
        object_name="photo-library/x.jpg",
        filename="x.jpg",
        tags=tags,
        description=description or "标签场景照片",
        file_size=0,
        content_type="image/jpeg",
        user_id=1,
        created_at=created_at or datetime.now(),
    )


async def _seed_photo(db, tags, created_at=None):
    photo = _make_photo(tags, created_at)
    db.add(photo)
    await db.commit()
    await db.refresh(photo)
    return photo


class TestScoringHelpers:
    def test_tag_keyword_score_coverage(self):
        svc = PhotoService.__new__(PhotoService)  # 绕过 __init__
        score = svc._tag_keyword_score(
            ["地下室", "电渗透", "注浆"], ["地下室", "电渗透"]
        )
        assert score == pytest.approx(2 / 3, abs=0.001)

    def test_tag_keyword_score_no_keywords(self):
        svc = PhotoService.__new__(PhotoService)
        assert svc._tag_keyword_score([], ["地下室"]) == 0.5

    def test_tag_keyword_score_partial_match(self):
        svc = PhotoService.__new__(PhotoService)
        score = svc._tag_keyword_score(["电极"], ["电渗透电极"])
        assert score == 1.0  # 关键词被标签包含即命中

    def test_freshness_score_decays(self):
        svc = PhotoService.__new__(PhotoService)
        now = datetime.now()
        assert svc._freshness_score(now, now) == 1.0
        old = now - timedelta(days=180)
        assert svc._freshness_score(old, now) == 0.0
        assert svc._freshness_score(None, now) == 0.5

    def test_anti_reuse_score(self):
        svc = PhotoService.__new__(PhotoService)
        assert svc._anti_reuse_score(None, 30) == 1.0
        recent = datetime.now() - timedelta(days=3)
        assert svc._anti_reuse_score(recent, 30) == pytest.approx(0.1)


class TestMatchWeighted:
    @pytest.mark.asyncio
    async def test_combines_llm_and_rule_scores(self, db_session):
        p1 = await _seed_photo(db_session, ["地下室", "电渗透"], datetime.now())
        p2 = await _seed_photo(
            db_session, ["办公室", "办公家具"], datetime.now() - timedelta(days=200)
        )
        svc = PhotoService(db_session)

        with (
            patch.object(
                PhotoService, "_llm_extract_keywords",
                new=AsyncMock(return_value=["地下室", "电渗透"]),
            ),
            patch.object(
                PhotoService, "_llm_semantic_scores",
                new=AsyncMock(return_value={
                    p1.id: 0.9,
                    p2.id: 0.1,
                    "__reason__": {p1.id: "相关", p2.id: "无关"},
                }),
            ),
        ):
            result = await svc.match_photos_weighted("地下室电渗透施工", count=2)
            assert len(result) == 2
            # p1 主题贴合 → 综合分应显著高于 p2
            assert result[0]["photo_id"] == p1.id
            assert result[0]["confidence"] > result[1]["confidence"]
            assert "weights" in result[0]
            assert result[0]["reason"]

    @pytest.mark.asyncio
    async def test_llm_failure_degrades_to_rule_only(self, db_session):
        p1 = await _seed_photo(db_session, ["地下室", "电渗透"])
        svc = PhotoService(db_session)

        with patch(
            "app.articles.photo_service.call_llm_with_retry",
            side_effect=RuntimeError("LLM down"),
        ):
            result = await svc.match_photos_weighted("地下室", count=1)
            assert len(result) == 1
            assert result[0]["photo_id"] == p1.id
            # 语义分降级为标签分，仍可产出
            assert result[0]["confidence"] > 0

    @pytest.mark.asyncio
    async def test_no_photos_returns_empty(self, db_session):
        svc = PhotoService(db_session)
        result = await svc.match_photos_weighted("地下室", count=3)
        assert result == []

    @pytest.mark.asyncio
    async def test_keywords_passed_to_semantic_prompt(self, db_session):
        p1 = await _seed_photo(db_session, ["地下室"])
        svc = PhotoService(db_session)

        captured: dict = {}

        async def fake_semantic(self, topic, template, photo_map):
            captured["template"] = template
            return {p1.id: 0.8}

        with (
            patch.object(
                PhotoService, "_llm_extract_keywords",
                new=AsyncMock(return_value=["地下室"]),
            ),
            patch.object(PhotoService, "_llm_semantic_scores", new=fake_semantic),
        ):
            await svc.match_photos_weighted(
                "地下室", template_instruction="按招商政策解读结构组织", count=1
            )
            assert "招商政策解读" in captured["template"]
