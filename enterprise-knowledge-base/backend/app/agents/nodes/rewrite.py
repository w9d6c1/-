"""查询改写节点 — LLM 语义改写 + 同义词扩展 + 指代消解"""

import copy

from langchain_core.messages import BaseMessage

from app.agents.llm import acall_llm_with_retry, create_llm
from app.agents.state import AgentState
from app.core.logging import logger
from app.knowledge.rewriter import normalize_query

_SYNONYM_MAP: dict[str, list[str]] = {}

REWRITE_SYSTEM_PROMPT = """你是一个查询改写助手。你的任务是将用户的多轮对话问题改写成独立、完整、清晰的查询语句。

规则：
1. 将指代词（"它"、"这个"、"那个"等）替换为对话历史上文中的具体实体
2. 补全省略的主语和宾语，使查询独立于对话历史
3. 保持原始问题的意图和关键信息
4. 如果有同义词提示，优先使用标准术语替换口语化表达
5. 只输出改写后的查询语句，不要添加任何解释、标点修饰或引号

示例：
历史: 用户问"产品A支持哪些颜色？" 客服答"黑色、白色、红色"
当前问题: "它的价格是多少？"
输出: 产品A的价格是多少？
"""


def _build_rewrite_messages(
    query: str,
    history: list[dict[str, str]],
    synonym_map: dict[str, list[str]],
) -> list:
    from langchain_core.messages import HumanMessage, SystemMessage

    messages: list = [SystemMessage(content=REWRITE_SYSTEM_PROMPT)]

    history_text = ""
    if history:
        history_lines = []
        for h in history[-6:]:
            role = "用户" if h["role"] == "user" else "客服"
            history_lines.append(f"{role}: {h['content']}")
        history_text = "\n".join(history_lines)

    synonym_text = ""
    if synonym_map:
        pairs = [f"{k} → {', '.join(v)}" for k, v in list(synonym_map.items())[:10]]
        synonym_text = "\n".join(pairs)

    user_prompt = ""
    if history_text:
        user_prompt += f"对话历史:\n{history_text}\n\n"
    if synonym_text:
        user_prompt += f"同义词参考:\n{synonym_text}\n\n"
    user_prompt += f"当前问题: {query}"

    messages.append(HumanMessage(content=user_prompt))
    return messages


def extract_history(messages: list[BaseMessage], max_messages: int = 6) -> list[dict[str, str]]:
    history: list[dict[str, str]] = []
    for msg in messages[-max_messages:]:
        role = "user" if msg.__class__.__name__ == "HumanMessage" else "assistant"
        content = str(msg.content) if hasattr(msg, "content") else ""
        history.append({"role": role, "content": content})
    return history


async def llm_rewrite_query(
    query: str,
    history: list[dict[str, str]],
    synonym_map: dict[str, list[str]],
) -> str:
    """使用 LLM 进行语义级查询改写"""
    try:
        llm = create_llm(temperature=0.0, max_tokens=256, top_p=1.0)
        msgs = _build_rewrite_messages(query, history, synonym_map)
        result = await acall_llm_with_retry(llm, msgs, max_retries=2)
        cleaned = result.strip().strip("\"'").strip()
        if cleaned:
            return cleaned
    except Exception:
        logger.debug("llm_rewrite_failed", query=query, exc_info=True)

    return normalize_query(query)


def _get_synonym_map() -> dict[str, list[str]]:
    return _SYNONYM_MAP


def update_synonym_map(syn_map: dict[str, list[str]]) -> None:
    global _SYNONYM_MAP
    _SYNONYM_MAP = dict(syn_map)


async def rewrite_node(state: AgentState) -> AgentState:
    result = copy.deepcopy(state)
    query = state.get("original_query", "")

    if not query or not query.strip():
        result["rewritten_query"] = ""
        return result

    messages = state.get("messages", [])

    if len(messages) <= 1:
        result["rewritten_query"] = normalize_query(query)
        return result

    history = extract_history(messages)
    syn_map = _get_synonym_map()
    rewritten = await llm_rewrite_query(query=query, history=history, synonym_map=syn_map)
    result["rewritten_query"] = rewritten
    return result
