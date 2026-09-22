"""企业微信渠道服务 — 消息处理主流程

流程:验签解密 → 幂等去重 → 身份映射 → 调内部智能体 → 主动回推。
因企微被动响应有 5 秒超时,而 AI 生成较慢,采用:
被动响应立即返回空串(200) + 后台任务异步生成并主动推送。
"""

import asyncio
import uuid

from app.agents.graph import build_internal_agent_graph
from app.agents.state import create_initial_state
from app.agents.cache import get_cache
from app.channels.wecom import asr
from app.channels.wecom.client import download_media, send_text_message
from app.core.config import settings
from app.core.logging import logger
from app.services.identity_service import resolve_internal_identity

_SOURCE = "wecom"
_THREAD_TTL = 3 * 24 * 3600  # 会话映射保留 3 天
_DEDUP_TTL = 300  # MsgId 去重窗口 5 分钟
_AGENT_TIMEOUT = 110

_graph = None


def _get_graph():
    global _graph
    if _graph is None:
        _graph = build_internal_agent_graph()
    return _graph


def _thread_key(user_id: str) -> str:
    return f"channel:wecom:thread:{user_id}"


def _dedup_key(msg_id: str) -> str:
    return f"channel:wecom:msg:{msg_id}"


async def is_duplicate(msg_id: str) -> bool:
    """基于 MsgId 幂等去重(企微会重试)。"""
    if not msg_id:
        return False
    cache = get_cache()
    try:
        client = await cache._ensure_client()
        # SET NX: 不存在才写入,返回 True 表示首次
        ok = await client.set(_dedup_key(msg_id), "1", nx=True, ex=_DEDUP_TTL)
        return not ok
    except Exception:
        logger.warning("wecom_dedup_failed", msg_id=msg_id, exc_info=True)
        return False


async def _get_or_create_thread(user_id: str) -> str:
    cache = get_cache()
    try:
        cached = await cache.get(_thread_key(user_id))
        if cached and cached.get("thread_id"):
            return str(cached["thread_id"])
    except Exception:
        logger.warning("wecom_thread_get_failed", user_id=user_id, exc_info=True)

    thread_id = str(uuid.uuid4())
    try:
        await cache.set(_thread_key(user_id), {"thread_id": thread_id}, ttl=_THREAD_TTL)
    except Exception:
        logger.warning("wecom_thread_set_failed", user_id=user_id, exc_info=True)
    return thread_id


async def generate_answer(user_id: str, question: str) -> str:
    """调用内部智能体生成回答,并异步落库审计日志。"""
    request_id = str(uuid.uuid4())
    identity = resolve_internal_identity(
        external_id=user_id,
        default_role=settings.wecom_default_role,
    )
    thread_id = await _get_or_create_thread(user_id)

    graph = _get_graph()
    state = create_initial_state(
        thread_id=thread_id,
        query=question,
        user_id=identity.user_id,
        user_role=identity.role,
        user_department=identity.department,
        user_scopes=identity.scopes,
        channel=_SOURCE,
    )

    try:
        result = await asyncio.wait_for(
            graph.ainvoke(state, config={"configurable": {"thread_id": thread_id}}),
            timeout=_AGENT_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning("wecom_agent_timeout", user_id=user_id)
        return "抱歉，处理超时，请稍后重试。"
    except Exception:
        logger.warning("wecom_agent_error", user_id=user_id, exc_info=True)
        return "抱歉，系统繁忙，请稍后重试。"

    is_blocked = result.get("is_blocked", False)
    answer = "抱歉，您的问题包含不支持的内容。" if is_blocked else (
        result.get("final_answer") or "抱歉，未找到相关信息。"
    )

    # 全链路审计落库(与 /api/agent 端点保持一致)
    asyncio.create_task(_log_chat(
        thread_id=thread_id,
        request_id=request_id,
        question=question,
        answer="" if is_blocked else answer,
        confidence=result.get("confidence", 0.0),
        faq_hit=result.get("faq_hit", False),
        transfer_human=result.get("needs_human", False),
        sensitive_hit=is_blocked,
        node_name=result.get("route") or "chat",
    ))
    if is_blocked:
        asyncio.create_task(_log_security(
            request_id=request_id,
            detail={
                "query": question,
                "block_reason": result.get("block_reason", ""),
                "source": _SOURCE,
                "external_user": user_id,
            },
        ))

    return answer


async def _log_chat(
    thread_id: str,
    request_id: str,
    question: str,
    answer: str,
    confidence: float,
    faq_hit: bool,
    transfer_human: bool,
    sensitive_hit: bool,
    node_name: str | None,
) -> None:
    from app.core.database import AsyncSessionLocal
    from app.services.audit_service import AuditLogService

    try:
        async with AsyncSessionLocal() as db:
            await AuditLogService(db).log_chat(
                thread_id=thread_id,
                request_id=request_id,
                source=_SOURCE,
                question=question,
                answer=answer,
                confidence=confidence,
                faq_hit=faq_hit,
                transfer_human=transfer_human,
                sensitive_hit=sensitive_hit,
                node_name=node_name,
            )
    except Exception:
        logger.warning("wecom_chat_log_failed", thread_id=thread_id, exc_info=True)


async def _log_security(request_id: str, detail: dict) -> None:
    from app.core.database import AsyncSessionLocal
    from app.services.audit_service import AuditLogService

    try:
        async with AsyncSessionLocal() as db:
            await AuditLogService(db).log_security(
                event_type="sensitive_word",
                request_id=request_id,
                detail=detail,
                severity="high",
            )
    except Exception:
        logger.warning("wecom_security_log_failed", exc_info=True)


async def process_and_reply(user_id: str, question: str) -> None:
    """后台任务:生成回答并主动推送给用户。"""
    if settings.wecom_send_ack:
        await send_text_message(user_id, settings.wecom_ack_reply)
    answer = await generate_answer(user_id, question)
    ok = await send_text_message(user_id, answer)
    if not ok:
        logger.warning("wecom_reply_push_failed", user_id=user_id)


async def handle_message(msg: dict) -> None:
    """处理一条解密后的企微消息(在后台任务中调用)。

    msg: parse_message_xml 的输出,含 MsgType/FromUserName/Content/MsgId 等。
    """
    msg_type = msg.get("MsgType", "")
    user_id = msg.get("FromUserName", "")
    msg_id = msg.get("MsgId", "")

    if not user_id:
        return

    if await is_duplicate(msg_id):
        logger.info("wecom_duplicate_msg_skipped", msg_id=msg_id)
        return

    if msg_type == "voice":
        await _handle_voice(user_id, msg)
        return

    if msg_type != "text":
        await send_text_message(user_id, "目前仅支持文本消息，请输入文字问题。")
        return

    question = (msg.get("Content") or "").strip()
    if not question:
        return

    await process_and_reply(user_id, question)


async def _handle_voice(user_id: str, msg: dict) -> None:
    """语音消息：下载媒体 → 转文字 → 走正常问答。"""
    media_id = (msg.get("MediaId") or "").strip()
    if not media_id:
        await send_text_message(user_id, "语音消息解析失败，请用文字提问。")
        return

    voice_format = (msg.get("Format") or "amr").lower()
    audio = await download_media(media_id)
    if not audio:
        await send_text_message(user_id, "语音下载失败，请稍后重试或用文字提问。")
        return

    question = await asr.transcribe(audio, voice_format=voice_format, usr_key=(msg.get("MsgId") or ""))
    if not question:
        await send_text_message(user_id, "语音识别暂不可用，请用文字提问。")
        return

    await process_and_reply(user_id, question)
