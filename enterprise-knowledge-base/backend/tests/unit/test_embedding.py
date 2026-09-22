"""Embedding 模型封装测试"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.embedding import (
    create_embed_config,
    get_embedding_dimension,
)


@pytest.fixture(autouse=True)
def _reset_siliconflow_cache():
    import app.agents.embedding as emb_module

    emb_module._SILICONFLOW_OK = None
    emb_module._SILICONFLOW_CHECK_AT = 0.0
    yield
    emb_module._SILICONFLOW_OK = None
    emb_module._SILICONFLOW_CHECK_AT = 0.0


def _ok_http_resp(payload: dict) -> MagicMock:
    """构造同步的 httpx-like 响应 mock：raise_for_status/json 都是普通方法。"""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value=payload)
    return resp


def _sf_client(payload: dict, get_payload: dict | None = None) -> MagicMock:
    """构造 SiliconFlow 客户端 mock：post/get 为可 await 的 AsyncMock。"""
    client = MagicMock()
    client.post = AsyncMock(return_value=_ok_http_resp(payload))
    client.get = AsyncMock(return_value=_ok_http_resp(get_payload or {"data": []}))
    return client


def test_embed_config_from_settings():
    cfg = create_embed_config()
    assert cfg.model.endswith("bge-large-zh-v1.5")
    assert cfg.device == "cpu"
    assert isinstance(cfg.model, str)


def test_embed_config_has_dataclass_attrs():
    cfg = create_embed_config()
    assert hasattr(cfg, "model")
    assert hasattr(cfg, "device")


def test_get_embedding_dimension():
    dim = get_embedding_dimension()
    assert dim == 1024
    assert isinstance(dim, int)


async def test_embed_texts_shape():
    import app.agents.embedding as emb_module

    payload = {
        "data": [
            {"index": 0, "embedding": [0.1] * 1024},
            {"index": 1, "embedding": [0.2] * 1024},
            {"index": 2, "embedding": [0.3] * 1024},
        ]
    }

    with patch.object(emb_module, "_get_siliconflow_client", return_value=_sf_client(payload)):
        with patch.object(emb_module.settings, "siliconflow_api_key", "test-key"):
            with patch.object(emb_module, "_siliconflow_availability", return_value=True):
                vectors = await emb_module.embed_texts(["文本1", "文本2", "文本3"])
                assert len(vectors) == 3
                assert len(vectors[0]) == 1024


async def test_embed_query_shape():
    import app.agents.embedding as emb_module

    payload = {"data": [{"index": 0, "embedding": [0.5] * 1024}]}

    with patch.object(emb_module, "_get_siliconflow_client", return_value=_sf_client(payload)):
        with patch.object(emb_module.settings, "siliconflow_api_key", "test-key"):
            with patch.object(emb_module, "_siliconflow_availability", return_value=True):
                vector = await emb_module.embed_query("测试查询")
                assert len(vector) == 1024


async def test_embed_empty_list():
    vectors = await __import__("app.agents.embedding", fromlist=["embed_texts"]).embed_texts([])
    assert vectors == []


async def test_embed_faq_query():
    import app.agents.embedding as emb_module

    payload = {"data": [{"index": 0, "embedding": [0.3] * 1024}]}

    with patch.object(emb_module, "_get_siliconflow_client", return_value=_sf_client(payload)):
        with patch.object(emb_module.settings, "siliconflow_api_key", "test-key"):
            with patch.object(emb_module, "_siliconflow_availability", return_value=True):
                vector = await emb_module.embed_faq_query("FAQ查询")
                assert len(vector) == 1024


async def test_embed_faq_texts():
    import app.agents.embedding as emb_module

    payload = {"data": [{"index": 0, "embedding": [0.1] * 1024}]}

    with patch.object(emb_module, "_get_siliconflow_client", return_value=_sf_client(payload)):
        with patch.object(emb_module.settings, "siliconflow_api_key", "test-key"):
            with patch.object(emb_module, "_siliconflow_availability", return_value=True):
                vectors = await emb_module.embed_faq_texts(["FAQ文本"])
                assert len(vectors) == 1
                assert len(vectors[0]) == 1024


async def test_local_fallback_on_api_failure():
    import app.agents.embedding as emb_module

    mock_client = MagicMock()
    mock_client.post = AsyncMock(side_effect=Exception("API unavailable"))

    mock_model = MagicMock()
    mock_model.encode.return_value = __import__("numpy").array([[0.1] * 1024])

    with patch.object(emb_module, "_get_siliconflow_client", return_value=mock_client):
        with patch.object(emb_module, "_get_local_model", new=AsyncMock(return_value=mock_model)):
            with patch.object(emb_module.settings, "siliconflow_api_key", "test-key"):
                with patch.object(emb_module, "_siliconflow_availability", return_value=True):
                    vectors = await emb_module.embed_texts(["fallback"])
                    assert len(vectors) == 1
                    assert len(vectors[0]) == 1024


async def test_embed_uses_cached_availability_skips_precheck():
    """可用性已缓存为 True 时，不再 GET /models 预检，直接走 API。"""
    import app.agents.embedding as emb_module

    mock_client = _sf_client({"data": [{"index": 0, "embedding": [0.1] * 1024}]})

    with patch.object(emb_module, "_get_siliconflow_client", return_value=mock_client):
        with patch.object(emb_module.settings, "siliconflow_api_key", "test-key"):
            with patch.object(emb_module, "_siliconflow_availability", return_value=True):
                await emb_module.embed_texts(["缓存命中"])

    mock_client.get.assert_not_awaited()
    mock_client.post.assert_awaited_once()


async def test_embed_prechecks_and_caches_on_first_use():
    """首次调用做预检并缓存结果，随后的调用复用缓存。"""
    import app.agents.embedding as emb_module

    mock_client = _sf_client({"data": [{"index": 0, "embedding": [0.2] * 1024}]})

    availability_calls: list = []

    def fake_availability():
        availability_calls.append(1)
        # 首次返回 None（触发预检），预检成功后应返回缓存结论
        return None if len(availability_calls) == 1 else True

    with patch.object(emb_module, "_get_siliconflow_client", return_value=mock_client):
        with patch.object(emb_module.settings, "siliconflow_api_key", "test-key"):
            with patch.object(emb_module, "_siliconflow_availability", new=MagicMock(side_effect=fake_availability)) as avail:
                with patch.object(emb_module, "_remember_siliconflow_availability", new=MagicMock()) as remember:
                    vectors = await emb_module.embed_texts(["预检"])
                    assert len(vectors) == 1
                    assert avail.call_count == 1
                    remember.assert_called_once_with(True)


async def test_precheck_cache_remember_and_expire():
    """预检结论按 TTL 记忆与失效。"""
    import app.agents.embedding as emb_module

    emb_module._SILICONFLOW_OK = None
    emb_module._SILICONFLOW_CHECK_AT = 0.0
    assert emb_module._siliconflow_availability() is None

    emb_module._remember_siliconflow_availability(True)
    assert emb_module._siliconflow_availability() is True

    emb_module._remember_siliconflow_availability(False)
    assert emb_module._siliconflow_availability() is False

    # 把检查时间推到很久以前 → 缓存过期，重新预检
    emb_module._SILICONFLOW_CHECK_AT = 0.0
    assert emb_module._siliconflow_availability() is None
