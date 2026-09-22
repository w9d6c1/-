"""FAQ + 词库 + 反馈 测试 (TDD: RED)"""

import pytest
from httpx import AsyncClient




# ===================== FAQ =====================

@pytest.mark.asyncio
async def test_create_faq_returns_201(client: AsyncClient, token_factory):
    token = await token_factory("faquser")
    resp = await client.post(
        "/api/admin/faqs",
        json={"category_id": 1, "question": "如何重置密码？", "answer": "请访问设置页面"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["question"] == "如何重置密码？"
    assert data["status"] == "draft"
    assert data["version"] == 1


@pytest.mark.asyncio
async def test_list_faqs_returns_items(client: AsyncClient, token_factory):
    token = await token_factory("faquser2")
    await client.post(
        "/api/admin/faqs",
        json={"category_id": 1, "question": "Q1", "answer": "A1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    await client.post(
        "/api/admin/faqs",
        json={"category_id": 1, "question": "Q2", "answer": "A2"},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp = await client.get(
        "/api/admin/faqs", headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) >= 2


@pytest.mark.asyncio
async def test_update_faq_status(client: AsyncClient, token_factory):
    token = await token_factory("faquser3", "dept_admin")
    resp = await client.post(
        "/api/admin/faqs",
        json={"category_id": 1, "question": "待上线FAQ", "answer": "答案"},
        headers={"Authorization": f"Bearer {token}"},
    )
    faq_id = resp.json()["id"]

    # 必须通过审核才能上线（直接 PUT status=online 将被拦截）
    await client.post(f"/api/admin/faqs/{faq_id}/submit", headers={"Authorization": f"Bearer {token}"})
    resp = await client.post(f"/api/admin/faqs/{faq_id}/approve", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "online"


@pytest.mark.asyncio
async def test_bulk_import_faqs(client: AsyncClient, token_factory):
    token = await token_factory("faquser4")
    resp = await client.post(
        "/api/admin/faqs/bulk",
        json={
            "items": [
                {"category_id": 1, "question": "批量Q1", "answer": "A1"},
                {"category_id": 1, "question": "批量Q2", "answer": "A2", "tags": ["常见问题"]},
            ]
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    assert resp.json()["imported"] == 2


@pytest.mark.asyncio
async def test_delete_faq(client: AsyncClient, token_factory):
    token = await token_factory("faquser5")
    resp = await client.post(
        "/api/admin/faqs",
        json={"category_id": 1, "question": "待删除", "answer": "答案"},
        headers={"Authorization": f"Bearer {token}"},
    )
    faq_id = resp.json()["id"]

    resp = await client.delete(
        f"/api/admin/faqs/{faq_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204


# ===================== FAQ 单条 + 编辑增强 =====================

@pytest.mark.asyncio
async def test_get_faq_by_id(client: AsyncClient, token_factory):
    token = await token_factory("faqget1")
    resp = await client.post(
        "/api/admin/faqs",
        json={"category_id": 1, "question": "获取单条测试", "answer": "获取单条答案", "scope": "public"},
        headers={"Authorization": f"Bearer {token}"},
    )
    faq_id = resp.json()["id"]

    resp = await client.get(f"/api/admin/faqs/{faq_id}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["question"] == "获取单条测试"
    assert resp.json()["scope"] == "public"


@pytest.mark.asyncio
async def test_get_faq_404(client: AsyncClient, token_factory):
    token = await token_factory("faqget2")
    resp = await client.get("/api/admin/faqs/99999", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_faq_scope(client: AsyncClient, token_factory):
    token = await token_factory("faqscope")
    resp = await client.post(
        "/api/admin/faqs",
        json={"category_id": 1, "question": "scope测试", "answer": "scope答案", "scope": "public"},
        headers={"Authorization": f"Bearer {token}"},
    )
    faq_id = resp.json()["id"]

    resp = await client.put(
        f"/api/admin/faqs/{faq_id}",
        json={"scope": "internal"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["scope"] == "internal"


# ===================== 同义词 =====================

@pytest.mark.asyncio
async def test_create_synonym(client: AsyncClient, token_factory):
    token = await token_factory("synuser")
    resp = await client.post(
        "/api/admin/synonyms",
        json={"word": "密码", "synonyms": ["口令", "passcode"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    assert resp.json()["word"] == "密码"


@pytest.mark.asyncio
async def test_list_synonyms(client: AsyncClient, token_factory):
    token = await token_factory("synuser2")
    await client.post(
        "/api/admin/synonyms",
        json={"word": "账号", "synonyms": ["账户", "ID"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp = await client.get(
        "/api/admin/synonyms", headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_delete_synonym(client: AsyncClient, token_factory):
    token = await token_factory("syndel")
    resp = await client.post(
        "/api/admin/synonyms",
        json={"word": "待删词", "synonyms": ["会被删"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    syn_id = resp.json()["id"]
    resp = await client.delete(f"/api/admin/synonyms/{syn_id}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 204


# ===================== 敏感词 =====================

@pytest.mark.asyncio
async def test_create_sensitive_word(client: AsyncClient, token_factory):
    token = await token_factory("swuser")
    resp = await client.post(
        "/api/admin/sensitive-words",
        json={"word": "违禁词示例", "word_type": "forbid"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_list_sensitive_words(client: AsyncClient, token_factory):
    token = await token_factory("swuser2")
    await client.post(
        "/api/admin/sensitive-words",
        json={"word": "敏感词A", "word_type": "sensitive"},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp = await client.get(
        "/api/admin/sensitive-words", headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


@pytest.mark.asyncio
async def test_delete_sensitive_word(client: AsyncClient, token_factory):
    token = await token_factory("swdel")
    resp = await client.post(
        "/api/admin/sensitive-words",
        json={"word": "待删敏感词", "word_type": "sensitive"},
        headers={"Authorization": f"Bearer {token}"},
    )
    sw_id = resp.json()["id"]
    resp = await client.delete(f"/api/admin/sensitive-words/{sw_id}", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 204


# ===================== 反馈 =====================

@pytest.mark.asyncio
async def test_submit_feedback(client: AsyncClient, token_factory):
    token = await token_factory("fbuser")
    resp = await client.post(
        "/api/admin/feedbacks",
        json={"thread_id": "thr_001", "rating": "like", "suggestion": "很好"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_submit_unanswered(client: AsyncClient, token_factory):
    token = await token_factory("uauser")
    resp = await client.post(
        "/api/admin/unanswered",
        json={"thread_id": "thr_002", "question": "你们支持API接入吗？", "source": "customer"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
