"""单元测试 — 写作模板按目标账号类型分流"""

import pytest

from app.articles.models import WritingTemplate
from app.articles.template_service import (
    ACCOUNT_PRESET_TEMPLATES,
    ACCOUNT_TYPES,
    TemplateService,
)


class TestPresetSeeding:
    @pytest.mark.asyncio
    async def test_seed_creates_account_type_presets(self, db_session):
        svc = TemplateService(db_session)
        await svc.seed_presets()

        for account_type in ACCOUNT_TYPES:
            ids = await svc.resolve_account_template_ids(account_type)
            assert len(ids) == len(ACCOUNT_PRESET_TEMPLATES[account_type]), account_type

    @pytest.mark.asyncio
    async def test_seed_is_idempotent(self, db_session):
        svc = TemplateService(db_session)
        await svc.seed_presets()
        first_ids = await svc.resolve_account_template_ids("dealer")
        await svc.seed_presets()
        second_ids = await svc.resolve_account_template_ids("dealer")
        assert first_ids == second_ids

    @pytest.mark.asyncio
    async def test_seed_does_not_overwrite_custom(self, db_session):
        svc = TemplateService(db_session)
        await svc.seed_presets()
        custom = await svc.create_template(1, "我的自定义", "style", "自定义指令")
        await svc.seed_presets()
        assert await db_session.get(WritingTemplate, custom.id) is not None


class TestListByAccountType:
    @pytest.mark.asyncio
    async def test_list_includes_type_presets(self, db_session):
        svc = TemplateService(db_session)
        await svc.seed_presets()
        templates = await svc.list_templates_by_account_type("user", 0)
        names = {t.name for t in templates}
        assert "选购指南型（用户）" in names
        assert "通俗易懂（用户）" in names

    @pytest.mark.asyncio
    async def test_list_excludes_other_type_presets(self, db_session):
        svc = TemplateService(db_session)
        await svc.seed_presets()
        templates = await svc.list_templates_by_account_type("user", 0)
        names = {t.name for t in templates}
        assert "招商政策解读型（经销商）" not in names
        assert "技术原理解析型（设计师）" not in names
        # 通用预设保留
        assert "问题解决型" in names


class TestResolveTemplateIds:
    @pytest.mark.asyncio
    async def test_resolve_empty_before_seed(self, db_session):
        svc = TemplateService(db_session)
        assert await svc.resolve_account_template_ids("designer") == []
