"""后台管理 — 多源内容管理路由（列表/详情/上下架/删除/同步触发/去重合并/状态日志）。"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.collector.registry import get_collector
from app.core.dependencies import DbDep, require_permission
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.source_content import (
    MergeRequest,
    SourceContentDetailResponse,
    SourceContentResponse,
    SourceLinkResponse,
    StatusUpdateRequest,
    SyncLogResponse,
    SyncStateResponse,
    SyncTriggerRequest,
    SyncTriggerResponse,
)
from app.services.source_content_admin import SourceContentAdminService

router = APIRouter(prefix="/source-contents", tags=["admin-source-contents"])

ReadUser = Annotated[User, Depends(require_permission("read"))]
WriteUser = Annotated[User, Depends(require_permission("write"))]
DeleteUser = Annotated[User, Depends(require_permission("delete"))]


def _paginate(items: list, total: int, page: int, page_size: int) -> dict:
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size,
    }


@router.get("", response_model=PaginatedResponse[SourceContentResponse])
async def list_source_contents(
    db: DbDep,
    cu: ReadUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    source_type: str | None = None,
    status: str | None = None,
    search: str | None = None,
):
    svc = SourceContentAdminService(db)
    items, total = await svc.list(
        page=page, page_size=page_size, source_type=source_type, status=status, search=search
    )
    return _paginate([SourceContentResponse.model_validate(i) for i in items], total, page, page_size)


@router.get("/sync-states", response_model=list[SyncStateResponse])
async def list_sync_states(db: DbDep, cu: ReadUser):
    svc = SourceContentAdminService(db)
    return [SyncStateResponse.model_validate(s) for s in await svc.get_sync_states()]


@router.get("/sync-logs", response_model=PaginatedResponse[SyncLogResponse])
async def list_sync_logs(
    db: DbDep,
    cu: ReadUser,
    platform: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    svc = SourceContentAdminService(db)
    items, total = await svc.get_sync_logs(platform=platform, page=page, page_size=page_size)
    return _paginate([SyncLogResponse.model_validate(i) for i in items], total, page, page_size)


@router.post("/sync", response_model=SyncTriggerResponse)
async def trigger_sync(db: DbDep, cu: WriteUser, payload: SyncTriggerRequest):
    svc = SourceContentAdminService(db)
    summary = await svc.trigger_sync(payload.platforms)
    return SyncTriggerResponse(
        total_fetched=summary.total_fetched,
        total_ingested=summary.total_ingested,
        failed_platforms=summary.failed_platforms,
        all_ok=summary.all_ok,
    )


@router.post("/merge", response_model=SourceContentResponse)
async def merge_documents(db: DbDep, cu: WriteUser, payload: MergeRequest):
    svc = SourceContentAdminService(db)
    try:
        primary = await svc.merge(payload.primary_doc_id, payload.duplicate_doc_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if primary is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    return SourceContentResponse.model_validate(primary)


@router.get("/{doc_id}", response_model=SourceContentDetailResponse)
async def get_source_content(db: DbDep, cu: ReadUser, doc_id: int):
    svc = SourceContentAdminService(db)
    doc = await svc.get(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    resp = SourceContentDetailResponse.model_validate(doc)
    resp.source_links = [SourceLinkResponse.model_validate(link) for link in await svc.get_source_links(doc_id)]
    return resp


@router.get("/{doc_id}/preview-url")
async def get_preview_url(db: DbDep, cu: ReadUser, doc_id: int) -> dict:
    """返回文章可跳转链接：永久链接直接返回；草稿来源实时解析微信预览链接。"""
    svc = SourceContentAdminService(db)
    doc = await svc.get(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    if doc.original_url:
        return {"url": doc.original_url}
    for link in await svc.get_source_links(doc_id):
        if link.platform == "wechat" and link.external_id.startswith("draft:"):
            parts = link.external_id.split(":")
            if len(parts) == 3 and parts[2].isdigit():
                url = await get_collector("wechat").resolve_draft_url(parts[1], int(parts[2]))
                if url:
                    return {"url": url}
    raise HTTPException(status_code=404, detail="无可用预览链接")


@router.put("/{doc_id}/status", response_model=SourceContentResponse)
async def update_status(db: DbDep, cu: WriteUser, doc_id: int, payload: StatusUpdateRequest):
    svc = SourceContentAdminService(db)
    doc = await svc.set_status(doc_id, payload.status)
    if doc is None:
        raise HTTPException(status_code=404, detail="文档不存在")
    return SourceContentResponse.model_validate(doc)


@router.delete("/{doc_id}")
async def delete_source_content(db: DbDep, cu: DeleteUser, doc_id: int):
    svc = SourceContentAdminService(db)
    if not await svc.delete(doc_id):
        raise HTTPException(status_code=404, detail="文档不存在")
    return {"success": True}
