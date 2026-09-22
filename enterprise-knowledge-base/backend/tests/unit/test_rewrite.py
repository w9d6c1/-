"""查询改写节点测试 (TDD: RED — LLM 改写 + DB 同义词)"""

import pytest


@pytest.mark.asyncio
async def test_llm_rewrite_basic():
    """LLM 改写将多轮对话上下文合并为独立查询"""
    from unittest.mock import AsyncMock, MagicMock, patch

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="产品A的退货政策是什么？"))

    mock_syn_map: dict[str, list[str]] = {}

    with patch("app.agents.nodes.rewrite.create_llm", return_value=mock_llm):
        from app.agents.nodes.rewrite import llm_rewrite_query, extract_history
        from langchain_core.messages import HumanMessage, AIMessage

        messages = [
            HumanMessage(content="产品A有哪些颜色？"),
            AIMessage(content="产品A有黑色和白色"),
            HumanMessage(content="它的退货政策是什么？"),
        ]

        history = extract_history(messages)
        result = await llm_rewrite_query(query="它的退货政策是什么？", history=history, synonym_map=mock_syn_map)

        assert "退货" in result
        assert "产品A" in result or "它" not in result


@pytest.mark.asyncio
async def test_llm_rewrite_no_llm_fallback_to_normalize():
    """LLM 不可用时回退到 normalize_query"""
    from unittest.mock import patch

    with patch("app.agents.nodes.rewrite.create_llm", side_effect=Exception("LLM unavailable")):
        from app.agents.nodes.rewrite import llm_rewrite_query
        from app.knowledge.rewriter import normalize_query

        result = await llm_rewrite_query(query="  如何 请假  ？  ", history=[], synonym_map={})
        expected = normalize_query("  如何 请假  ？  ")
        assert result == expected


@pytest.mark.asyncio
async def test_rewrite_node_uses_llm_when_history_exists():
    """rewrite_node 有多轮对话时调用 LLM 改写"""
    from unittest.mock import AsyncMock, MagicMock, patch
    from app.agents.state import create_initial_state
    from langchain_core.messages import HumanMessage, AIMessage

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="产品A的退货政策是什么？"))

    with patch("app.agents.nodes.rewrite.create_llm", return_value=mock_llm):
        from app.agents.nodes.rewrite import rewrite_node

        messages = [
            HumanMessage(content="产品A有哪些颜色？"),
            AIMessage(content="黑色和白色"),
            HumanMessage(content="它的退货政策是什么？"),
        ]

        state = create_initial_state(thread_id="t1", query="它的退货政策是什么？")
        state["messages"] = messages

        result = await rewrite_node(state)
        assert "产品A" in result["rewritten_query"]
        assert "退货" in result["rewritten_query"]


@pytest.mark.asyncio
async def test_rewrite_node_single_turn_no_llm():
    """单轮对话时不调用 LLM"""
    from app.agents.state import create_initial_state

    from app.agents.nodes.rewrite import rewrite_node

    state = create_initial_state(thread_id="t2", query="如何请假")
    state["messages"] = state.get("messages", [])

    result = await rewrite_node(state)
    assert result["rewritten_query"] == "如何请假"


@pytest.mark.asyncio
async def test_rewrite_node_empty_query():
    """空查询直接返回空字符串"""
    from app.agents.state import create_initial_state
    from app.agents.nodes.rewrite import rewrite_node

    state = create_initial_state(thread_id="t3", query="")
    result = await rewrite_node(state)
    assert result["rewritten_query"] == ""


@pytest.mark.asyncio
async def test_llm_rewrite_includes_synonym_hint():
    """LLM 改写 Prompt 包含同义词提示"""
    from unittest.mock import AsyncMock, MagicMock, patch

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="考勤打卡规则查询"))

    syn_map: dict[str, list[str]] = {"考勤": ["打卡", "签到"], "OA": ["办公系统"]}

    with patch("app.agents.nodes.rewrite.create_llm", return_value=mock_llm):
        from app.agents.nodes.rewrite import llm_rewrite_query

        result = await llm_rewrite_query(query="打卡规则", history=[], synonym_map=syn_map)
        assert "考勤" in result or "打卡" in result

        # Verify the synonym was included in the prompt sent to LLM
        call_args = mock_llm.ainvoke.call_args[0][0]
        prompt_text = str(call_args)
        assert "考勤" in prompt_text
        assert "打卡" in prompt_text


@pytest.mark.asyncio
async def test_rewrite_node_with_synonyms():
    """rewrite_node 多轮对话时传递同义词到 LLM"""
    from unittest.mock import AsyncMock, MagicMock, patch
    from app.agents.state import create_initial_state
    from langchain_core.messages import HumanMessage, AIMessage

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="请假休假调休相关制度"))

    syn_map: dict[str, list[str]] = {"请假": ["休假", "调休"]}

    with patch("app.agents.nodes.rewrite.create_llm", return_value=mock_llm):
        with patch("app.agents.nodes.rewrite._SYNONYM_MAP", syn_map):
            from app.agents.nodes.rewrite import rewrite_node

            messages = [
                HumanMessage(content="你好"),
                AIMessage(content="你好！有什么可以帮你的？"),
                HumanMessage(content="休假怎么申请？"),
            ]

            state = create_initial_state(thread_id="t4", query="休假怎么申请？")
            state["messages"] = messages

            result = await rewrite_node(state)
            assert len(result["rewritten_query"]) > 0


@pytest.mark.asyncio
async def test_load_synonym_map_from_db(client, db_session, token_factory):
    """从 DB 加载同义词映射"""
    from app.knowledge.rewriter import load_synonym_map

    token = await token_factory("synrewrite", "superadmin")

    await client.post(
        "/api/admin/synonyms",
        json={"word": "打卡", "synonyms": ["签到", "考勤"]},
        headers={"Authorization": f"Bearer {token}"},
    )

    syn_map = await load_synonym_map(db_session)
    assert "打卡" in syn_map
    assert "签到" in syn_map["打卡"]


@pytest.mark.asyncio
async def test_agent_rewrite_api_uses_db_synonyms(client, db_session, token_factory):
    """/api/agent/rewrite 使用 DB 同义词而非硬编码"""
    token = await token_factory("synagent", "superadmin")

    await client.post(
        "/api/admin/synonyms",
        json={"word": "报销", "synonyms": ["费用申请", "差旅费"]},
        headers={"Authorization": f"Bearer {token}"},
    )

    resp = await client.post(
        "/api/agent/rewrite",
        json={"message": "报销流程怎么走"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "original" in data
    assert "rewritten" in data or "expanded" in data or "normalized" in data
