"""后台管理 — FAQ 管理路由"""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.core.dependencies import DbDep, require_auth, require_permission
from app.models.user import User
from app.schemas.common import PaginatedResponse
from app.schemas.faq import FAQBulkImport, FAQCreate, FAQResponse, FAQReviewAction, FAQUpdate
from app.services.audit_service import log_operation_async
from app.services.faq_service import FAQService

router = APIRouter(prefix="/faqs", tags=["admin-faqs"])

_OP_NAME = lambda u: u.display_name or u.username or "unknown"


@router.get("", response_model=PaginatedResponse[FAQResponse])
async def list_faqs(
    db: DbDep, current_user: Annotated[User, Depends(require_auth)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
) -> PaginatedResponse[FAQResponse]:
    items, total = await FAQService(db).list(current_user, page, page_size)
    total_pages = max(1, (total + page_size - 1) // page_size) if total > 0 else 0
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size, total_pages=total_pages)


@router.get("/{faq_id}", response_model=FAQResponse)
async def get_faq(
    faq_id: int, db: DbDep,
    _u: Annotated[User, Depends(require_auth)],
) -> FAQResponse:
    from app.models.faq import KnowledgeFAQ

    faq = await db.get(KnowledgeFAQ, faq_id)
    if faq is None:
        raise HTTPException(status_code=404, detail="FAQ not found")
    return faq  # type: ignore[return-value]


@router.post("", response_model=FAQResponse, status_code=status.HTTP_201_CREATED)
async def create_faq(
    payload: FAQCreate, db: DbDep,
    current_user: Annotated[User, Depends(require_permission("write"))],
) -> FAQResponse:
    result = await FAQService(db).create(payload, current_user)
    asyncio.create_task(log_operation_async(
        operator_id=current_user.id,
        operator_name=_OP_NAME(current_user),
        operation_type="create",
        target_table="knowledge_faq",
        target_id=result.id,
    ))
    return result  # type: ignore[return-value]


@router.post("/bulk", status_code=status.HTTP_201_CREATED)
async def bulk_import_faqs(
    payload: FAQBulkImport, db: DbDep,
    current_user: Annotated[User, Depends(require_permission("write"))],
) -> dict[str, int]:
    count = await FAQService(db).bulk_import(payload, current_user)
    asyncio.create_task(log_operation_async(
        operator_id=current_user.id,
        operator_name=_OP_NAME(current_user),
        operation_type="create",
        target_table="knowledge_faq",
    ))
    return {"imported": count}


class BulkIds(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=200)


@router.post("/bulk-delete")
async def bulk_delete_faqs(
    payload: BulkIds, db: DbDep,
    current_user: Annotated[User, Depends(require_permission("write"))],
) -> dict:
    deleted, failed = 0, []
    for fid in payload.ids:
        try:
            ok = await FAQService(db).delete(fid, current_user)
        except PermissionError:
            failed.append({"id": fid, "reason": "permission denied"})
            continue
        if not ok:
            failed.append({"id": fid, "reason": "not found"})
            continue
        deleted += 1
        asyncio.create_task(log_operation_async(
            operator_id=current_user.id, operator_name=_OP_NAME(current_user),
            operation_type="delete", target_table="knowledge_faq", target_id=fid,
        ))
    return {"deleted": deleted, "failed": failed}


@router.put("/{faq_id}", response_model=FAQResponse)
async def update_faq(
    faq_id: int, payload: FAQUpdate, db: DbDep,
    current_user: Annotated[User, Depends(require_permission("write"))],
) -> FAQResponse:
    try:
        faq = await FAQService(db).update(faq_id, payload, current_user)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Not authorized for this department")
    if faq is None:
        raise HTTPException(status_code=404, detail="FAQ not found")
    asyncio.create_task(log_operation_async(
        operator_id=current_user.id,
        operator_name=_OP_NAME(current_user),
        operation_type="update",
        target_table="knowledge_faq",
        target_id=faq_id,
    ))
    return faq  # type: ignore[return-value]


@router.delete("/{faq_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_faq(
    faq_id: int, db: DbDep,
    current_user: Annotated[User, Depends(require_permission("write"))],
) -> None:
    try:
        deleted = await FAQService(db).delete(faq_id, current_user)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Not authorized for this department")
    if not deleted:
        raise HTTPException(status_code=404, detail="FAQ not found")
    asyncio.create_task(log_operation_async(
        operator_id=current_user.id,
        operator_name=_OP_NAME(current_user),
        operation_type="delete",
        target_table="knowledge_faq",
        target_id=faq_id,
    ))


@router.post("/reload-vectors")
async def reload_faq_vectors(
    db: DbDep,
    current_user: Annotated[User, Depends(require_permission("write"))],
) -> dict:
    from app.agents.nodes.faq import refresh_faq_vectors_from_db

    count = await refresh_faq_vectors_from_db(db)
    return {"status": "ok", "loaded": count}


@router.post("/{faq_id}/submit", response_model=FAQResponse)
async def submit_for_review(
    faq_id: int, db: DbDep,
    current_user: Annotated[User, Depends(require_permission("write"))],
) -> FAQResponse:
    try:
        faq = await FAQService(db).submit_for_review(faq_id, current_user)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Not authorized for this department")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if faq is None:
        raise HTTPException(status_code=404, detail="FAQ not found")
    return faq  # type: ignore[return-value]


@router.post("/{faq_id}/approve", response_model=FAQResponse)
async def approve_faq(
    faq_id: int, db: DbDep,
    current_user: Annotated[User, Depends(require_permission("write"))],
) -> FAQResponse:
    try:
        faq = await FAQService(db).approve(faq_id, current_user)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Not authorized for this department")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if faq is None:
        raise HTTPException(status_code=404, detail="FAQ not found")
    asyncio.create_task(log_operation_async(
        operator_id=current_user.id,
        operator_name=_OP_NAME(current_user),
        operation_type="update",
        target_table="knowledge_faq",
        target_id=faq_id,
    ))
    return faq  # type: ignore[return-value]


@router.post("/{faq_id}/reject", response_model=FAQResponse)
async def reject_faq(
    faq_id: int, payload: FAQReviewAction, db: DbDep,
    current_user: Annotated[User, Depends(require_permission("write"))],
) -> FAQResponse:
    try:
        faq = await FAQService(db).reject(faq_id, current_user, comment=payload.comment)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Not authorized for this department")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if faq is None:
        raise HTTPException(status_code=404, detail="FAQ not found")
    asyncio.create_task(log_operation_async(
        operator_id=current_user.id,
        operator_name=_OP_NAME(current_user),
        operation_type="update",
        target_table="knowledge_faq",
        target_id=faq_id,
    ))
    return faq  # type: ignore[return-value]


@router.get("/{faq_id}/versions")
async def list_faq_versions(
    faq_id: int, db: DbDep,
    _u: Annotated[User, Depends(require_auth)],
) -> list[dict]:
    versions = await FAQService(db).get_versions(faq_id)
    return versions


@router.post("/{faq_id}/rollback/{version_id}", response_model=FAQResponse)
async def rollback_faq(
    faq_id: int, version_id: int, db: DbDep,
    current_user: Annotated[User, Depends(require_permission("write"))],
) -> FAQResponse:
    try:
        faq = await FAQService(db).rollback(faq_id, version_id, current_user)
    except PermissionError:
        raise HTTPException(status_code=403, detail="Not authorized for this department")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if faq is None:
        raise HTTPException(status_code=404, detail="FAQ not found")
    asyncio.create_task(log_operation_async(
        operator_id=current_user.id,
        operator_name=_OP_NAME(current_user),
        operation_type="update",
        target_table="knowledge_faq",
        target_id=faq_id,
    ))
    return faq  # type: ignore[return-value]
