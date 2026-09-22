"""单元测试 — 短视频文案模块（热点/推荐/脚本/素材）"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.copywriting import hot_douyin
from app.copywriting.hot_manual import ManualHotService
from app.copywriting.material_service import MaterialService, _ext
from app.copywriting.recommend import recommend_copy_titles
from app.copywriting.script_service import ScriptService, build_script_body, parse_storyboard


def _mock_client(resp: MagicMock | None = None, get_side_effect=None):
    """构造支持 async with 的 httpx 客户端 mock。"""
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    if get_side_effect is not None:
        client.get = AsyncMock(side_effect=get_side_effect)
    else:
        client.get = AsyncMock(return_value=resp)
    return client


# ============================================================
# 抖音热搜
# ============================================================

class TestDouyinHot:
    @pytest.fixture(autouse=True)
    def _clear_cache(self):
        hot_douyin._cache = None
        yield
        hot_douyin._cache = None

    @pytest.mark.asyncio
    async def test_parses_word_list_with_links(self):
        payload = {
            "status_code": 0,
            "data": {
                "word_list": [
                    {
                        "word": "上海房价", "hot_value": 12124241, "group_id": "123",
                        "word_cover": {"url_list": ["https://img1/x.jpeg"]},
                    },
                    {"word": "", "hot_value": 1, "group_id": "456"},
                    {"word": "台风路径", "hot_value": 100, "group_id": None},
                ]
            },
        }
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(return_value=payload)
        client = _mock_client(resp=resp)
        with patch(
            "app.copywriting.hot_douyin.httpx.AsyncClient",
            return_value=client,
        ):
            items = await hot_douyin.fetch_douyin_hot()
            assert len(items) == 2
            assert items[0]["title"] == "上海房价"
            assert items[0]["url"] == "https://www.douyin.com/search/%E4%B8%8A%E6%B5%B7%E6%88%BF%E4%BB%B7"
            assert items[0]["cover"] == "https://img1/x.jpeg"
            assert items[1]["url"] == "https://www.douyin.com/search/%E5%8F%B0%E9%A3%8E%E8%B7%AF%E5%BE%84"
            assert items[1]["cover"] == ""

    @pytest.mark.asyncio
    async def test_failure_returns_cached(self):
        hot_douyin._cache = (0.0, [{"rank": 1, "title": "旧", "hot_value": 1, "url": ""}])
        client = _mock_client(get_side_effect=RuntimeError("network down"))
        with patch(
            "app.copywriting.hot_douyin.httpx.AsyncClient",
            return_value=client,
        ):
            items = await hot_douyin.fetch_douyin_hot()
            assert items[0]["title"] == "旧"

    @pytest.mark.asyncio
    async def test_empty_on_fresh_failure(self):
        client = _mock_client(get_side_effect=RuntimeError("network down"))
        with patch(
            "app.copywriting.hot_douyin.httpx.AsyncClient",
            return_value=client,
        ):
            assert await hot_douyin.fetch_douyin_hot() == []


# ============================================================
# 文案标题推荐
# ============================================================

class TestRecommend:
    @pytest.mark.asyncio
    async def test_returns_recommendations(self, db_session):
        hot_items = [
            {"rank": 1, "title": "热点A", "url": "https://www.douyin.com/video/1"},
            {"rank": 2, "title": "热点B", "url": "https://www.douyin.com/video/2"},
        ]
        fake_llm = '''[
          {"title": "装修前必看的5个避坑细节", "hot_word": "热点A", "hot_url": "https://www.douyin.com/video/1", "reason": "借装修热点切入防潮知识"},
          {"title": "地下室防潮干货", "hot_word": "热点B", "hot_url": "https://www.douyin.com/video/2", "reason": "结合热点引流"}
        ]'''
        with (
            patch(
                "app.copywriting.recommend.call_llm_with_retry",
                new_callable=AsyncMock, return_value=fake_llm,
            ),
            patch(
                "app.copywriting.recommend.build_knowledge_digest",
                new_callable=AsyncMock, return_value="知识库标题示例",
            ),
        ):
            recs = await recommend_copy_titles(db_session, hot_items, count=5)
            assert len(recs) == 2
            assert recs[0]["title"] == "装修前必看的5个避坑细节"
            assert recs[0]["hot_url"] == "https://www.douyin.com/video/1"
            assert recs[0]["hot_word"] == "热点A"

    @pytest.mark.asyncio
    async def test_empty_hot_returns_empty(self, db_session):
        assert await recommend_copy_titles(db_session, [], count=3) == []

    @pytest.mark.asyncio
    async def test_llm_failure_returns_empty(self, db_session):
        hot_items = [{"rank": 1, "title": "热点A", "url": ""}]
        with (
            patch(
                "app.copywriting.recommend.call_llm_with_retry",
                side_effect=RuntimeError("LLM down"),
            ),
            patch(
                "app.copywriting.recommend.build_knowledge_digest",
                new_callable=AsyncMock, return_value="",
            ),
        ):
            assert await recommend_copy_titles(db_session, hot_items, count=3) == []


# ============================================================
# 脚本生成
# ============================================================

class TestScript:
    @pytest.mark.asyncio
    async def test_parse_voiceover_and_storyboard(self):
        fake = '''{"voiceover": "大家好啊，今天聊聊地下室防潮。", "storyboard": "1|开场镜头|大家好啊|3"}'''
        with (
            patch(
                "app.copywriting.script_service.hybrid_retrieve",
                new_callable=AsyncMock, return_value=[],
            ),
            patch(
                "app.copywriting.script_service.call_llm_with_retry",
                new_callable=AsyncMock, return_value=fake,
            ),
        ):
            svc = ScriptService.__new__(ScriptService)
            result = await svc.generate_script(
                user_id=1, title="地下室防潮", hot_word="热点A"
            )
            assert "地下室防潮" in result["voiceover"]
            assert "开场镜头" in result["storyboard"]
            assert result["user_id"] == 1

    @pytest.mark.asyncio
    async def test_fallback_parse_on_bad_json(self):
        raw = "1|镜头A|台词A|3\n大家好，这是一段口播"
        svc = ScriptService.__new__(ScriptService)
        voiceover, storyboard = svc._parse_script(raw, "标题")
        assert "大家好" in voiceover
        assert "镜头A" in storyboard

    def test_normalize_storyboard_list(self):
        """LLM 返回 dict 列表型分镜头 → 规范为行格式"""
        svc = ScriptService.__new__(ScriptService)
        storyboard = [
            {"镜头": 1, "画面描述": "开场", "台词口播": "大家好", "时长秒": 3},
            {"镜头": 2, "画面描述": "细节", "台词口播": "看这里", "时长秒": 4},
        ]
        out = svc._normalize_storyboard(storyboard)
        assert out is not None
        assert "1|开场|大家好|3" in out
        assert "2|细节|看这里|4" in out

    def test_parse_empty_fallback_title(self):
        svc = ScriptService.__new__(ScriptService)
        voiceover, _ = svc._parse_script("", "标题X")
        assert "标题X" in voiceover

    def test_parse_storyboard_lines(self):
        shots = parse_storyboard("1|开场|大家好|3\n2|细节|看这里|4")
        assert len(shots) == 2
        assert shots[0]["scene"] == "开场"
        assert shots[1]["dur"] == "4"
        assert parse_storyboard("") == []

    def test_build_script_body_table(self):
        from app.copywriting.models import VideoScript

        script = VideoScript(
            title="标题", hot_word="热点A", hot_url="https://x",
            voiceover="口播内容", storyboard="1|开场|大家好|3",
            requirement="30秒竖屏", material_notes="素材说明",
        )
        body = build_script_body(script, table=True)
        assert "口播稿" in body
        assert "| 1 | 开场 | 大家好 | 3 |" in body
        assert "热点A" in body

    def test_build_script_body_plain(self):
        from app.copywriting.models import VideoScript

        script = VideoScript(
            title="标题", voiceover="口播内容", storyboard="1|开场|大家好|3",
        )
        body = build_script_body(script, table=False)
        assert "镜头 1：画面：开场" in body
        assert "台词：大家好" in body

    def test_build_script_pdf(self):
        pytest.importorskip("reportlab")
        from app.copywriting.models import VideoScript
        from app.copywriting.script_service import build_script_pdf

        script = VideoScript(
            title="PDF测试", hot_word="热点", hot_url="https://x",
            voiceover="口播内容", storyboard="1|开场|大家好|3\n2|细节|看这里|4",
        )
        data = build_script_pdf(script)
        assert data[:5] == b"%PDF-"
        assert len(data) > 500

    @pytest.mark.asyncio
    async def test_create_update_get_delete(self, db_session):
        svc = ScriptService(db_session)
        obj = await svc.create_script({
            "user_id": 7,
            "title": "测试脚本",
            "hot_word": "热点",
            "hot_url": "https://x",
            "voiceover": "口播",
            "storyboard": "1|画面|台词|3",
        })
        assert obj.id > 0
        got = await svc.get_script(obj.id)
        assert got.title == "测试脚本"
        updated = await svc.update_script(obj.id, {"voiceover": "新口播"})
        assert updated.voiceover == "新口播"
        assert await svc.delete_script(obj.id, 7) is True
        assert await svc.get_script(obj.id) is None


# ============================================================
# 手动热榜
# ============================================================

class TestManualHot:
    @pytest.mark.asyncio
    async def test_crud(self, db_session):
        svc = ManualHotService(db_session)
        obj = await svc.create_item(3, "馋妈妈热点", "https://chanmama.com/1", source="chanmama", sort_order=1)
        items = await svc.list_items(user_id=3)
        assert len(items) == 1
        assert items[0].title == "馋妈妈热点"
        assert await svc.delete_item(obj.id, 3) is True
        assert await svc.list_items(user_id=3) == []

    @pytest.mark.asyncio
    async def test_clear_all(self, db_session):
        svc = ManualHotService(db_session)
        await svc.create_item(5, "A", None)
        await svc.create_item(5, "B", None)
        assert await svc.clear_all(5) == 2
        assert await svc.list_items(user_id=5) == []


# ============================================================
# 素材
# ============================================================

class TestMaterial:
    def test_ext_detection(self):
        assert _ext("a.jpg") == ".jpg"
        assert _ext("b.txt") == ".txt"
        assert _ext("c.mp4") == ".mp4"
        assert _ext("noext") == ""

    @pytest.mark.asyncio
    async def test_upload_text_file(self, db_session):
        svc = MaterialService(db_session)
        with patch(
            "app.copywriting.material_service.upload_file",
            new=MagicMock(return_value=None),
        ):
            result = await svc.upload_file(
                "note.txt", "今天要拍地下室的防水施工".encode("utf-8"), "text/plain", 1
            )
        assert result["ok"] is True
        assert result["type"] == "text"
        assert "防水施工" in result["description"]

    @pytest.mark.asyncio
    async def test_upload_video_not_analyzed(self, db_session):
        svc = MaterialService(db_session)
        with patch(
            "app.copywriting.material_service.upload_file",
            new=MagicMock(return_value=None),
        ):
            result = await svc.upload_file(
                "clip.mp4", b"fakevideo", "video/mp4", 1
            )
        assert result["type"] == "video"
        assert "暂不读取画面" in result["description"]

    @pytest.mark.asyncio
    async def test_upload_photo_without_vision(self, db_session):
        svc = MaterialService(db_session)
        with (
            patch(
                "app.copywriting.material_service.upload_file",
                new=MagicMock(return_value=None),
            ),
            patch(
                "app.copywriting.material_service.get_vision_provider",
                new=MagicMock(return_value=None),
            ),
        ):
            result = await svc.upload_file(
                "photo.jpg", b"fakeimage", "image/jpeg", 1
            )
        assert result["type"] == "photo"
        assert "未配置视觉模型" in result["description"]

    def test_summarize_skips_failed(self):
        entries = [
            {"ok": True, "type": "text", "filename": "a.txt", "description": "内容A"},
            {"ok": False, "type": "other", "filename": "b.bin", "description": "失败"},
        ]
        notes = MaterialService.summarize(entries)
        assert "内容A" in notes
        assert "b.bin" not in notes
