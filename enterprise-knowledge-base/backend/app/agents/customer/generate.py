"""客服答案生成节点 — 客服友好的 Prompt 模板 + 流式支持"""

import asyncio
import copy

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.llm import create_llm
from app.agents.state import AgentState
from app.core.logging import logger

CUSTOMER_QA_SYSTEM_PROMPT = """你是一个企业客服助手。请根据提供的知识库文档内容，以友好、专业的方式回答用户问题。

规则：
1. 只基于提供的文档内容回答，不要编造信息。
2. 回答中必须标注信息来源，格式为 [来源: 文档标题]。
3. 如果文档中没有相关信息，请友好地告知用户，并建议用户联系人工客服获取帮助。
4. 保持回答简洁、专业、有礼貌。使用"您"称呼用户。
5. 对于投诉、退款等敏感问题，先安抚用户情绪，再提供解决方案。
6. 回答使用中文，语气温暖但不谄媚。"""

_GENERATE_MAX_RETRIES = 3
_GENERATE_RETRY_DELAYS = [1.0, 2.0, 4.0]


async def customer_generate_node(state: AgentState) -> AgentState:
    result = copy.deepcopy(state)
    query = state.get("rewritten_query") or state.get("original_query", "")
    context = state.get("context", "")

    if not context:
        context = "（无相关知识库内容，请基于对话历史友好回复）"

    history = state.get("messages", [])
    messages = [SystemMessage(content=CUSTOMER_QA_SYSTEM_PROMPT)]
    for msg in history:
        messages.append(msg)
    messages.append(HumanMessage(content=f"用户最新问题：{query}\n\n参考文档：\n{context}\n\n请结合对话历史回答问题："))

    last_error: Exception | None = None
    for attempt in range(_GENERATE_MAX_RETRIES):
        try:
            llm = create_llm(temperature=0.3, max_tokens=1024)
            chunks: list[str] = []
            async for chunk in llm.astream(messages):
                content = getattr(chunk, "content", "")
                if content:
                    chunks.append(str(content))
            answer = "".join(chunks)
            if not answer:
                answer = "抱歉，系统暂时遇到问题，请稍后重试或联系人工客服。"
            result["final_answer"] = answer
            if attempt > 0:
                logger.info("customer_generate_retry_succeeded", attempt=attempt + 1)
            return result
        except Exception as e:
            last_error = e
            logger.warning("customer_generate_llm_failed", attempt=attempt + 1, max_retries=_GENERATE_MAX_RETRIES, error=str(e))
            if attempt < _GENERATE_MAX_RETRIES - 1:
                await asyncio.sleep(_GENERATE_RETRY_DELAYS[attempt])

    logger.error("customer_generate_all_retries_failed", error=str(last_error), query=query[:100])
    result["final_answer"] = "抱歉，系统暂时遇到问题，请稍后重试或联系人工客服。"
    return result
