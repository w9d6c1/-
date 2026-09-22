"""短视频文案 — REST API 路由

挂载在 /api/admin/copywriting 下。
"""

import time
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from app.copywriting.hot_douyin import fetch_douyin_hot
from app.copywriting.hot_manual import ManualHotService
from app.copywriting.material_service import MaterialService, fetch_link_content
from app.copywriting.recommend import recommend_copy_titles
from app.copywriting.schemas import (
    HotManualCreate,
    HotManualItemResponse,
    LinkImportRequest,
    LinkImportResponse,
    ScriptGenerateRequest,
    ScriptResponse,
    ScriptUpdate,
    TitleRecommendItem,
    TitlesRecommendRequest,
    TitlesRecommendResponse,
)
from app.copywriting.script_service import ScriptService, build_script_body, build_script_pdf
from app.core.dependencies import DbDep, require_auth, require_permission
from app.models.user import User
from app.schemas.common import PaginatedResponse

router = APIRouter(prefix="/copywriting", tags=["admin-copywriting"])

AuthDep = Annotated[User, Depends(require_auth)]
WriteDep = Annotated[User, Depends(require_permission("write"))]

_PAGE = Query(1, ge=1, description="页码")
_PAGE_SIZE = Query(20, ge=1, le=100, description="每页条数")


# ============================================================
# 热点 — 抖音热搜 + 手动热榜
# ============================================================

@router.get("/hot-topics")
async def get_hot_topics(
    db: DbDep,
    cu: AuthDep,
    refresh: bool = Query(default=False, description="强制刷新抖音热搜缓存"),
):
    """抖音热搜 + 手动热榜聚合（含视频跳转链接与封面图）"""
    douyin = await fetch_douyin_hot(refresh=refresh)
    svc = ManualHotService(db)
    manual = await svc.list_items(user_id=cu.id if cu.role != "superadmin" else None)
    manual_items = [
        {
            "id": m.id,
            "rank": m.sort_order or i + 1,
            "title": m.title,
            "hot_value": 0,
            "url": m.url or "",
            "cover": "",
            "source": m.source,
        }
        for i, m in enumerate(manual)
    ]
    return {
        "sources": {
            "douyin": {"label": "抖音热搜", "items": douyin},
            "manual": {"label": "手动热榜", "items": manual_items},
        },
        "updated_at": time.time(),
    }


@router.post("/hot-topics/manual", response_model=HotManualItemResponse, status_code=201)
async def create_manual_hot(
    payload: HotManualCreate,
    db: DbDep,
    cu: WriteDep,
):
    """新增手动热榜条目（馋妈妈等）"""
    svc = ManualHotService(db)
    obj = await svc.create_item(
        user_id=cu.id,
        title=payload.title,
        url=payload.url,
        source=payload.source,
        sort_order=payload.sort_order,
    )
    return HotManualItemResponse.model_validate(obj)


@router.delete("/hot-topics/manual/{item_id}")
async def delete_manual_hot(
    item_id: int,
    db: DbDep,
    cu: WriteDep,
):
    """删除手动热榜条目"""
    svc = ManualHotService(db)
    ok = await svc.delete_item(item_id, cu.id)
    if not ok:
        raise HTTPException(404, "热榜条目不存在")
    return {"ok": True}


@router.delete("/hot-topics/manual")
async def clear_manual_hot(
    db: DbDep,
    cu: WriteDep,
):
    """清空当前用户手动热榜"""
    svc = ManualHotService(db)
    deleted = await svc.clear_all(cu.id)
    return {"ok": True, "deleted": deleted}


# ============================================================
# 文案标题推荐
# ============================================================

@router.post("/titles/recommend", response_model=TitlesRecommendResponse)
async def recommend_titles(
    payload: TitlesRecommendRequest,
    db: DbDep,
    cu: AuthDep,
):
    """热点 + 知识库 → 今天要拍的文案标题（含视频跳转链接）"""
    douyin = await fetch_douyin_hot()
    hot_items: list[dict] = []
    for it in douyin:
        hot_items.append({
            "rank": it["rank"],
            "title": it["title"],
            "url": it["url"],
            "cover": it.get("cover", ""),
        })

    if payload.include_manual:
        svc = ManualHotService(db)
        manual = await svc.list_items(user_id=cu.id if cu.role != "superadmin" else None)
        for i, m in enumerate(manual):
            hot_items.append({
                "rank": m.sort_order or i + 1,
                "title": m.title,
                "url": m.url or "",
                "cover": "",
            })

    recs = await recommend_copy_titles(db, hot_items, count=payload.count)

    # 按 hot_word 与热榜标题匹配，回填封面图（LLM 可能微调热点词，做包含式匹配）
    hot_title_to_cover = {}
    for it in hot_items:
        hot_title_to_cover[it["title"]] = it.get("cover", "")

    for r in recs:
        word = r.get("hot_word", "").strip()
        if word:
            cover = hot_title_to_cover.get(word, "")
            if not cover:
                for title, c in hot_title_to_cover.items():
                    if c and (word in title or title in word):
                        cover = c
                        break
            r["cover"] = cover

    return TitlesRecommendResponse(
        recommendations=[TitleRecommendItem(**r) for r in recs],
        hot_count=len(hot_items),
    )


# ============================================================
# 素材 — 文件上传 / 链接导入
# ============================================================

@router.post("/materials/upload")
async def upload_materials(
    db: DbDep,
    cu: WriteDep,
    files: list[UploadFile] = File(..., min_length=1, max_length=10),
):
    """上传素材（照片/文字/视频）→ 返回每份的类型与可读描述"""
    svc = MaterialService(db)
    entries: list[dict] = []
    for f in files:
        data = await f.read()
        if len(data) > 20 * 1024 * 1024:
            entries.append({
                "ok": False, "filename": f.filename or "file",
                "type": "other", "description": "文件超过 20MB 限制", "object_name": None,
            })
            continue
        result = await svc.upload_file(
            f.filename or "file", data, f.content_type or "application/octet-stream", cu.id
        )
        entries.append(result)
    return {"entries": entries, "count": len(entries)}


@router.post("/materials/import-link", response_model=LinkImportResponse)
async def import_link(
    payload: LinkImportRequest,
    cu: WriteDep,
):
    """导入链接，抓取正文内容作为素材"""
    try:
        content = await fetch_link_content(payload.url)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        raise HTTPException(400, f"链接抓取失败: {e}") from e
    return LinkImportResponse(
        url=payload.url,
        content=content,
        content_length=len(content),
    )


# ============================================================
# 脚本 — 生成 + CRUD
# ============================================================

@router.post("/scripts/generate", response_model=ScriptResponse, status_code=201)
async def generate_script(
    payload: ScriptGenerateRequest,
    db: DbDep,
    cu: WriteDep,
):
    """按标题+热点+素材+知识库生成口播稿与分镜头脚本，并保存"""
    svc = ScriptService(db)
    material_notes = ""
    if payload.material_notes:
        material_notes = payload.material_notes
    elif payload.material_entries:
        material_notes = MaterialService.summarize(payload.material_entries)

    try:
        data = await svc.generate_script(
            user_id=cu.id,
            title=payload.title,
            hot_word=payload.hot_word,
            hot_url=payload.hot_url,
            requirement=payload.requirement or "",
            material_notes=material_notes,
        )
    except Exception as exc:
        raise HTTPException(500, f"脚本生成失败: {exc}") from exc

    obj = await svc.create_script(data)
    return ScriptResponse.model_validate(obj)


@router.get("/scripts", response_model=PaginatedResponse[ScriptResponse])
async def list_scripts(
    db: DbDep,
    cu: AuthDep,
    page: int = _PAGE,
    page_size: int = _PAGE_SIZE,
):
    """脚本列表（分页）"""
    svc = ScriptService(db)
    items, total = await svc.list_scripts(
        user_id=cu.id if cu.role != "superadmin" else None,
        page=page,
        page_size=page_size,
    )
    total_pages = (total + page_size - 1) // page_size
    return PaginatedResponse(
        items=[ScriptResponse.model_validate(s) for s in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/scripts/{script_id}", response_model=ScriptResponse)
async def get_script(
    script_id: int,
    db: DbDep,
    cu: AuthDep,
):
    """脚本详情"""
    svc = ScriptService(db)
    obj = await svc.get_script(script_id)
    if not obj:
        raise HTTPException(404, "脚本不存在")
    return ScriptResponse.model_validate(obj)


@router.put("/scripts/{script_id}", response_model=ScriptResponse)
async def update_script(
    script_id: int,
    payload: ScriptUpdate,
    db: DbDep,
    cu: WriteDep,
):
    """编辑脚本（口播稿/分镜头可改）"""
    svc = ScriptService(db)
    data = payload.model_dump(exclude_unset=True)
    obj = await svc.update_script(script_id, data)
    if not obj:
        raise HTTPException(404, "脚本不存在")
    return ScriptResponse.model_validate(obj)


@router.delete("/scripts/{script_id}")
async def delete_script(
    script_id: int,
    db: DbDep,
    cu: WriteDep,
):
    """删除脚本"""
    svc = ScriptService(db)
    ok = await svc.delete_script(script_id, cu.id)
    if not ok:
        raise HTTPException(404, "脚本不存在")
    return {"ok": True}


@router.get("/scripts/{script_id}/export")
async def export_script(
    script_id: int,
    db: DbDep,
    cu: AuthDep,
    format: str = Query("md", pattern="^(md|txt|html|docx|pdf)$", description="导出格式"),
):
    """导出脚本（MD / TXT / HTML / DOCX / PDF）"""
    from urllib.parse import quote

    from fastapi.responses import Response

    from app.articles.publisher import export_docx, export_html, export_markdown

    svc = ScriptService(db)
    script = await svc.get_script(script_id)
    if not script:
        raise HTTPException(404, "脚本不存在")

    if format == "docx":
        data = export_docx(script.title, build_script_body(script, table=False))
        filename = f"{script.title}.docx"
        content_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif format == "pdf":
        data = build_script_pdf(script)
        filename = f"{script.title}.pdf"
        content_type = "application/pdf"
    elif format == "html":
        data = export_html(script.title, build_script_body(script, table=True))
        filename = f"{script.title}.html"
        content_type = "text/html; charset=utf-8"
    elif format == "txt":
        body = build_script_body(script, table=False)
        text = f"{script.title}\n\n{body}".replace("**", "").replace("## ", "")
        data = text.encode("utf-8")
        filename = f"{script.title}.txt"
        content_type = "text/plain; charset=utf-8"
    else:
        data = export_markdown(script.title, build_script_body(script, table=True))
        filename = f"{script.title}.md"
        content_type = "text/markdown; charset=utf-8"

    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
        },
    )
