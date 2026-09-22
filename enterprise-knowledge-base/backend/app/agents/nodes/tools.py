"""工具调用决策节点 — ReAct Loop + 查询分解 + 工具绑定"""

import asyncio
import copy
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool

from app.agents.llm import create_llm
from app.agents.state import AgentState
from app.core.logging import logger
from app.retrieval.fusion import FusionResult, hybrid_retrieve

_TOOL_RETRIEVE_TIMEOUT = 15

TOOL_SYSTEM_PROMPT = """你是一个企业知识库的智能检索助手。你可以使用以下工具来帮助用户找到更准确的答案：

1. **search_knowledge_base**: 在知识库中搜索更多相关文档。当已有文档不够完整或相关时使用。
2. **decompose_query**: 将复杂多问题拆分为多个独立子查询，便于分别检索。

规则：
- 如果已有检索结果已经足够回答问题，不需要调用工具。
- 如果用户的查询包含多个独立问题，先调用 decompose_query 拆分。
- 如果某些方面缺乏相关文档，调用 search_knowledge_base 补充。
- 最多调用 3 次工具。"""

TOOLS: list = []


@tool
async def search_knowledge_base(query: str, scope: str = "public") -> str:
    """在知识库中搜索相关文档。当已有检索结果不完整时使用此工具补充搜索。

    Args:
        query: 搜索关键词或问题
        scope: 搜索范围 (public/internal/customer)，默认 public
    """
    try:
        results = await hybrid_retrieve(query, scope=scope, top_k=5)
        if not results:
            return "未找到相关结果。"
        parts = [r.content for r in results]
        return "\n".join(parts)
    except Exception as e:
        logger.warning("search_knowledge_base_failed", error=str(e))
        return f"搜索失败: {e}"


@tool
def decompose_query(query: str) -> str:
    """将包含多个独立问题的复杂查询拆分为多个子查询，每行一个子查询。

    Args:
        query: 需要拆分的复杂查询
    """
    return query


TOOLS = [search_knowledge_base, decompose_query]


def _format_docs_for_llm(docs: list[FusionResult]) -> str:
    if not docs:
        return "（无已检索文档）"
    parts: list[str] = []
    for i, doc in enumerate(docs[:10]):
        parts.append(f"文档{i + 1}：{doc.content}\n")
    return "\n".join(parts)


async def _execute_tool(tool_call: dict, state: AgentState) -> list[FusionResult]:
    name = tool_call.get("name", "")
    args = tool_call.get("args", {})
    call_id = tool_call.get("id", "unknown")

    if name == "search_knowledge_base":
        sub_query = args.get("query", "")
        scope = args.get("scope", "public")
        if not sub_query:
            return []
        logger.info("tool_search_knowledge_base", query=sub_query, scope=scope, call_id=call_id)
        try:
            results = await asyncio.wait_for(
                hybrid_retrieve(sub_query, scope=scope, top_k=5),
                timeout=_TOOL_RETRIEVE_TIMEOUT,
            )
            return list(results)
        except (asyncio.TimeoutError, Exception):
            return []

    elif name == "decompose_query":
        complex_query = args.get("query", "")
        if not complex_query:
            return []
        sub_queries = _split_sub_queries(complex_query)
        logger.info("tool_decompose_query", original=complex_query, sub_count=len(sub_queries), call_id=call_id)

        all_results: list[FusionResult] = []
        scopes = state.get("user_scopes", ["public"])
        for sub_q in sub_queries:
            for scope in scopes:
                try:
                    results = await asyncio.wait_for(
                        hybrid_retrieve(sub_q, scope=scope, top_k=3),
                        timeout=_TOOL_RETRIEVE_TIMEOUT,
                    )
                    all_results.extend(results)
                except (asyncio.TimeoutError, Exception):
                    pass
        return all_results

    return []


def _split_sub_queries(query: str) -> list[str]:
    """将复杂查询拆分为子查询"""
    delimiters = ["和", "与", "以及", "还有", "？", "?", "。", ";", "；", "\n"]
    parts = [query]
    for delim in delimiters:
        new_parts: list[str] = []
        for p in parts:
            new_parts.extend(p.split(delim))
        parts = [s.strip() for s in new_parts if s.strip()]

    if len(parts) <= 1 and len(query) > 40:
        return [query[:len(query) // 2], query[len(query) // 2:]]
    return parts[:5]


def _merge_docs(original: list[FusionResult], new_docs: list[FusionResult]) -> list[FusionResult]:
    seen: set[str] = set()
    merged: list[FusionResult] = []
    for doc in original:
        if doc.unique_id not in seen:
            seen.add(doc.unique_id)
            merged.append(doc)
    for doc in new_docs:
        if doc.unique_id not in seen:
            seen.add(doc.unique_id)
            merged.append(doc)
    merged.sort(key=lambda d: d.fused_score, reverse=True)
    return merged


async def tool_decision_node(state: AgentState) -> AgentState:
    result = copy.deepcopy(state)

    iteration = state.get("iteration", 0)
    if iteration >= 3:
        return result

    query = state.get("rewritten_query") or state.get("original_query", "")
    docs = state.get("retrieved_docs", [])

    # 性能优化：企微渠道且已有检索结果时，跳过 ReAct 循环（省一次 LLM 决策往返）。
    # 检索结果已足以支撑 answer，避免为每个文档类问题多付一次 DeepSeek 调用。
    if state.get("channel") == "wecom" and docs:
        result["iteration"] = iteration + 1
        return result

    try:
        llm = create_llm(temperature=0.0, max_tokens=1024, top_p=1.0)
        llm_with_tools = llm.bind_tools(TOOLS)
    except Exception:
        result["iteration"] = iteration + 1
        return result

    messages: list = [
        SystemMessage(content=TOOL_SYSTEM_PROMPT),
        HumanMessage(content=f"用户问题：{query}\n\n已检索文档：\n{_format_docs_for_llm(docs)}\n\n请判断是否需要调用工具来补充搜索或分解查询。"),
    ]

    tool_iterations = 0
    max_tool_iterations = 3 - iteration
    enriched_docs: list[FusionResult] = []

    try:
        for _ in range(max_tool_iterations):
            response = await llm_with_tools.ainvoke(messages)
            content = getattr(response, "content", "")
            tool_calls = getattr(response, "tool_calls", None)

            if not tool_calls:
                stripped = copy.deepcopy(response)
                stripped.content = ""
                messages.append(stripped)
                break

            stripped = copy.deepcopy(response)
            stripped.content = ""
            messages.append(stripped)

            for tc in tool_calls:
                tool_docs = await _execute_tool(tc, state)
                enriched_docs.extend(tool_docs)
                tool_result = f"工具 {tc.get('name')} 执行完成，返回 {len(tool_docs)} 条结果。"
                messages.append(ToolMessage(content=tool_result, tool_call_id=tc.get("id", "unknown")))

            tool_iterations += 1
    except Exception:
        logger.debug("tool_loop_error", exc_info=True)

    result["iteration"] = min(iteration + tool_iterations + 1, 3)
    result["retrieved_docs"] = _merge_docs(docs, enriched_docs)
    return result
