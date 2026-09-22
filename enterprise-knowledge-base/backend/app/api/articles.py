"""文章批量生成 — REST API 路由

模式: 遵循 app/api/admin/document.py
所有端点挂载在 /api/admin/articles 下。
"""

import asyncio
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response, StreamingResponse

from app.articles.schemas import (
    AccountVerifyResult,
    AnalyzeStyleRequest,
    ArticleDetailResponse,
    ArticleResponse,
    ArticleUpdate,
    BatchCreate,
    BatchDetailResponse,
    BatchPhotoSelectRequest,
    BatchResponse,
    BulkDeleteBatchesRequest,
    ImitateRequest,
    ImitateResponse,
    PhotoMatchRequest,
    PhotoMatchResponse,
    PhotoResponse,
    PhotoUpdate,
    PhotoUploadResponse,
    PlatformAccountCreate,
    PlatformAccountDetailResponse,
    PlatformAccountResponse,
    PlatformAccountUpdate,
    PlatformInfo,
    PublishingRecordResponse,
    PublishingStatsResponse,
    PublishRequest,
    StyleAnalysisResponse,
    TemplateCreate,
    TemplateResponse,
    TemplateUpdate,
    TopicGenerateRequest,
    TopicGenerateResponse,
    TopicRecommendItem,
    WeightedPhotoMatchRequest,
    WeightedPhotoMatchResponse,
)
from app.articles.service import ArticleService, sse_event
from app.core.config import settings
from app.core.dependencies import DbDep, require_auth, require_permission
from app.models.user import User
from app.schemas.common import PaginatedResponse

router = APIRouter(prefix="/articles", tags=["admin-articles"])

# 类型别名
AuthDep = Annotated[User, Depends(require_auth)]
WriteDep = Annotated[User, Depends(require_permission("write"))]

_PAGE = Query(1, ge=1, description="页码")
_PAGE_SIZE = Query(20, ge=1, le=100, description="每页条数")


# ============================================================
# Batch — 批次 CRUD
# ============================================================

@router.post("/batches", response_model=BatchResponse, status_code=201)
async def create_batch(
    payload: BatchCreate,
    db: DbDep,
    cu: WriteDep,
):
    """创建文章生成批次"""
    svc = ArticleService(db)
    batch = await svc.create_batch(
        topic=payload.topic,
        article_count=payload.article_count,
        user_id=cu.id,
        angle_keys=payload.angle_keys,
        account_type=payload.account_type,
    )
    return batch


@router.get("/batches", response_model=PaginatedResponse[BatchResponse])
async def list_batches(
    db: DbDep,
    cu: AuthDep,
    page: int = _PAGE,
    page_size: int = _PAGE_SIZE,
):
    """批次列表（分页）"""
    svc = ArticleService(db)
    items, total = await svc.list_batches(
        user_id=cu.id if cu.role != "superadmin" else None,
        page=page,
        page_size=page_size,
    )
    total_pages = (total + page_size - 1) // page_size
    return PaginatedResponse(
        items=[BatchResponse.model_validate(b) for b in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/batches/{batch_id}", response_model=BatchDetailResponse)
async def get_batch(
    batch_id: int,
    db: DbDep,
    cu: AuthDep,
):
    """批次详情"""
    svc = ArticleService(db)
    batch = await svc.get_batch(batch_id)
    if not batch:
        raise HTTPException(404, "批次不存在")
    return BatchDetailResponse.model_validate(batch)


@router.delete("/batches/{batch_id}")
async def delete_batch(
    batch_id: int,
    db: DbDep,
    cu: WriteDep,
):
    """删除批次（级联删除文章和发布记录）"""
    svc = ArticleService(db)
    ok = await svc.delete_batch(batch_id)
    if not ok:
        raise HTTPException(404, "批次不存在")
    return {"ok": True}


@router.post("/batches/bulk-delete")
async def bulk_delete_batches(
    payload: BulkDeleteBatchesRequest,
    db: DbDep,
    cu: WriteDep,
):
    """批量删除批次（级联删除文章和发布记录），单项失败不影响其余"""
    svc = ArticleService(db)
    deleted = 0
    failed: list[dict] = []
    for batch_id in payload.ids:
        ok = await svc.delete_batch(batch_id)
        if ok:
            deleted += 1
        else:
            failed.append({"id": batch_id, "reason": "not found"})
    return {"deleted": deleted, "failed": failed}


# ============================================================
# Photo Upload
# ============================================================

@router.post("/batches/{batch_id}/upload-photos")
async def upload_photos(
    batch_id: int,
    db: DbDep,
    cu: WriteDep,
    files: list[UploadFile] = File(..., min_length=1, max_length=20),
):
    """上传 3-5 张现场照片"""
    if len(files) < 1:
        raise HTTPException(400, "至少上传 1 张照片")

    # 校验文件
    allowed_types = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
    file_data: list[tuple[str, bytes, str]] = []
    for f in files:
        if f.content_type and f.content_type not in allowed_types:
            raise HTTPException(400, f"不支持的图片格式: {f.content_type}，仅支持 JPEG/PNG/WebP/HEIC")
        data = await f.read()
        if len(data) > 10 * 1024 * 1024:
            raise HTTPException(400, f"图片 {f.filename} 超过 10MB 限制")
        file_data.append((f.filename or "photo.jpg", data, f.content_type or "image/jpeg"))

    svc = ArticleService(db)
    try:
        object_names = await svc.upload_photos(batch_id, file_data)
    except ValueError as e:
        raise HTTPException(404, str(e))

    return {"ok": True, "photo_count": len(object_names), "object_names": object_names}


# ============================================================
# Generation + SSE Progress
# ============================================================

@router.post("/batches/{batch_id}/generate")
async def start_generation(
    batch_id: int,
    db: DbDep,
    cu: WriteDep,
    template_ids: list[int] | None = Query(default=None, description="写作模板 ID 列表"),
    use_photo_library: bool = Query(default=False, description="是否使用照片库（替代手动上传）"),
    min_words: int | None = Query(default=None, description="最小字数"),
    max_words: int | None = Query(default=None, description="最大字数"),
):
    """启动后台生成任务（可选指定写作模板 + 照片库模式 + 字数限制）"""
    svc = ArticleService(db)
    batch = await svc.get_batch(batch_id)
    if not batch:
        raise HTTPException(404, "批次不存在")
    if batch.status == "generating":
        raise HTTPException(400, "该批次正在生成中")

    asyncio.create_task(_run_generation_in_session(batch_id, template_ids, use_photo_library, min_words, max_words))
    return {"ok": True, "batch_id": batch_id, "status": "generating"}


async def _run_generation_in_session(
    batch_id: int, template_ids: list[int] | None = None, use_photo_library: bool = False,
    min_words: int | None = None, max_words: int | None = None,
) -> None:
    """在独立 DB session 中执行生成任务"""
    from app.core.database import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        svc = ArticleService(session)
        photo_ids = None
        if use_photo_library:
            from app.articles.photo_service import PhotoService
            ps = PhotoService(session)
            photos = await ps.get_batch_photos(batch_id)
            photo_ids = [p.id for p in photos]
        await svc.run_generation(batch_id, template_ids, photo_ids, min_words, max_words)


@router.get("/batches/{batch_id}/stream")
async def stream_progress(
    batch_id: int,
    db: DbDep,
    cu: AuthDep,
):
    """SSE 实时进度推送（轮询式）

    持续推送直至批次终态（completed/failed），并在静默期发送心跳，
    避免长耗时生成（单篇 LLM 写作可达数分钟）期间连接因无数据被
    反向代理（nginx/Vite）按空闲超时掐断，导致前端收不到 completed。
    """
    svc = ArticleService(db)
    return StreamingResponse(
        _stream_events(batch_id, db, svc),
        media_type="text/event-stream",
    )


# SSE 心跳间隔（秒）与兜底迭代上限（约 1 小时，正常生成远短于此）
_STREAM_HEARTBEAT_INTERVAL = 30
_STREAM_MAX_ITERATIONS = 3600


async def _stream_events(
    batch_id: int,
    db: DbDep,
    svc: ArticleService,
    heartbeat_interval: float = _STREAM_HEARTBEAT_INTERVAL,
    max_iterations: int = _STREAM_MAX_ITERATIONS,
):
    """批次 SSE 事件生成器（独立成函数便于单元测试）。

    轮询批次状态：状态/数量变化时推送进度；静默期按 heartbeat_interval
    推送心跳；到达 completed/failed 终态后结束。
    """
    last_count = -1
    last_status = ""
    last_beat = 0.0
    for _ in range(max_iterations):
        batch = await svc.get_batch(batch_id)
        if not batch:
            yield sse_event("error", batch_id, "批次不存在")
            return

        await db.refresh(batch)

        if batch.status != last_status:
            last_status = batch.status
            yield sse_event("progress", batch_id, f"状态: {batch.status}",
                            {"status": batch.status})

        if batch.generated_count > last_count:
            last_count = batch.generated_count
            articles, _ = await svc.list_articles(batch_id, page=1, page_size=last_count)
            await db.refresh(batch, attribute_names=["generated_count", "status"])
            articles_data = [ArticleDetailResponse.model_validate(a).model_dump(mode="json") for a in articles]
            yield sse_event("article_generated", batch_id,
                            f"已完成 {batch.generated_count}/{batch.article_count}",
                            articles_data)

        if batch.status == "completed":
            yield sse_event("completed", batch_id, "全部文章生成完毕")
            return
        if batch.status == "failed":
            yield sse_event("error", batch_id,
                            batch.error_message or "生成失败",
                            {"error": batch.error_message})
            return

        # 心跳：静默期每 heartbeat_interval 秒推一次进度，保持连接存活
        now = asyncio.get_running_loop().time()
        if now - last_beat >= heartbeat_interval:
            last_beat = now
            yield sse_event("progress", batch_id,
                            f"生成中：已完成 {batch.generated_count}/{batch.article_count}",
                            {"status": batch.status})

        await asyncio.sleep(1)


# ============================================================
# Article CRUD
# ============================================================

@router.get("/batches/{batch_id}/articles", response_model=PaginatedResponse[ArticleResponse])
async def list_articles(
    batch_id: int,
    db: DbDep,
    cu: AuthDep,
    page: int = _PAGE,
    page_size: int = _PAGE_SIZE,
):
    """列出批次下的文章"""
    svc = ArticleService(db)
    items, total = await svc.list_articles(batch_id, page=page, page_size=page_size)
    total_pages = (total + page_size - 1) // page_size
    return PaginatedResponse(
        items=[ArticleResponse.model_validate(a) for a in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/articles/{article_id}", response_model=ArticleDetailResponse)
async def get_article(
    article_id: int,
    db: DbDep,
    cu: AuthDep,
):
    """文章详情（含正文）"""
    svc = ArticleService(db)
    article = await svc.get_article(article_id)
    if not article:
        raise HTTPException(404, "文章不存在")
    return ArticleDetailResponse.model_validate(article)


@router.put("/articles/{article_id}", response_model=ArticleDetailResponse)
async def update_article(
    article_id: int,
    payload: ArticleUpdate,
    db: DbDep,
    cu: WriteDep,
):
    """编辑文章标题/正文"""
    svc = ArticleService(db)
    article = await svc.update_article(article_id, payload.title, payload.content)
    if not article:
        raise HTTPException(404, "文章不存在")
    return ArticleDetailResponse.model_validate(article)


@router.delete("/articles/{article_id}")
async def delete_article(
    article_id: int,
    db: DbDep,
    cu: WriteDep,
):
    """删除单篇文章"""
    svc = ArticleService(db)
    ok = await svc.delete_article(article_id)
    if not ok:
        raise HTTPException(404, "文章不存在")
    return {"ok": True}


@router.post("/articles/{article_id}/regenerate", response_model=ArticleDetailResponse)
async def regenerate_article(
    article_id: int,
    db: DbDep,
    cu: WriteDep,
):
    """重生成单篇文章"""
    svc = ArticleService(db)
    article = await svc.regenerate_article(article_id)
    if not article:
        raise HTTPException(404, "文章不存在")
    return ArticleDetailResponse.model_validate(article)


# ============================================================
# Publishing
# ============================================================

@router.post("/articles/{article_id}/publish")
async def publish_single(
    article_id: int,
    payload: PublishRequest,
    db: DbDep,
    cu: WriteDep,
):
    """发布单篇文章到指定平台"""
    svc = ArticleService(db)
    article = await svc.get_article(article_id)
    if not article:
        raise HTTPException(404, "文章不存在")

    records = await svc.publish_articles(
        batch_id=article.batch_id,
        platform_ids=payload.platform_ids,
        article_ids=[article_id],
        account_id=payload.account_id,
        scheduled_at=payload.scheduled_at,
    )
    return {
        "ok": True,
        "records": [PublishingRecordResponse.model_validate(r) for r in records],
    }


@router.post("/batches/{batch_id}/publish")
async def publish_batch(
    batch_id: int,
    payload: PublishRequest,
    db: DbDep,
    cu: WriteDep,
):
    """批量发布批次文章到指定平台"""
    svc = ArticleService(db)
    records = await svc.publish_articles(
        batch_id=batch_id,
        platform_ids=payload.platform_ids,
        article_ids=payload.article_ids,
        account_id=payload.account_id,
        scheduled_at=payload.scheduled_at,
    )
    return {
        "ok": True,
        "record_count": len(records),
        "records": [PublishingRecordResponse.model_validate(r) for r in records],
    }


@router.get("/articles/{article_id}/publishing-status", response_model=list[PublishingRecordResponse])
async def get_publishing_status(
    article_id: int,
    db: DbDep,
    cu: AuthDep,
):
    """查询文章发布记录"""
    svc = ArticleService(db)
    records = await svc.get_publishing_records(article_id)
    return [PublishingRecordResponse.model_validate(r) for r in records]


@router.get("/batches/{batch_id}/publishing-status", response_model=list[PublishingRecordResponse])
async def get_batch_publishing_status(
    batch_id: int,
    db: DbDep,
    cu: AuthDep,
):
    """查询批次内全部文章的发布记录（供前端轮询发布进度）"""
    svc = ArticleService(db)
    records = await svc.get_batch_publishing_records(batch_id)
    return [PublishingRecordResponse.model_validate(r) for r in records]


@router.get("/publishing-stats", response_model=PublishingStatsResponse)
async def get_publishing_stats(
    db: DbDep,
    cu: AuthDep,
):
    """发布仪表板统计"""
    from app.articles.schemas import PublishingRecordResponse as PRR
    svc = ArticleService(db)
    stats = await svc.get_publishing_stats()
    return PublishingStatsResponse(
        total_published=stats["total_published"],
        total_failed=stats["total_failed"],
        total_pending=stats["total_pending"],
        today_published=stats["today_published"],
        today_failed=stats["today_failed"],
        by_platform=stats["by_platform"],
        recent_records=[PRR.model_validate(r) for r in stats["recent_records"]],
    )


@router.get("/platforms", response_model=list[PlatformInfo])
async def list_platforms(cu: AuthDep):
    """列出可用发布平台"""
    from app.articles.publisher import list_platforms as _list_platforms
    return [PlatformInfo(**p) for p in _list_platforms()]


@router.get("/bridge/status")
async def bridge_status(cu: AuthDep):
    """发布桥接器状态（后端探测，供前端同源调用，避免浏览器直连本机端口被 CSP/Mixed-content 拦截）"""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.publisher_bridge_url}/health")
            if resp.status_code == 200:
                data = resp.json()
                data["ok"] = bool(data.get("ok"))
                return data
            return {"ok": False, "error": f"桥接器返回 {resp.status_code}"}
    except Exception as exc:
        from app.core.logging import logger as _logger
        _logger.warning("bridge_status_check_failed", error=repr(exc))
        return {"ok": False, "error": "桥接器未启动(3010不可达)"}


# ============================================================
# Platform Account — 平台账号管理
# ============================================================

@router.get("/accounts", response_model=list[PlatformAccountResponse])
async def list_accounts(
    db: DbDep,
    cu: AuthDep,
    platform_id: str | None = Query(default=None, description="按平台筛选"),
):
    """列出平台账号"""
    svc = ArticleService(db)
    accounts = await svc.list_accounts(
        user_id=cu.id if cu.role != "superadmin" else None,
        platform_id=platform_id,
    )
    return [PlatformAccountResponse.model_validate(a) for a in accounts]


@router.post("/accounts", response_model=PlatformAccountResponse, status_code=201)
async def create_account(
    payload: PlatformAccountCreate,
    db: DbDep,
    cu: WriteDep,
):
    """创建平台账号"""
    svc = ArticleService(db)
    account = await svc.create_account(
        platform_id=payload.platform_id,
        account_name=payload.account_name,
        account_group=payload.account_group,
        ws_token=payload.ws_token,
        credentials=payload.credentials or None,
        credentials_type=payload.credentials_type,
        user_id=cu.id,
    )
    return PlatformAccountResponse.model_validate(account)


@router.get("/accounts/{account_id}", response_model=PlatformAccountDetailResponse)
async def get_account(
    account_id: int,
    db: DbDep,
    cu: AuthDep,
):
    """获取账号详情（含解密凭证）"""
    svc = ArticleService(db)
    account = await svc.get_account(account_id)
    if not account:
        raise HTTPException(404, "账号不存在")

    from app.articles.crypto import decrypt_credentials
    result = PlatformAccountDetailResponse.model_validate(account)
    try:
        result.credentials = decrypt_credentials(account.credentials) if account.credentials else ""
    except Exception:
        result.credentials = ""
    return result


@router.put("/accounts/{account_id}", response_model=PlatformAccountResponse)
async def update_account(
    account_id: int,
    payload: PlatformAccountUpdate,
    db: DbDep,
    cu: WriteDep,
):
    """更新平台账号"""
    svc = ArticleService(db)
    account = await svc.update_account(
        account_id=account_id,
        account_name=payload.account_name,
        account_group=payload.account_group,
        ws_token=payload.ws_token,
        credentials=payload.credentials,
        credentials_type=payload.credentials_type,
    )
    if not account:
        raise HTTPException(404, "账号不存在")
    return PlatformAccountResponse.model_validate(account)


@router.delete("/accounts/{account_id}")
async def delete_account(
    account_id: int,
    db: DbDep,
    cu: WriteDep,
):
    """删除平台账号"""
    svc = ArticleService(db)
    ok = await svc.delete_account(account_id)
    if not ok:
        raise HTTPException(404, "账号不存在")
    return {"ok": True}


@router.post("/accounts/{account_id}/verify", response_model=AccountVerifyResult)
async def verify_account(
    account_id: int,
    db: DbDep,
    cu: WriteDep,
):
    """验证账号连接"""
    svc = ArticleService(db)
    result = await svc.verify_account(account_id)
    return AccountVerifyResult(
        success=result["success"],
        message=result["message"],
        account_id=account_id,
    )


# ============================================================
# Export
# ============================================================

@router.get("/articles/{article_id}/export")
async def export_article(
    article_id: int,
    db: DbDep,
    cu: AuthDep,
    format: str = Query("md", pattern="^(md|html|docx)$", description="导出格式"),
):
    """导出单篇文章（MD / HTML / DOCX）"""
    svc = ArticleService(db)
    try:
        data, filename, content_type = await svc.export_article(article_id, format)
    except ValueError as e:
        raise HTTPException(404, str(e))
    except RuntimeError as e:
        raise HTTPException(500, str(e))

    from urllib.parse import quote

    from fastapi.responses import Response
    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
        },
    )


@router.get("/batches/{batch_id}/export")
async def export_batch(
    batch_id: int,
    db: DbDep,
    cu: AuthDep,
):
    """批量导出整个批次为 ZIP（含 MD + DOCX）"""
    svc = ArticleService(db)
    try:
        data = await svc.export_batch_zip(batch_id)
    except RuntimeError as e:
        raise HTTPException(500, str(e))

    batch = await svc.get_batch(batch_id)
    safe_topic = (batch.topic if batch else "articles")[:50].replace("/", "_")

    from urllib.parse import quote
    return StreamingResponse(
        iter([data]),
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(safe_topic)}.zip",
        },
    )


# ============================================================
# Writing Templates — 写作模板 CRUD
# ============================================================

@router.get("/templates", response_model=list[TemplateResponse])
async def list_templates(
    db: DbDep,
    cu: AuthDep,
    account_type: str | None = Query(
        default=None,
        description="按适用账号类型筛选(user/designer/dealer)，空=全部",
    ),
):
    """列出可用模板（系统预设 + 当前用户自定义），可按账号类型筛选"""
    from app.articles.template_service import TemplateService
    svc = TemplateService(db)
    await svc.seed_presets()
    if account_type:
        templates = await svc.list_templates_by_account_type(account_type, cu.id)
    else:
        templates = await svc.list_templates(cu.id)
    return [TemplateResponse.model_validate(t) for t in templates]


@router.post("/templates", response_model=TemplateResponse, status_code=201)
async def create_template(
    payload: TemplateCreate,
    db: DbDep,
    cu: WriteDep,
):
    """创建自定义模板"""
    from app.articles.template_service import TemplateService
    svc = TemplateService(db)
    obj = await svc.create_template(
        cu.id,
        payload.name,
        payload.type,
        payload.prompt_instruction,
        account_type=payload.account_type,
    )
    return TemplateResponse.model_validate(obj)


@router.put("/templates/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: int,
    payload: TemplateUpdate,
    db: DbDep,
    cu: WriteDep,
):
    """编辑自定义模板（预设模板不可修改）"""
    from app.articles.template_service import TemplateService
    svc = TemplateService(db)
    data = {}
    if payload.name is not None:
        data["name"] = payload.name
    if payload.prompt_instruction is not None:
        data["prompt_instruction"] = payload.prompt_instruction
    obj = await svc.update_template(template_id, cu.id, data)
    if not obj:
        raise HTTPException(404, "模板不存在")
    return TemplateResponse.model_validate(obj)


@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: int,
    db: DbDep,
    cu: WriteDep,
):
    """删除模板"""
    from app.articles.template_service import TemplateService
    svc = TemplateService(db)
    ok = await svc.delete_template(template_id, cu.id)
    if not ok:
        raise HTTPException(404, "模板不存在")
    return {"ok": True}


# ============================================================
# Style Analysis — 风格分析
# ============================================================

@router.post("/analyze-style", response_model=StyleAnalysisResponse)
async def analyze_article_style(
    payload: AnalyzeStyleRequest,
    cu: AuthDep,
):
    """分析参考文章的写作风格，返回 5 维度分析结果"""
    from app.articles.imitate import analyze_style

    style = await analyze_style(payload.source_text)
    return StyleAnalysisResponse(**style)


@router.post("/fetch-url", response_model=dict)
async def fetch_article_url(
    payload: dict,
    cu: AuthDep,
):
    """抓取网页文章内容，返回提取的纯文本"""
    import httpx as _httpx

    from app.articles.imitate import fetch_article_content

    url = (payload or {}).get("url", "")
    if not url:
        raise HTTPException(400, "请提供网页链接")

    try:
        content = await fetch_article_content(url, use_jina_fallback=True)
        return {"content": content}
    except ValueError as e:
        raise HTTPException(400, str(e))
    except _httpx.HTTPError as e:
        raise HTTPException(400, f"网页抓取失败: {e}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"网页抓取失败: {e}")


# ============================================================
# Imitate — 模仿创作
# ============================================================

@router.post("/imitate", response_model=ImitateResponse, status_code=201)
async def imitate_article_endpoint(
    payload: ImitateRequest,
    db: DbDep,
    cu: WriteDep,
):
    """模仿创作：分析参考文章风格 → 检索知识库 → 生成模仿文章"""
    source_text = payload.source_text

    # 如果提供了 URL 但没有文本，抓取网页
    if not source_text and payload.source_url:
        try:
            from app.articles.imitate import fetch_article_content

            source_text = await fetch_article_content(payload.source_url, use_jina_fallback=True)
        except ValueError as e:
            raise HTTPException(400, str(e))
        except httpx.HTTPError as e:
            raise HTTPException(400, f"网页抓取失败: {e}")

    if not source_text or len(source_text.strip()) < 100:
        raise HTTPException(400, "参考文章内容不能少于 100 字")

    # 分析风格（优先使用前端已分析的结果，避免重复 LLM 调用）
    from app.articles.imitate import analyze_style, imitate_article, retrieve_knowledge

    if payload.style_analysis:
        style = payload.style_analysis
    else:
        style = await analyze_style(source_text)

    # 检索知识库
    knowledge = await retrieve_knowledge(payload.topic)

    # 创建或复用批次
    svc = ArticleService(db)

    if payload.batch_id:
        batch = await svc.get_batch(payload.batch_id)
        if not batch:
            raise HTTPException(404, "批次不存在")
    else:
        batch = await svc.create_batch(
            topic=payload.topic,
            article_count=1,
            user_id=cu.id,
        )

    # 关联照片
    if payload.photo_ids:
        from app.articles.photo_service import PhotoService
        ps = PhotoService(db)
        await ps.select_photos_for_batch(batch.id, payload.photo_ids)

    # 读取照片信息
    photo_descriptions = ""
    photo_object_names: list = []
    photo_ids = payload.photo_ids or []
    if photo_ids:
        from app.articles.photo_service import PhotoService
        ps = PhotoService(db)
        photos = await ps.get_batch_photos(batch.id)
        if photos:
            desc_parts = []
            for i, p in enumerate(photos):
                photo_object_names.append(p.object_name)
                tag_str = ", ".join(p.tags) if p.tags else ""
                desc_parts.append(f"【照片 {i + 1}：{p.filename} | 标签：{tag_str}】\n{p.description or ''}")
            photo_descriptions = "\n\n---\n\n".join(desc_parts)

    # 生成模仿文章
    result = await imitate_article(
        topic=payload.topic,
        style_analysis=style,
        knowledge_context=knowledge,
        photo_descriptions=photo_descriptions,
        photo_object_names=photo_object_names or None,
        min_words=payload.word_count_min,
        max_words=payload.word_count_max,
    )

    # 存入数据库
    from app.articles.models import Article
    article = Article(
        batch_id=batch.id,
        title=result["title"],
        content=result["content"],
        word_count=result["word_count"],
        angle="imitate",
        image_placement=result.get("image_placement"),
        status="draft",
        user_id=cu.id,
    )
    db.add(article)
    batch.generated_count = 1
    batch.status = "completed"
    await db.commit()
    await db.refresh(article)

    return ImitateResponse(
        batch_id=batch.id,
        article=ArticleDetailResponse.model_validate(article),
    )


# ============================================================
# Photo Library — 照片库管理
# ============================================================

@router.post("/photos/upload", response_model=PhotoUploadResponse, status_code=201)
async def photo_library_upload(
    file: UploadFile = File(...),
    db: DbDep = None,
    cu: WriteDep = None,
):
    """上传照片到照片库，Vision AI 自动生成标签和描述"""
    allowed_types = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}
    content_type = file.content_type or "image/jpeg"
    if content_type not in allowed_types:
        raise HTTPException(400, f"不支持的图片格式: {content_type}，仅支持 JPEG/PNG/WebP/HEIC")

    data = await file.read()
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(400, f"图片 {file.filename} 超过 10MB 限制")

    from app.articles.photo_service import PhotoService
    svc = PhotoService(db)
    result = await svc.upload_photo(
        file.filename or "photo.jpg", data, content_type, cu.id
    )
    return result


@router.get("/photos", response_model=PaginatedResponse[PhotoResponse])
async def list_photos(
    db: DbDep,
    cu: AuthDep,
    page: int = _PAGE,
    page_size: int = _PAGE_SIZE,
    tag: str | None = Query(default=None, description="按标签筛选"),
):
    """照片列表（分页 + 标签筛选）"""
    from app.articles.photo_service import PhotoService
    svc = PhotoService(db)
    items, total = await svc.list_photos(
        user_id=cu.id if cu.role != "superadmin" else None,
        page=page,
        page_size=page_size,
        tag=tag,
    )
    total_pages = (total + page_size - 1) // page_size
    return PaginatedResponse(
        items=[PhotoResponse.model_validate(p) for p in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/photos/{photo_id}", response_model=PhotoResponse)
async def get_photo_detail(
    photo_id: int,
    db: DbDep,
    cu: AuthDep,
):
    """照片详情"""
    from app.articles.photo_service import PhotoService
    svc = PhotoService(db)
    photo = await svc.get_photo(photo_id)
    if not photo:
        raise HTTPException(404, "照片不存在")
    return PhotoResponse.model_validate(photo)


@router.put("/photos/{photo_id}", response_model=PhotoResponse)
async def update_photo_tags(
    photo_id: int,
    payload: PhotoUpdate,
    db: DbDep,
    cu: WriteDep,
):
    """更新照片标签"""
    from app.articles.photo_service import PhotoService
    svc = PhotoService(db)
    photo = await svc.update_photo(photo_id, payload.tags)
    if not photo:
        raise HTTPException(404, "照片不存在")
    return PhotoResponse.model_validate(photo)


@router.delete("/photos/{photo_id}")
async def delete_photo(
    photo_id: int,
    db: DbDep,
    cu: WriteDep,
):
    """删除照片（MinIO + 数据库）"""
    from app.articles.photo_service import PhotoService
    svc = PhotoService(db)
    ok = await svc.delete_photo(photo_id)
    if not ok:
        raise HTTPException(404, "照片不存在")
    return {"ok": True}


@router.post("/photos/{photo_id}/suggest-tags")
async def suggest_photo_tags(
    photo_id: int,
    db: DbDep,
    cu: WriteDep,
):
    """重新为照片生成 AI 标签建议"""
    from app.articles.photo_service import PhotoService
    svc = PhotoService(db)
    try:
        tags = await svc.suggest_tags(photo_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"photo_id": photo_id, "tags": tags}


@router.post("/photos/match", response_model=PhotoMatchResponse)
async def match_photos(
    payload: PhotoMatchRequest,
    db: DbDep,
    cu: AuthDep,
):
    """根据文章主题智能匹配照片库中的照片（LLM 标签匹配 + 防重复窗口）"""
    from app.articles.photo_service import PhotoService
    svc = PhotoService(db)
    matches = await svc.match_photos(payload.topic, payload.count, payload.exclude_days)
    return PhotoMatchResponse(matches=matches)


@router.post("/photos/match-weighted", response_model=WeightedPhotoMatchResponse)
async def match_photos_weighted(
    payload: WeightedPhotoMatchRequest,
    db: DbDep,
    cu: AuthDep,
):
    """权重配图：结合主题与写作模板指令，LLM 语义分 + 规则权重加权匹配照片"""
    from app.articles.photo_service import PhotoService
    svc = PhotoService(db)
    matches = await svc.match_photos_weighted(
        topic=payload.topic,
        template_instruction=payload.template_instruction or "",
        count=payload.count,
        exclude_days=payload.exclude_days,
    )
    return WeightedPhotoMatchResponse(matches=matches)


@router.post("/batches/{batch_id}/select-photos")
async def select_photos_for_batch(
    batch_id: int,
    payload: BatchPhotoSelectRequest,
    db: DbDep,
    cu: WriteDep,
):
    """将照片库中的照片关联到批次（替代手动上传）"""
    from app.articles.photo_service import PhotoService
    svc = PhotoService(db)
    records = await svc.select_photos_for_batch(batch_id, payload.photo_ids)
    return {"ok": True, "count": len(records), "photo_ids": payload.photo_ids}


# ============================================================
# Hot Topics — 今日热点与智能选题推荐
# ============================================================

@router.get("/hot-topics")
async def get_hot_topics_api(
    cu: AuthDep,
    refresh: bool = Query(default=False, description="强制刷新缓存"),
):
    """获取四平台热榜（百度/微博/知乎/头条，30 分钟缓存）"""
    from app.articles.hot_topics import get_hot_topics

    return await get_hot_topics(refresh=refresh)


@router.post("/hot-topics/recommend")
async def recommend_hot_titles(
    db: DbDep,
    cu: AuthDep,
    max_topics: int = Query(default=8, ge=1, le=20, description="最多推荐选题数"),
    company_direction: str = Query(default="", description="公司创作方向（自由文本）"),
):
    """结合知识库内容与公司方向，从今日热点中智能推荐文章选题与标题"""
    from app.articles.hot_topics import recommend_titles

    return await recommend_titles(db, max_topics=max_topics, company_direction=company_direction)


@router.post("/topics/generate", response_model=TopicGenerateResponse)
async def generate_topics(
    payload: TopicGenerateRequest,
    db: DbDep,
    cu: AuthDep,
):
    """智能选题：热点 + 知识库 + 公司方向 → 推荐选题列表（供文章创作第 1 步使用）"""
    from app.articles.hot_topics import recommend_titles

    result = await recommend_titles(
        db,
        max_topics=payload.max_topics,
        company_direction=payload.company_direction,
    )
    return TopicGenerateResponse(
        recommendations=[TopicRecommendItem(**r) for r in result["recommendations"]],
        hot_count=result.get("hot_count", 0),
        message=result.get("message", ""),
    )


# ============================================================
# Photo Proxy — MinIO 图片代理（必须放在所有 /photos 路由的最后）
# ============================================================

@router.get("/photos/{object_name:path}")
async def get_photo(
    object_name: str,
    cu: AuthDep,
):
    """代理 MinIO 照片，前端可直接用此 URL 显示图片

    支持路径格式: article-photos/{batch_id}/{filename}
    """

    from app.core.minio_client import get_minio_client

    client = get_minio_client()
    try:
        response = client.get_object("knowledge-docs", object_name)
        data = response.read()
        response.close()
        response.release_conn()

        content_type = "image/jpeg"
        if object_name.lower().endswith(".png"):
            content_type = "image/png"
        elif object_name.lower().endswith(".webp"):
            content_type = "image/webp"

        return Response(content=data, media_type=content_type)
    except Exception:
        raise HTTPException(404, f"照片不存在: {object_name}")
