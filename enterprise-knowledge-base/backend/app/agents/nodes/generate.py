"""答案生成节点 — LLM Prompt 模板 + 引用标注 + 流式支持"""

import asyncio
import copy

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.llm import clean_response, create_llm
from app.agents.state import AgentState
from app.core.config import settings
from app.core.logging import logger

QA_SYSTEM_PROMPT = """你是一个企业知识库问答助手。你只能依据下方提供的文档内容回答用户问题。

规则：
1. 只基于提供的文档内容回答，严禁编造或使用文档之外的知识。
2. 回答中引用文档时，使用 [1]、[2]、[3] 等数字标记对应参考文档的序号。
3. 如果文档内容不足以回答问题，必须明确告知用户"知识库中暂无相关信息"，不得自行发挥。
4. 与知识库/文档无关的闲聊、通用知识、个人问题，一律礼貌拒绝，引导用户询问与知识库相关的问题。
5. 保持回答简洁、专业、准确。
6. 回答使用中文。"""

_GENERATE_MAX_RETRIES = 3
_GENERATE_RETRY_DELAYS = [1.0, 2.0, 4.0]


async def generate_node(state: AgentState) -> AgentState:
    result = copy.deepcopy(state)
    query = state.get("rewritten_query") or state.get("original_query", "")
    context = state.get("context", "").strip()

    # FAQ 精准命中：答案由人工维护，直接返回，跳过 LLM 重新加工（大幅提速）
    if settings.faq_direct_answer and state.get("faq_hit") and state.get("faq_answer"):
        result["final_answer"] = clean_response(state["faq_answer"])
        result["faq_direct"] = True
        return result

    # 检索不到任何相关内容时，直接返回固定拒绝语，避免 LLM 凭自身知识回答无关内容
    if not context:
        result["final_answer"] = settings.no_answer_reply
        return result

    history = state.get("messages", [])
    messages = [SystemMessage(content=QA_SYSTEM_PROMPT)]
    for msg in history:
        messages.append(msg)
    messages.append(HumanMessage(content=f"用户最新问题：{query}\n\n参考文档：\n{context}\n\n请结合对话历史回答问题："))

    last_error: Exception | None = None
    for attempt in range(_GENERATE_MAX_RETRIES):
        try:
            llm = create_llm(temperature=0.3, max_tokens=512)
            chunks: list[str] = []
            async for chunk in llm.astream(messages):
                content = getattr(chunk, "content", "")
                if content:
                    chunks.append(str(content))
            answer = "".join(chunks)
            if not answer:
                answer = "抱歉，未找到相关信息。"
            result["final_answer"] = answer
            if attempt > 0:
                logger.info("generate_retry_succeeded", attempt=attempt + 1)
            return result
        except Exception as e:
            last_error = e
            logger.warning("generate_llm_failed", attempt=attempt + 1, max_retries=_GENERATE_MAX_RETRIES, error=str(e))
            if attempt < _GENERATE_MAX_RETRIES - 1:
                await asyncio.sleep(_GENERATE_RETRY_DELAYS[attempt])

    logger.error("generate_all_retries_failed", error=str(last_error), query=query[:100])
    result["final_answer"] = "抱歉，生成答案时出错，请稍后重试。"
    return result
