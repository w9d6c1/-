"""FAQ 向量加载测试 (TDD: RED — 先写测试确保失败)"""

import pytest
from httpx import AsyncClient




@pytest.mark.asyncio
async def test_load_online_faqs_only_returns_online(client: AsyncClient, db_session, token_factory):
    """只有审核通过的 FAQ 被加载"""
    from app.services.faq_service import load_online_faqs

    admin_token = await token_factory("faqload1", "dept_admin")
    resp = await client.post(
        "/api/admin/faqs",
        json={"category_id": 1, "question": "如何退货？", "answer": "联系客服办理退货"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    faq_id = resp.json()["id"]
    await client.post(f"/api/admin/faqs/{faq_id}/submit", headers={"Authorization": f"Bearer {admin_token}"})
    await client.post(f"/api/admin/faqs/{faq_id}/approve", headers={"Authorization": f"Bearer {admin_token}"})

    op_token = await token_factory("faqload1_op", "operator")
    await client.post(
        "/api/admin/faqs",
        json={"category_id": 1, "question": "草稿问题", "answer": "草稿答案"},
        headers={"Authorization": f"Bearer {op_token}"},
    )

    faqs = await load_online_faqs(db_session)
    assert len(faqs) == 1
    assert faqs[0]["question"] == "如何退货？"


@pytest.mark.asyncio
async def test_load_online_faqs_filters_by_scope(client: AsyncClient, db_session, token_factory):
    """按 scope 过滤 FAQ"""
    from app.services.faq_service import load_online_faqs

    token = await token_factory("faqload2", "dept_admin")
    resp = await client.post(
        "/api/admin/faqs",
        json={"category_id": 1, "question": "公共问题", "answer": "公共答案", "scope": "public"},
        headers={"Authorization": f"Bearer {token}"},
    )
    faq_id = resp.json()["id"]
    await client.post(f"/api/admin/faqs/{faq_id}/submit", headers={"Authorization": f"Bearer {token}"})
    await client.post(f"/api/admin/faqs/{faq_id}/approve", headers={"Authorization": f"Bearer {token}"})

    resp = await client.post(
        "/api/admin/faqs",
        json={"category_id": 1, "question": "内部问题", "answer": "内部答案", "scope": "internal"},
        headers={"Authorization": f"Bearer {token}"},
    )
    faq_id2 = resp.json()["id"]
    await client.post(f"/api/admin/faqs/{faq_id2}/submit", headers={"Authorization": f"Bearer {token}"})
    await client.post(f"/api/admin/faqs/{faq_id2}/approve", headers={"Authorization": f"Bearer {token}"})

    faqs = await load_online_faqs(db_session, scopes=["public"])
    assert len(faqs) == 1
    assert faqs[0]["question"] == "公共问题"

    faqs_all = await load_online_faqs(db_session, scopes=["public", "internal"])
    assert len(faqs_all) == 2


@pytest.mark.asyncio
async def test_load_online_faqs_includes_similar_questions(client: AsyncClient, db_session, token_factory):
    """FAQ 的相似问题也被加载用于向量化"""
    from app.services.faq_service import load_online_faqs

    token = await token_factory("faqload3", "dept_admin")
    resp = await client.post(
        "/api/admin/faqs",
        json={
            "category_id": 1,
            "question": "退货流程",
            "answer": "请先申请退货单",
            "similar_questions": ["如何退货", "退货步骤", "退换货"],
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    faq_id = resp.json()["id"]
    await client.post(f"/api/admin/faqs/{faq_id}/submit", headers={"Authorization": f"Bearer {token}"})
    await client.post(f"/api/admin/faqs/{faq_id}/approve", headers={"Authorization": f"Bearer {token}"})

    faqs = await load_online_faqs(db_session)
    assert len(faqs) == 1
    assert len(faqs[0]["questions_for_embedding"]) == 4  # 问题 + 3 个相似问题


@pytest.mark.asyncio
async def test_faq_vectors_loaded_with_mock_embedding():
    """FAQ_VECTORS 通过加载函数填充（mock embedding）"""
    from unittest.mock import AsyncMock, patch
    from app.agents.nodes.faq import _set_faq_vectors, _clear_faq_vectors

    test_faqs = [
        {
            "id": 1,
            "question": "测试问题A",
            "answer": "测试答案A",
            "scope": "public",
            "questions_for_embedding": ["测试问题A", "相似问题A1"],
        },
        {
            "id": 2,
            "question": "测试问题B",
            "answer": "测试答案B",
            "scope": "internal",
            "questions_for_embedding": ["测试问题B"],
        },
    ]

    with patch("app.agents.nodes.faq.embed_texts", new=AsyncMock(side_effect=lambda texts: [[0.1] * 1024 for _ in texts])):
        await _set_faq_vectors(test_faqs, scopes=["public"])

    from app.agents.nodes.faq import FAQ_VECTORS

    assert len(FAQ_VECTORS) == 2  # 2 questions for embedding in public scope
    assert FAQ_VECTORS[0]["content"] == "测试答案A"
    assert FAQ_VECTORS[0]["scope"] == "public"
    assert FAQ_VECTORS[0]["faq_id"] == 1

    await _clear_faq_vectors()


@pytest.mark.asyncio
async def test_faq_match_node_hits_when_vectors_populated():
    """FAQ_VECTORS 有数据时 faq_match_node 能命中"""
    from unittest.mock import AsyncMock, patch
    from app.agents.nodes.faq import _set_faq_vectors, _clear_faq_vectors, faq_match_node
    from app.agents.state import create_initial_state

    test_faqs = [
        {
            "id": 1,
            "question": "退货问题",
            "answer": "请联系客服退货",
            "scope": "public",
            "questions_for_embedding": ["退货问题", "如何退货"],
        },
    ]

    with patch("app.agents.nodes.faq.embed_texts", new=AsyncMock(side_effect=lambda texts: [[0.1] * 1024 for _ in texts])):
        await _set_faq_vectors(test_faqs, scopes=["public"])

        with patch("app.agents.nodes.faq.embed_query", new=AsyncMock(return_value=[0.1] * 1024)):
            state = create_initial_state(thread_id="test_1", query="如何退货", user_scopes=["public"])
            result = await faq_match_node(state)

        assert result["faq_hit"] is True
        assert result["faq_answer"] == "请联系客服退货"
        assert result["route"] == "faq_answer"

    await _clear_faq_vectors()


@pytest.mark.asyncio
async def test_faq_match_node_no_match_different_query():
    """FAQ_VECTORS 有数据但问题不匹配时返回 faq_hit=False"""
    from unittest.mock import AsyncMock, patch
    from app.agents.nodes.faq import _set_faq_vectors, _clear_faq_vectors, faq_match_node
    from app.agents.state import create_initial_state

    test_faqs = [
        {
            "id": 1,
            "question": "退货问题",
            "answer": "请联系客服退货",
            "scope": "public",
            "questions_for_embedding": ["退货问题"],
        },
    ]

    with patch("app.agents.nodes.faq.embed_texts", new=AsyncMock(side_effect=lambda texts: [[0.1] * 1024 for _ in texts])):
        await _set_faq_vectors(test_faqs, scopes=["public"])

        # 返回不相似的向量
        with patch("app.agents.nodes.faq.embed_query", new=AsyncMock(return_value=[-0.5] * 1024)):
            state = create_initial_state(thread_id="test_2", query="完全不相关的问题")
            result = await faq_match_node(state)

            assert result["faq_hit"] is False

    await _clear_faq_vectors()


@pytest.mark.asyncio
async def test_faq_match_node_empty_vectors_no_error():
    """FAQ_VECTORS 为空时不报错"""
    from app.agents.nodes.faq import _clear_faq_vectors, faq_match_node
    from app.agents.state import create_initial_state

    await _clear_faq_vectors()

    state = create_initial_state(thread_id="test_3", query="任何问题")
    result = await faq_match_node(state)

    assert result["faq_hit"] is False
