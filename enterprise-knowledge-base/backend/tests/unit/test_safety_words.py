"""安全词库加载测试 (TDD: RED — 禁答词 + 敏感词从 DB 加载)"""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_load_forbid_words_from_db(client, db_session, token_factory):
    """从 DB 加载 forbid 类型禁答词"""
    from app.agents.nodes.validate import load_words_from_db

    token = await token_factory("safety1", "superadmin")
    await client.post(
        "/api/admin/sensitive-words",
        json={"word": "政治敏感词测试", "word_type": "forbid"},
        headers={"Authorization": f"Bearer {token}"},
    )
    await client.post(
        "/api/admin/sensitive-words",
        json={"word": "违禁商品", "word_type": "forbid"},
        headers={"Authorization": f"Bearer {token}"},
    )
    await client.post(
        "/api/admin/sensitive-words",
        json={"word": "内部敏感信息", "word_type": "sensitive"},
        headers={"Authorization": f"Bearer {token}"},
    )

    result = await load_words_from_db(db_session)

    assert len(result["forbid"]) == 2
    assert "政治敏感词测试" in result["forbid"]
    assert "违禁商品" in result["forbid"]
    assert len(result["sensitive"]) == 1
    assert "内部敏感信息" in result["sensitive"]


@pytest.mark.asyncio
async def test_load_forbid_words_empty_db(client, db_session):
    """空 DB 时返回空列表"""
    from app.agents.nodes.validate import load_words_from_db

    result = await load_words_from_db(db_session)

    assert result["forbid"] == []
    assert result["sensitive"] == []


@pytest.mark.asyncio
async def test_validate_node_blocks_forbid_word():
    """validate_input_node 拦截包含禁答词的输入"""
    from app.agents.nodes.validate import update_blocked_patterns, validate_input_node
    from app.agents.state import create_initial_state

    update_blocked_patterns(["政治敏感词测试", "违禁商品"])

    state = create_initial_state(thread_id="t1", query="请问政治敏感词测试是什么？")
    result = validate_input_node(state)

    assert result["is_blocked"] is True
    assert "政治敏感词测试" in result["block_reason"]
    assert result["route"] == "reject"


@pytest.mark.asyncio
async def test_validate_node_allows_safe_content():
    """正常内容不被拦截"""
    from app.agents.nodes.validate import update_blocked_patterns, validate_input_node
    from app.agents.state import create_initial_state

    update_blocked_patterns(["违禁词"])

    state = create_initial_state(thread_id="t2", query="如何查询考勤记录？")
    result = validate_input_node(state)

    assert result["is_blocked"] is False


@pytest.mark.asyncio
async def test_output_node_filters_sensitive_words():
    """validate_output_node 过滤敏感词并脱敏"""
    from app.agents.nodes.output import update_sensitive_patterns, validate_output_node
    from app.agents.state import create_initial_state

    update_sensitive_patterns(["内部机密", "身份证号"])

    state = create_initial_state(thread_id="t3", query="测试")
    state["final_answer"] = "根据内部机密文件显示，您的身份证号是110101199001011234"
    result = validate_output_node(state)

    assert "内部机密" not in result["final_answer"]
    assert "身份证号" not in result["final_answer"]
    assert "***" in result["final_answer"]


@pytest.mark.asyncio
async def test_output_node_no_sensitive_words():
    """无敏感词时直接输出"""
    from app.agents.nodes.output import update_sensitive_patterns, validate_output_node
    from app.agents.state import create_initial_state

    update_sensitive_patterns(["机密"])

    state = create_initial_state(thread_id="t4", query="测试")
    state["final_answer"] = "这是一个正常的回答内容"
    result = validate_output_node(state)

    assert result["final_answer"] == "这是一个正常的回答内容"


@pytest.mark.asyncio
async def test_update_patterns_empty_does_not_break():
    """空列表更新不会报错"""
    from app.agents.nodes.validate import update_blocked_patterns, validate_input_node
    from app.agents.nodes.output import update_sensitive_patterns, validate_output_node
    from app.agents.state import create_initial_state

    update_blocked_patterns([])
    update_sensitive_patterns([])

    state = create_initial_state(thread_id="t5", query="正常问题")
    result = validate_input_node(state)
    assert result["is_blocked"] is False

    state["final_answer"] = "正常回答"
    result2 = validate_output_node(state)
    assert result2["final_answer"] == "正常回答"
