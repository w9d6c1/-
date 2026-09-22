"""智能体 AI 问答 API 路由 — 完整 chat + SSE 流式 (内部 + 客服)"""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.customer_graph import build_customer_agent_graph, create_customer_state
from app.agents.graph import build_internal_agent_graph
from app.agents.nodes.rewrite import update_synonym_map
from app.agents.state import create_initial_state
from app.core.database import AsyncSessionLocal, get_db
from app.core.dependencies import get_current_user
from app.core.logging import logger as _logger
from app.core.middleware import request_id_var
from app.knowledge.rewriter import expand_synonyms, load_synonym_map, normalize_query, rewrite_query

CurrentUserDep = Annotated[dict | None, Depends(get_current_user)]
DbDep = Annotated[AsyncSession, Depends(get_db)]

router = APIRouter(tags=["agent"])
agent_limiter = Limiter(key_func=get_remote_address)

_agent_graph = None
_customer_graph = None


def _get_graph():
    global _agent_graph
    if _agent_graph is None:
        _agent_graph = build_internal_agent_graph()
    return _agent_graph


def _get_customer_graph():
    global _customer_graph
    if _customer_graph is None:
        _customer_graph = build_customer_agent_graph()
    return _customer_graph


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=5000)
    thread_id: str | None = None
    scope: str = "public"


class CustomerChatRequest(BaseModel):
    message: str
    thread_id: str | None = None


class AgentInfo(BaseModel):
    modules: dict
    status: str


@router.get("/status")
async def agent_status():
    return {"status": "ok", "module": "agent"}


@router.get("/info", response_model=AgentInfo)
async def agent_info():
    return AgentInfo(
        status="ready",
        modules={
            "llm": "ok",
            "embedding": "ok",
            "loader": "ok",
            "rewriter": "ok",
            "es_bm25": "ok",
            "milvus_dense": "ok",
            "rrf_fusion": "ok",
            "reranker": "ok",
            "vector_sync": "ok",
            "validate_node": "ok",
            "auth_node": "ok",
            "rewrite_node": "ok",
            "route_node": "ok",
            "faq_node": "ok",
            "retrieve_node": "ok",
            "tools_node": "ok",
            "context_node": "ok",
            "generate_node": "ok",
            "output_node": "ok",
            "log_node": "ok",
            "graph": "ok",
            "sse_chat": "ok",
        },
    )


# ── 内部智能体 (标准路径) ──

async def _do_chat(req: ChatRequest, source: str = "internal", user: dict | None = None) -> dict:
    graph = _get_graph()
    thread_id = req.thread_id or str(uuid.uuid4())
    request_id = request_id_var.get() or str(uuid.uuid4())

    config = {"configurable": {"thread_id": thread_id}}

    try:
        saved = await graph.aget_state(config)
    except Exception:
        saved = None

    if saved and saved.values and saved.values.get("messages"):
        from langchain_core.messages import HumanMessage
        history = list(saved.values["messages"])
        history.append(HumanMessage(content=req.message))
        state = create_initial_state(thread_id=thread_id, query=req.message)
        state["messages"] = history
        state["rewritten_query"] = ""
    else:
        state = create_initial_state(thread_id=thread_id, query=req.message)

    if user:
        state["user_id"] = user.get("user_id")
        state["user_role"] = user.get("role", "readonly")
        state["user_department"] = user.get("department")
    else:
        state["user_role"] = "readonly"

    result = await asyncio.wait_for(
        graph.ainvoke(state, config=config),
        timeout=120,
    )

    answer = result.get("final_answer", "")
    is_blocked = result.get("is_blocked", False)

    if answer and not is_blocked:
        from langchain_core.messages import AIMessage
        try:
            saved_after = await graph.aget_state(config)
            msgs = list(saved_after.values.get("messages", [])) if saved_after and saved_after.values else []
            msgs.append(AIMessage(content=answer))
            await graph.aupdate_state(config, {"messages": msgs})
        except Exception:
            pass

    confidence = result.get("confidence", 0.0)
    needs_human = result.get("needs_human", False)
    faq_hit = result.get("faq_hit", False)
    route = result.get("route", "")
    hit_faq_id = result.get("hit_faq_id")
    hit_chunk_ids = result.get("hit_chunk_ids")
    node_latency_ms = result.get("total_latency_ms", 0)
    user_id = result.get("user_id")

    asyncio.create_task(_log_chat_async(
        thread_id=thread_id, request_id=request_id, source=source,
        question=req.message, answer=answer if not is_blocked else "",
        confidence=confidence, faq_hit=faq_hit, transfer_human=needs_human,
        sensitive_hit=is_blocked,
        node_name=route or "chat",
        node_latency_ms=node_latency_ms,
        hit_faq_id=hit_faq_id,
        hit_chunk_ids=hit_chunk_ids,
        user_id=user_id,
        citations=result.get("citations"),
        images=result.get("doc_images"),
    ))

    if is_blocked:
        asyncio.create_task(_log_security_async(
            event_type="sensitive_word",
            detail={"query": req.message, "block_reason": result.get("block_reason", ""), "source": source},
            severity="high", request_id=request_id,
        ))

    return {
        "thread_id": thread_id, "answer": answer,
        "is_blocked": is_blocked, "block_reason": result.get("block_reason", ""),
        "confidence": confidence, "needs_human": needs_human,
        "faq_hit": faq_hit, "route": route,
        "citations": result.get("citations", []),
        "images": result.get("doc_images", []),
    }


@router.post("/internal/chat")
@agent_limiter.limit("30/minute")
async def internal_chat(req: ChatRequest, request: Request, current_user: CurrentUserDep = None):
    return await _do_chat(req, "internal", user=current_user)


@router.post("/internal/chat/stream")
async def internal_chat_stream(req: ChatRequest, current_user: CurrentUserDep = None):
    thread_id = req.thread_id or str(uuid.uuid4())
    user_role = current_user.get("role", "readonly") if current_user else "readonly"
    user_id = current_user.get("user_id") if current_user else None
    return StreamingResponse(
        _stream_events(thread_id, req.message, user_role=user_role, user_id=user_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── 内部智能体 (旧路径, 向后兼容) ──

@router.post("/chat", deprecated=True)
async def agent_chat(req: ChatRequest, current_user: CurrentUserDep = None):
    return await _do_chat(req, "internal", user=current_user)


@router.post("/chat/stream", deprecated=True)
async def agent_chat_stream(req: ChatRequest, current_user: CurrentUserDep = None):
    return await internal_chat_stream(req, current_user=current_user)


async def _stream_events(
    thread_id: str,
    query: str,
    user_role: str = "readonly",
    user_id: int | None = None,
) -> AsyncIterator[str]:
    graph = _get_graph()
    config = {"configurable": {"thread_id": thread_id}}

    try:
        saved = await graph.aget_state(config)
    except Exception:
        saved = None

    if saved and saved.values and saved.values.get("messages"):
        from langchain_core.messages import HumanMessage
        history = list(saved.values["messages"])
        history.append(HumanMessage(content=query))
        state = create_initial_state(thread_id=thread_id, query=query)
        state["messages"] = history
        state["rewritten_query"] = ""
    else:
        state = create_initial_state(thread_id=thread_id, query=query)

    state["user_role"] = user_role
    final_emitted = False
    streamed_answer = ""
    final_answer = ""
    done_meta: dict = {}

    try:
        async for event in graph.astream_events(state, version="v2", config=config):
            kind = event.get("event", "")
            if kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk", {})
                content = getattr(chunk, "content", "")
                if content:
                    streamed_answer += str(content)
                    yield f"data: {json.dumps({'type': 'token', 'content': str(content)}, ensure_ascii=False)}\n\n"

            elif kind == "on_chain_end" and not final_emitted:
                output = event.get("data", {}).get("output", {})
                node_name = event.get("name", "")
                if isinstance(output, dict) and output.get("final_answer") and node_name == "output":
                    final_emitted = True
                    final_answer = output.get("final_answer", "")
                    done_meta = {"confidence": output.get("confidence", 0.0), "needs_human": output.get("needs_human", False), "faq_hit": output.get("faq_hit", False), "citations": output.get("citations", []), "images": output.get("doc_images", [])}
                    yield f"data: {json.dumps({'type': 'done', 'answer': final_answer, 'confidence': output.get('confidence', 0.0), 'needs_human': output.get('needs_human', False), 'faq_hit': output.get('faq_hit', False), 'citations': output.get('citations', []), 'images': output.get('doc_images', [])}, ensure_ascii=False)}\n\n"
        if not final_emitted:
            done_meta = {"confidence": 0.0, "needs_human": False, "faq_hit": False, "citations": [], "images": []}
            yield f"data: {json.dumps({'type': 'done', 'answer': '抱歉，未找到相关信息。', 'confidence': 0.0, 'needs_human': False, 'citations': [], 'images': []}, ensure_ascii=False)}\n\n"
    except TimeoutError:
        _logger.warning("stream_timeout", thread_id=thread_id, query=query[:100])
        yield f"data: {json.dumps({'type': 'error', 'message': '请求超时，请稍后再试'}, ensure_ascii=False)}\n\n"
    except Exception as e:
        _logger.error("stream_exception", thread_id=thread_id, query=query[:100], error=str(e))
        yield f"data: {json.dumps({'type': 'error', 'message': '系统内部错误'}, ensure_ascii=False)}\n\n"

    if streamed_answer:
        import re as _re
        cleaned = streamed_answer
        cleaned = _re.sub(r'\[来源[：:][^\]]*\]', '', cleaned)
        cleaned = _re.sub(r'\[FAQ\s*精准匹配\]', '', cleaned)
        cleaned = _re.sub(r'(?m)^#{1,6}\s+', '', cleaned)
        cleaned = _re.sub(r'(?m)^-{3,}$', '', cleaned)
        cleaned = _re.sub(r'(?m)^\s*[-*]\s+', '', cleaned)
        cleaned = _re.sub(r'\n{3,}', '\n\n', cleaned)
        cleaned = _re.sub(
            r'(?:^(?:首先|我[先再]|根据已有|基于上述|接下来|用户|未找到|让我)'
            r'[^。\n]*?(?:搜索|检索|查找|查看|分析|判断|关键词|尝试|工具|换个)[^。\n]*?[。\n]+)',
            '', cleaned, flags=_re.MULTILINE
        )
        cleaned = cleaned.strip()
        streamed_answer = cleaned
        if not final_emitted:
            yield f"data: {json.dumps({'type': 'done', 'answer': cleaned, 'confidence': 0.0, 'needs_human': False, 'citations': [], 'images': []}, ensure_ascii=False)}\n\n"
        from langchain_core.messages import AIMessage
        try:
            saved_after = await graph.aget_state(config)
            msgs = list(saved_after.values.get("messages", [])) if saved_after and saved_after.values else []
            msgs.append(AIMessage(content=streamed_answer))
            await graph.aupdate_state(config, {"messages": msgs})
        except Exception:
            pass

    answer_to_log = final_answer or streamed_answer
    if answer_to_log:
        asyncio.create_task(_log_chat_async(
            thread_id=thread_id,
            request_id=request_id_var.get() or str(uuid.uuid4()),
            source="internal",
            question=query,
            answer=answer_to_log,
            confidence=done_meta.get("confidence", 0.0),
            faq_hit=done_meta.get("faq_hit", False),
            transfer_human=done_meta.get("needs_human", False),
            node_name="chat",
            user_id=user_id,
            citations=done_meta.get("citations"),
            images=done_meta.get("images"),
        ))

    yield "data: [DONE]\n\n"


# ── 客服智能体端点 ──

@router.post("/customer/chat")
@agent_limiter.limit("60/minute")
async def customer_chat(req: CustomerChatRequest, request: Request):
    graph = _get_customer_graph()
    thread_id = req.thread_id or str(uuid.uuid4())
    request_id = request_id_var.get() or str(uuid.uuid4())

    config = {"configurable": {"thread_id": thread_id}}

    try:
        saved = await graph.aget_state(config)
    except Exception:
        saved = None

    if saved and saved.values and saved.values.get("messages"):
        from langchain_core.messages import HumanMessage
        history = list(saved.values["messages"])
        history.append(HumanMessage(content=req.message))
        state = create_customer_state(thread_id=thread_id, query=req.message)
        state["messages"] = history
        state["rewritten_query"] = ""
    else:
        state = create_customer_state(thread_id=thread_id, query=req.message)

    result = await asyncio.wait_for(
        graph.ainvoke(state, config=config),
        timeout=120,
    )

    answer = result.get("final_answer", "")
    is_blocked = result.get("is_blocked", False)

    if answer and not is_blocked:
        from langchain_core.messages import AIMessage
        try:
            saved_after = await graph.aget_state(config)
            msgs = list(saved_after.values.get("messages", [])) if saved_after and saved_after.values else []
            msgs.append(AIMessage(content=answer))
            await graph.aupdate_state(config, {"messages": msgs})
        except Exception:
            pass

    confidence = result.get("confidence", 0.0)
    needs_human = result.get("needs_human", False)
    faq_hit = result.get("faq_hit", False)
    route = result.get("route", "")

    asyncio.create_task(_log_chat_async(
        thread_id=thread_id,
        request_id=request_id,
        source="customer",
        question=req.message,
        answer=answer if not is_blocked else "",
        confidence=confidence,
        faq_hit=faq_hit,
        transfer_human=needs_human,
        sensitive_hit=is_blocked,
        citations=result.get("citations"),
        images=result.get("doc_images"),
    ))

    if is_blocked:
        asyncio.create_task(_log_security_async(
            event_type="sensitive_word",
            detail={"query": req.message, "block_reason": result.get("block_reason", ""), "source": "customer"},
            severity="high",
            request_id=request_id,
        ))

    return {
        "thread_id": thread_id,
        "answer": answer,
        "is_blocked": is_blocked,
        "block_reason": result.get("block_reason", ""),
        "confidence": confidence,
        "needs_human": needs_human,
        "human_reason": result.get("human_reason", ""),
        "faq_hit": faq_hit,
        "route": route,
        "citations": result.get("citations", []),
        "images": result.get("doc_images", []),
    }


async def _customer_stream_events(thread_id: str, query: str) -> AsyncIterator[str]:
    graph = _get_customer_graph()
    config = {"configurable": {"thread_id": thread_id}}

    try:
        saved = await graph.aget_state(config)
    except Exception:
        saved = None

    if saved and saved.values and saved.values.get("messages"):
        from langchain_core.messages import HumanMessage
        history = list(saved.values["messages"])
        history.append(HumanMessage(content=query))
        state = create_customer_state(thread_id=thread_id, query=query)
        state["messages"] = history
        state["rewritten_query"] = ""
    else:
        state = create_customer_state(thread_id=thread_id, query=query)

    streamed_answer = ""
    final_emitted = False
    final_answer = ""
    done_meta: dict = {}

    try:
        async for event in graph.astream_events(state, version="v2", config=config):
            kind = event.get("event", "")
            if kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk", {})
                content = getattr(chunk, "content", "")
                if content:
                    streamed_answer += str(content)
                    yield f"data: {json.dumps({'type': 'token', 'content': str(content)}, ensure_ascii=False)}\n\n"

            elif kind == "on_chain_end" and not final_emitted:
                output = event.get("data", {}).get("output", {})
                node_name = event.get("name", "")
                if isinstance(output, dict) and "final_answer" in output and output.get("final_answer") and node_name == "output":
                    final_emitted = True
                    final_answer = output.get("final_answer", "")
                    done_meta = {"confidence": output.get("confidence", 0.0), "needs_human": output.get("needs_human", False), "faq_hit": output.get("faq_hit", False), "citations": output.get("citations", []), "images": output.get("doc_images", [])}
                    yield f"data: {json.dumps({'type': 'done', 'answer': final_answer, 'confidence': output.get('confidence', 0.0), 'needs_human': output.get('needs_human', False), 'faq_hit': output.get('faq_hit', False), 'citations': output.get('citations', []), 'images': output.get('doc_images', [])}, ensure_ascii=False)}\n\n"
    except TimeoutError:
        _logger.warning("customer_stream_timeout", thread_id=thread_id, query=query[:100])
        yield f"data: {json.dumps({'type': 'error', 'message': '请求超时，请稍后再试'}, ensure_ascii=False)}\n\n"
    except Exception as e:
        _logger.error("customer_stream_exception", thread_id=thread_id, query=query[:100], error=str(e))
        yield f"data: {json.dumps({'type': 'error', 'message': '系统内部错误'}, ensure_ascii=False)}\n\n"

    if streamed_answer:
        import re as _re
        cleaned = streamed_answer
        cleaned = _re.sub(r'\[来源[：:][^\]]*\]', '', cleaned)
        cleaned = _re.sub(r'\[FAQ\s*精准匹配\]', '', cleaned)
        cleaned = _re.sub(r'(?m)^#{1,6}\s+', '', cleaned)
        cleaned = _re.sub(r'(?m)^-{3,}$', '', cleaned)
        cleaned = _re.sub(r'(?m)^\s*[-*]\s+', '', cleaned)
        cleaned = _re.sub(r'\n{3,}', '\n\n', cleaned)
        cleaned = _re.sub(
            r'(?:^(?:首先|我[先再]|根据已有|基于上述|接下来|用户|未找到|让我)'
            r'[^。\n]*?(?:搜索|检索|查找|查看|分析|判断|关键词|尝试|工具|换个)[^。\n]*?[。\n]+)',
            '', cleaned, flags=_re.MULTILINE
        )
        cleaned = cleaned.strip()
        streamed_answer = cleaned
        from langchain_core.messages import AIMessage
        try:
            saved_after = await graph.aget_state(config)
            msgs = list(saved_after.values.get("messages", [])) if saved_after and saved_after.values else []
            msgs.append(AIMessage(content=streamed_answer))
            await graph.aupdate_state(config, {"messages": msgs})
        except Exception:
            pass

    answer_to_log = final_answer or streamed_answer
    if answer_to_log:
        asyncio.create_task(_log_chat_async(
            thread_id=thread_id,
            request_id=request_id_var.get() or str(uuid.uuid4()),
            source="customer",
            question=query,
            answer=answer_to_log,
            confidence=done_meta.get("confidence", 0.0),
            faq_hit=done_meta.get("faq_hit", False),
            transfer_human=done_meta.get("needs_human", False),
            node_name="chat",
            citations=done_meta.get("citations"),
            images=done_meta.get("images"),
        ))

    yield "data: [DONE]\n\n"


@router.post("/customer/chat/stream")
async def customer_chat_stream(req: CustomerChatRequest):
    thread_id = req.thread_id or str(uuid.uuid4())
    return StreamingResponse(
        _customer_stream_events(thread_id, req.message),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── 线程历史恢复 ──

class ThreadSummaryResponse(BaseModel):
    thread_id: str
    title: str
    turns: int
    last_active: datetime


class ThreadMessageResponse(BaseModel):
    question: str
    answer: str
    confidence: float | None = None
    faq_hit: bool = False
    citations: list | None = None
    images: list | None = None
    created_at: datetime


@router.get("/threads", response_model=list[ThreadSummaryResponse])
async def list_threads_api(limit: int = 50, cu: CurrentUserDep = None, db: DbDep = None):
    if cu is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    from app.services.thread_history import list_threads

    return await list_threads(db, "internal", user_id=cu.get("user_id"), limit=min(limit, 100))


@router.get("/threads/{thread_id}/messages", response_model=list[ThreadMessageResponse])
async def get_thread_messages_api(
    thread_id: str, source: str = "internal", cu: CurrentUserDep = None, db: DbDep = None
):
    if source not in ("internal", "customer"):
        raise HTTPException(status_code=400, detail="invalid source")
    from app.services.thread_history import get_thread_messages

    user_id = None
    if source == "internal":
        if cu is None:
            raise HTTPException(status_code=401, detail="Not authenticated")
        user_id = cu.get("user_id")
    msgs = await get_thread_messages(db, thread_id, source, user_id=user_id)
    if source == "internal" and not msgs:
        raise HTTPException(status_code=404, detail="thread not found")
    return msgs


async def _log_chat_async(
    thread_id: str,
    request_id: str,
    source: str,
    question: str,
    answer: str,
    confidence: float,
    faq_hit: bool,
    transfer_human: bool,
    sensitive_hit: bool = False,
    node_name: str | None = None,
    node_latency_ms: int = 0,
    hit_faq_id: int | None = None,
    hit_chunk_ids: list[str] | None = None,
    user_id: int | None = None,
    citations: list | None = None,
    images: list | None = None,
) -> None:
    from app.services.audit_service import AuditLogService

    try:
        async with AsyncSessionLocal() as db:
            svc = AuditLogService(db)
            await svc.log_chat(
                thread_id=thread_id,
                request_id=request_id,
                source=source,
                question=question,
                answer=answer,
                confidence=confidence,
                faq_hit=faq_hit,
                transfer_human=transfer_human,
                sensitive_hit=sensitive_hit,
                node_name=node_name,
                node_latency_ms=node_latency_ms,
                hit_faq_id=hit_faq_id,
                hit_chunk_ids=hit_chunk_ids,
                user_id=user_id,
                node_output={"citations": citations, "images": images}
                if citations or images
                else None,
            )
    except Exception:
        _logger.warning("chat_log_async_failed", thread_id=thread_id, exc_info=True)


async def _log_security_async(
    event_type: str,
    detail: dict,
    severity: str = "medium",
    request_id: str = "",
) -> None:
    from app.services.audit_service import AuditLogService

    try:
        async with AsyncSessionLocal() as db:
            svc = AuditLogService(db)
            await svc.log_security(
                event_type=event_type,
                request_id=request_id,
                detail=detail,
                severity=severity,
            )
    except Exception:
        _logger.warning("security_log_async_failed", event_type=event_type, exc_info=True)

    if severity in ("high", "critical"):
        try:
            from app.core.notifier import notify_security_event
            await notify_security_event(
                event_type=event_type,
                detail=str(detail),
                severity=severity,
            )
        except Exception:
            _logger.warning("security_notify_failed", event_type=event_type, exc_info=True)


# ── 查询改写端点 ──

@router.post("/rewrite")
async def agent_rewrite(req: ChatRequest):
    syn_map: dict[str, list[str]] = {}
    try:
        async with AsyncSessionLocal() as db:
            syn_map = await load_synonym_map(db)
    except Exception:
        _logger.warning("synonym_load_failed", exc_info=True)
    update_synonym_map(syn_map)

    normalized = normalize_query(req.message)
    expanded = expand_synonyms(normalized, syn_map)
    rewritten = rewrite_query(req.message, syn_map)
    return {
        "original": req.message,
        "normalized": normalized,
        "expanded": expanded,
        "rewritten": rewritten,
    }
