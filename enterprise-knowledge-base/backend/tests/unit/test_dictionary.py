"""词库管理 测试 — 同义词 + 敏感词 + 批量导入 + 缓存刷新"""

import csv
import io

import pytest
from httpx import AsyncClient


# ── 同义词 ──

@pytest.mark.asyncio
async def test_create_synonym(client: AsyncClient, token_factory):
    token = await token_factory("syn1")
    resp = await client.post(
        "/api/admin/synonyms",
        json={"word": "加班", "synonyms": ["超时工作", "OT"], "scope": "public"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["word"] == "加班"
    assert data["synonyms"] == ["超时工作", "OT"]


@pytest.mark.asyncio
async def test_list_synonyms_paginated(client: AsyncClient, token_factory):
    token = await token_factory("syn2")
    resp = await client.get(
        "/api/admin/synonyms",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert "page" in data


@pytest.mark.asyncio
async def test_delete_synonym(client: AsyncClient, token_factory):
    token = await token_factory("syn3")
    resp = await client.post(
        "/api/admin/synonyms",
        json={"word": "待删", "synonyms": ["删除测试"], "scope": "public"},
        headers={"Authorization": f"Bearer {token}"},
    )
    syn_id = resp.json()["id"]

    resp = await client.delete(
        f"/api/admin/synonyms/{syn_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204

    resp = await client.get(
        "/api/admin/synonyms", headers={"Authorization": f"Bearer {token}"},
    )
    data = resp.json()
    assert not any(s["id"] == syn_id for s in data["items"])


@pytest.mark.asyncio
async def test_update_synonym(client: AsyncClient, token_factory):
    token = await token_factory("syn4")
    resp = await client.post(
        "/api/admin/synonyms",
        json={"word": "原词", "synonyms": ["旧同义"], "scope": "public"},
        headers={"Authorization": f"Bearer {token}"},
    )
    syn_id = resp.json()["id"]

    resp = await client.put(
        f"/api/admin/synonyms/{syn_id}",
        json={"word": "新词", "synonyms": ["新同义1", "新同义2"]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["word"] == "新词"
    assert data["synonyms"] == ["新同义1", "新同义2"]


@pytest.mark.asyncio
async def test_cache_invalidated_on_synonym_create(client: AsyncClient, token_factory):
    token = await token_factory("syn5")
    resp = await client.post(
        "/api/admin/synonyms",
        json={"word": "缓存测试", "synonyms": ["cache"], "scope": "public"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_readonly_cannot_create_synonym(client: AsyncClient, token_factory):
    token = await token_factory("syn_ro", "readonly")
    resp = await client.post(
        "/api/admin/synonyms",
        json={"word": "无权限", "synonyms": ["no"], "scope": "public"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


# ── 敏感词 ──

@pytest.mark.asyncio
async def test_create_sensitive_word(client: AsyncClient, token_factory):
    token = await token_factory("sw1")
    resp = await client.post(
        "/api/admin/sensitive-words",
        json={"word": "测试敏感", "word_type": "sensitive"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["word"] == "测试敏感"
    assert data["word_type"] == "sensitive"


@pytest.mark.asyncio
async def test_create_forbid_word(client: AsyncClient, token_factory):
    token = await token_factory("sw2")
    resp = await client.post(
        "/api/admin/sensitive-words",
        json={"word": "禁答测试", "word_type": "forbid"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["word_type"] == "forbid"


@pytest.mark.asyncio
async def test_list_sensitive_words_paginated(client: AsyncClient, token_factory):
    token = await token_factory("sw3")
    resp = await client.get(
        "/api/admin/sensitive-words",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data


@pytest.mark.asyncio
async def test_delete_sensitive_word(client: AsyncClient, token_factory):
    token = await token_factory("sw4")
    resp = await client.post(
        "/api/admin/sensitive-words",
        json={"word": "待删敏感", "word_type": "sensitive"},
        headers={"Authorization": f"Bearer {token}"},
    )
    sw_id = resp.json()["id"]

    resp = await client.delete(
        f"/api/admin/sensitive-words/{sw_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_cache_invalidated_on_sensitive_word_create(client: AsyncClient, token_factory):
    token = await token_factory("sw5")
    resp = await client.post(
        "/api/admin/sensitive-words",
        json={"word": "缓存敏感", "word_type": "sensitive"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_readonly_cannot_create_sensitive_word(client: AsyncClient, token_factory):
    token = await token_factory("sw_ro", "readonly")
    resp = await client.post(
        "/api/admin/sensitive-words",
        json={"word": "无权限敏感", "word_type": "sensitive"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


# ── 批量导入 ──

@pytest.mark.asyncio
async def test_import_synonyms_csv(client: AsyncClient, token_factory):
    token = await token_factory("import1")
    csv_content = "word,synonyms,scope\n导入词A,同义1,同义2,public\n导入词B,同义3,internal\n"
    resp = await client.post(
        "/api/admin/synonyms/import",
        files={"file": ("synonyms.csv", csv_content.encode("utf-8"), "text/csv")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["imported"] == 2


@pytest.mark.asyncio
async def test_import_sensitive_words_csv(client: AsyncClient, token_factory):
    token = await token_factory("import2")
    csv_content = "word,word_type\n导入禁答词,forbid\n导入敏感词,sensitive\n"
    resp = await client.post(
        "/api/admin/sensitive-words/import",
        files={"file": ("words.csv", csv_content.encode("utf-8"), "text/csv")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["imported"] >= 2


@pytest.mark.asyncio
async def test_import_rejects_non_csv(client: AsyncClient, token_factory):
    token = await token_factory("import3")
    resp = await client.post(
        "/api/admin/synonyms/import",
        files={"file": ("bad.txt", b"not csv", "text/plain")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400


# ── 缓存刷新验证 ──

@pytest.mark.asyncio
async def test_reload_after_delete_leaves_clean_state(client: AsyncClient, token_factory):
    from app.agents.nodes.validate import load_blocked_patterns

    token = await token_factory("reload1")
    resp = await client.post(
        "/api/admin/sensitive-words",
        json={"word": "测试刷新", "word_type": "forbid"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 201
    sw_id = resp.json()["id"]

    blocked_before = load_blocked_patterns()
    assert "测试刷新" in blocked_before

    await client.delete(
        f"/api/admin/sensitive-words/{sw_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    blocked_after = load_blocked_patterns()
    assert "测试刷新" not in blocked_after
