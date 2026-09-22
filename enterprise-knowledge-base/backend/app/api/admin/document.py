"""后台管理 — 文档管理路由"""

import asyncio
import json
import uuid
from dataclasses import asdict
from typing import Annotated, Literal

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field

from sqlalchemy import select

from app.core.config import settings
from app.core.dependencies import DbDep, require_auth, require_permission, require_role
from app.core.logging import logger
from app.models.document import DocChunk, KnowledgeDoc
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.document import (
    ChunkResponse,
    DocumentCreate,
    DocumentDetailResponse,
    DocumentReviewAction,
    DocumentResponse,
    DocumentUpdate,
)
from app.services.document_service import DocumentService
from app.services.audit_service import log_operation_async
from app.services.text_cleaner import clean_document_text
from app.services.text_parser import parse_docx_bytes, parse_pdf_bytes, parse_text

router = APIRouter(prefix="/documents", tags=["admin-documents"])

_OP_DOC = lambda u: u.display_name or u.username or "unknown"


def _guard_department(current_user: User, target_department: str | None) -> None:
    """非 superadmin 只能把文档挂在自己部门下，不能指到别的部门"""
    if current_user.role == "superadmin":
        return
    if target_department != current_user.department:
        raise HTTPException(status_code=403, detail="不能将文档指定到其他部门")

MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB
ALLOWED_SCOPES = {"public", "customer", "internal"}
ALLOWED_CHUNK_STRATEGIES = {"fixed", "semantic", "recursive"}


@router.get("/departments")
async def list_departments(db: DbDep, cu: Annotated[User, Depends(require_auth)]) -> list[str]:
    depts: set[str] = set()
    for col in (User.department, KnowledgeDoc.department):
        result = await db.execute(
            select(col).where(col.isnot(None)).where(col != "").distinct()
        )
        for row in result.all():
            value = (row[0] or "").strip()
            if value:
                depts.add(value)
    return sorted(depts)


class ContentUpload(BaseModel):
    content: str = Field(max_length=5_000_000)
    file_type: Literal["md", "txt", "pdf", "docx"] = "txt"
    auto_clean: bool = True


class ParseRequest(BaseModel):
    content: str
    file_type: Literal["md", "txt", "pdf", "docx"] = "txt"


FILE_EXT_TO_TYPE: dict[str, str] = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".md": "md",
    ".txt": "txt",
}

ALLOWED_EXTENSIONS = set(FILE_EXT_TO_TYPE.keys())
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/markdown",
    "text/plain",
    "application/octet-stream",
    "text/x-markdown",
}


@router.get("", response_model=PaginatedResponse[DocumentResponse])
async def list_docs(
    db: DbDep, cu: Annotated[User, Depends(require_auth)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category_id: int | None = None,
    scope: str | None = None,
    status: str | None = None,
):
    items, total = await DocumentService(db).list(
        cu, page=page, page_size=page_size,
        category_id=category_id, scope=scope, status=status,
    )
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if total > 0 else 0,
    }


@router.post("", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def create_doc(
    payload: DocumentCreate, db: DbDep,
    cu: Annotated[User, Depends(require_permission("write"))],
) -> DocumentResponse:
    _guard_department(cu, payload.department or cu.department)
    doc = await DocumentService(db).create(payload, cu)
    asyncio.create_task(log_operation_async(
        operator_id=cu.id, operator_name=_OP_DOC(cu),
        operation_type="create", target_table="knowledge_doc", target_id=doc.id,
        content_after={"title": payload.title, "scope": payload.scope},
    ))
    return doc  # type: ignore[return-value]


@router.post("/parse")
async def parse_content(
    payload: ParseRequest, db: DbDep,
    _w: Annotated[User, Depends(require_permission("write"))],
) -> dict:
    result = parse_text(payload.content, payload.file_type)
    return {"plain_text": result.plain_text, "word_count": result.word_count}


@router.post("/{doc_id}/content", response_model=DocumentResponse)
async def upload_content(
    doc_id: int, payload: ContentUpload, db: DbDep,
    cu: Annotated[User, Depends(require_permission("write"))],
) -> DocumentResponse:
    try:
        doc = await DocumentService(db).update_content(
            doc_id, payload.content, payload.file_type, cu, auto_clean=payload.auto_clean
        )
    except PermissionError:
        raise HTTPException(status_code=403, detail="Not authorized")
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    asyncio.create_task(log_operation_async(
        operator_id=cu.id, operator_name=_OP_DOC(cu),
        operation_type="update", target_table="knowledge_doc", target_id=doc_id,
        content_after={"file_type": payload.file_type, "auto_clean": payload.auto_clean},
    ))
    return doc  # type: ignore[return-value]


@router.post("/{doc_id}/chunk")
async def chunk_document(
    doc_id: int, db: DbDep,
    cu: Annotated[User, Depends(require_permission("write"))],
) -> dict:
    try:
        result = await DocumentService(db).chunk(doc_id, cu)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Not authorized")
    asyncio.create_task(log_operation_async(
        operator_id=cu.id, operator_name=_OP_DOC(cu),
        operation_type="update", target_table="knowledge_doc", target_id=doc_id,
        content_after={"chunk_count": result.get("chunk_count", 0)},
    ))
    return result


class RechunkPayload(BaseModel):
    chunk_strategy: str = "recursive"
    chunk_size: int = Field(default=512, ge=128, le=2048)
    chunk_overlap: int = Field(default=80, ge=0, le=1024)


@router.post("/{doc_id}/rechunk")
async def rechunk_document(
    doc_id: int, payload: RechunkPayload, db: DbDep,
    cu: Annotated[User, Depends(require_permission("write"))],
) -> dict:
    doc = await db.get(KnowledgeDoc, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if cu.role != "superadmin" and doc.department != cu.department:
        raise HTTPException(status_code=403, detail="Not authorized")
    if doc.plain_text is None:
        raise HTTPException(status_code=400, detail="文档无内容，请先编辑内容")

    doc.chunk_strategy = payload.chunk_strategy
    doc.chunk_size = payload.chunk_size
    doc.chunk_overlap = payload.chunk_overlap

    result = await DocumentService(db).chunk(doc_id, cu)

    from app.retrieval.sync import deindex_document as _deindex

    asyncio.create_task(_deindex(doc_id))
    if doc.status == "online" and doc.review_status == "approved":
        asyncio.create_task(_resync_after_rechunk(doc_id))

    asyncio.create_task(log_operation_async(
        operator_id=cu.id, operator_name=_OP_DOC(cu),
        operation_type="update", target_table="knowledge_doc", target_id=doc_id,
        content_after={
            "chunk_count": result.get("chunk_count", 0),
            "chunk_strategy": payload.chunk_strategy,
            "chunk_size": payload.chunk_size,
        },
    ))
    return {**result, "message": "分块已重建，后台正在重新向量化"}


@router.get("/{doc_id}/chunks", response_model=list[ChunkResponse])
async def list_chunks(
    doc_id: int, db: DbDep,
    cu: Annotated[User, Depends(require_auth)],
) -> list[ChunkResponse]:
    doc = await db.get(KnowledgeDoc, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if cu.role != "superadmin" and doc.department != cu.department:
        raise HTTPException(status_code=403, detail="Not authorized")

    stmt = select(DocChunk).where(DocChunk.doc_id == doc_id).order_by(DocChunk.chunk_index)
    result = await db.execute(stmt)
    return list(result.scalars())


@router.post("/{doc_id}/resync")
async def resync_document(
    doc_id: int, db: DbDep,
    cu: Annotated[User, Depends(require_permission("write"))],
) -> dict:
    from app.retrieval.sync import sync_document

    doc = await db.get(KnowledgeDoc, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if cu.role != "superadmin" and doc.department != cu.department:
        raise HTTPException(status_code=403, detail="Not authorized")
    if doc.status != "online":
        raise HTTPException(status_code=400, detail="仅已上线文档可重新向量化")
    if doc.chunk_count == 0:
        raise HTTPException(status_code=400, detail="文档暂无切片，请先执行分块")

    count = await sync_document(db, doc_id)
    asyncio.create_task(log_operation_async(
        operator_id=cu.id, operator_name=_OP_DOC(cu),
        operation_type="update", target_table="knowledge_doc", target_id=doc_id,
        content_after={"resynced": count},
    ))
    return {"synced": count}


@router.get("/{doc_id}", response_model=DocumentDetailResponse)
async def get_document_detail(
    doc_id: int, db: DbDep,
    cu: Annotated[User, Depends(require_auth)],
) -> DocumentDetailResponse:
    doc = await db.get(KnowledgeDoc, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    if cu.role != "superadmin" and cu.department and doc.department != cu.department:
        raise HTTPException(status_code=403, detail="Not authorized")
    return doc  # type: ignore[return-value]


@router.post("/{doc_id}/review", response_model=DocumentResponse)
async def review_document(
    doc_id: int, payload: DocumentReviewAction, db: DbDep,
    cu: Annotated[User, Depends(require_role("superadmin", "dept_admin"))],
) -> DocumentResponse:
    try:
        doc = await DocumentService(db).review(doc_id, payload.action, cu, comment=payload.comment)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Not authorized to review")
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found")
    asyncio.create_task(log_operation_async(
        operator_id=cu.id, operator_name=_OP_DOC(cu),
        operation_type="update", target_table="knowledge_doc", target_id=doc_id,
        content_after={"action": payload.action, "comment": payload.comment},
    ))
    return doc  # type: ignore[return-value]


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_doc(
    doc_id: int, db: DbDep,
    cu: Annotated[User, Depends(require_permission("write"))],
) -> None:
    try:
        deleted = await DocumentService(db).delete(doc_id, cu)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Not authorized")
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found")
    asyncio.create_task(log_operation_async(
        operator_id=cu.id, operator_name=_OP_DOC(cu),
        operation_type="delete", target_table="knowledge_doc", target_id=doc_id,
    ))


class DocBulkIds(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=200)


class BulkCleanPayload(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=200)
    use_llm: bool = False


@router.post("/bulk-clean")
async def bulk_clean_docs(
    payload: BulkCleanPayload, db: DbDep,
    cu: Annotated[User, Depends(require_permission("write"))],
) -> dict:
    cleaned, failed = 0, []
    for did in payload.ids:
        try:
            result = await DocumentService(db).clean(did, cu, use_llm=payload.use_llm)
        except PermissionError:
            failed.append({"id": did, "reason": "permission denied"})
            continue
        except ValueError:
            failed.append({"id": did, "reason": "no content"})
            continue
        if result is None:
            failed.append({"id": did, "reason": "not found"})
            continue
        cleaned += 1
        asyncio.create_task(log_operation_async(
            operator_id=cu.id, operator_name=_OP_DOC(cu),
            operation_type="update", target_table="knowledge_doc", target_id=did,
            content_after={"action": "clean"},
        ))
    return {"cleaned": cleaned, "failed": failed}


class CleanOptions(BaseModel):
    use_llm: bool = False


@router.post("/{doc_id}/clean")
async def clean_document(
    doc_id: int, db: DbDep,
    cu: Annotated[User, Depends(require_permission("write"))],
    payload: CleanOptions = Body(default_factory=CleanOptions),
) -> dict:
    try:
        result = await DocumentService(db).clean(doc_id, cu, use_llm=payload.use_llm)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Not authorized")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    if result is None:
        raise HTTPException(status_code=404, detail="Document not found")
    doc, clean_result = result
    asyncio.create_task(log_operation_async(
        operator_id=cu.id, operator_name=_OP_DOC(cu),
        operation_type="update", target_table="knowledge_doc", target_id=doc_id,
        content_after={"action": "clean", "use_llm": payload.use_llm,
                       "report": asdict(clean_result.report)},
    ))
    return {
        "id": doc.id,
        "clean_status": doc.clean_status,
        "word_count": doc.word_count,
        "chunk_count": doc.chunk_count,
        "report": asdict(clean_result.report),
    }


@router.post("/bulk-delete")
async def bulk_delete_docs(
    payload: DocBulkIds, db: DbDep,
    cu: Annotated[User, Depends(require_permission("write"))],
) -> dict:
    deleted, failed = 0, []
    for did in payload.ids:
        try:
            ok = await DocumentService(db).delete(did, cu)
        except PermissionError:
            failed.append({"id": did, "reason": "permission denied"})
            continue
        if not ok:
            failed.append({"id": did, "reason": "not found"})
            continue
        deleted += 1
        asyncio.create_task(log_operation_async(
            operator_id=cu.id, operator_name=_OP_DOC(cu),
            operation_type="delete", target_table="knowledge_doc", target_id=did,
        ))
    return {"deleted": deleted, "failed": failed}


@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_file(
    db: DbDep,
    cu: Annotated[User, Depends(require_permission("write"))],
    file: UploadFile = File(...),
    title: str = Form("未命名文档"),
    category_id: int = Form(1),
    scope: str = Form("public"),
    chunk_strategy: str = Form("recursive"),
    department: str | None = Form(None),
    auto_clean: bool = Form(True),
) -> DocumentResponse:
    if scope not in ALLOWED_SCOPES:
        raise HTTPException(status_code=400, detail=f"不支持的知识范围: {scope}")
    if chunk_strategy not in ALLOWED_CHUNK_STRATEGIES:
        raise HTTPException(status_code=400, detail=f"不支持的分块策略: {chunk_strategy}")

    dept = department or cu.department
    _guard_department(cu, dept)

    ext = ""
    if file.filename and "." in file.filename:
        ext = "." + file.filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {ext}，仅支持 pdf, docx, md, txt")

    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail="文件大小不能超过 50MB")
    if not content:
        raise HTTPException(status_code=400, detail="文件内容为空")

    file_type = FILE_EXT_TO_TYPE.get(ext, "txt")
    doc_title = title if title and title != "未命名文档" else (file.filename or "未命名文档")

    # 二进制类型走专用解析器，文本类型按编码解码
    if file_type == "pdf":
        raw_source = parse_pdf_bytes(content).plain_text
    elif file_type == "docx":
        raw_source = parse_docx_bytes(content).plain_text
    else:
        raw_source = content.decode("utf-8", errors="ignore")

    # 自动清洗：先清洗源文本再解析入库，raw_text 保留清洗前原文
    if auto_clean:
        clean_result = clean_document_text(raw_source)
        cleaned_text = clean_result.text
        clean_status = "cleaned"
        clean_report = json.dumps(asdict(clean_result.report), ensure_ascii=False)
    else:
        cleaned_text = raw_source
        clean_status = "skipped"
        clean_report = None

    if file_type in ("pdf", "docx"):
        plain_text = cleaned_text
        word_count = len(cleaned_text)
    else:
        parsed = parse_text(cleaned_text, file_type)
        plain_text = parsed.plain_text
        word_count = parsed.word_count

    # 对象存储尽力而为：MinIO 不可用不应阻断文档入库（正文已解析，可用于检索）
    object_name = f"{uuid.uuid4().hex}{ext}"
    file_path = ""
    try:
        from app.core.minio_client import ensure_bucket, upload_file as minio_upload

        ensure_bucket(settings.minio_bucket)
        minio_upload(
            settings.minio_bucket,
            object_name,
            content,
            file.content_type or "application/octet-stream",
        )
        file_path = object_name
    except Exception:
        logger.warning("minio_upload_failed", exc_info=True)

    doc = KnowledgeDoc(
        category_id=category_id,
        title=doc_title,
        scope=scope,
        chunk_strategy=chunk_strategy,
        file_type=file_type,
        file_path=file_path,
        file_size=len(content),
        plain_text=plain_text,
        word_count=word_count,
        department=dept,
        raw_text=raw_source,
        clean_status=clean_status,
        clean_report=clean_report,
    )
    db.add(doc)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    await db.refresh(doc)

    await DocumentService(db).chunk(doc.id, cu)

    asyncio.create_task(log_operation_async(
        operator_id=cu.id, operator_name=_OP_DOC(cu),
        operation_type="create", target_table="knowledge_doc", target_id=doc.id,
        content_after={"title": doc_title, "file_type": file_type, "file_size": len(content)},
    ))
    return doc  # type: ignore[return-value]


async def _resync_after_rechunk(doc_id: int) -> None:
    from app.core.database import AsyncSessionLocal
    from app.retrieval.sync import sync_document

    await asyncio.sleep(2)
    for attempt in range(3):
        try:
            async with AsyncSessionLocal() as db:
                await sync_document(db, doc_id)
            return
        except Exception:
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)
