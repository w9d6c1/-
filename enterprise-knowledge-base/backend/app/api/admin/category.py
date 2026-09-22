"""后台管理 — 分类管理路由"""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.core.dependencies import require_auth, require_permission
from app.models.user import User
from app.schemas.category import CategoryCreate, CategoryResponse, CategoryUpdate
from app.schemas.common import PaginatedResponse
from app.services.audit_service import log_operation_async
from app.services.category_service import CategoryService
from app.core.dependencies import DbDep

router = APIRouter(prefix="/categories", tags=["admin-categories"])


class BulkIds(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=200)


@router.get("", response_model=PaginatedResponse[CategoryResponse])
async def list_categories(
    db: DbDep,
    current_user: Annotated[User, Depends(require_auth)],
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
) -> PaginatedResponse[CategoryResponse]:
    service = CategoryService(db)
    items, total = await service.list(current_user, page, page_size)
    total_pages = max(1, (total + page_size - 1) // page_size) if total > 0 else 0
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size, total_pages=total_pages)


@router.get("/tree", response_model=list[CategoryResponse])
async def category_tree(
    db: DbDep,
    current_user: Annotated[User, Depends(require_auth)],
) -> list[CategoryResponse]:
    service = CategoryService(db)
    return await service.tree(current_user)


@router.post("", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
async def create_category(
    payload: CategoryCreate,
    db: DbDep,
    current_user: Annotated[User, Depends(require_permission("write"))],
) -> CategoryResponse:
    service = CategoryService(db)
    try:
        result = await service.create(payload, current_user)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    asyncio.create_task(log_operation_async(
        operator_id=current_user.id,
        operator_name=current_user.display_name or current_user.username,
        operation_type="create",
        target_table="knowledge_category",
        target_id=result.id,
    ))
    return result  # type: ignore[return-value]


@router.put("/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: int,
    payload: CategoryUpdate,
    db: DbDep,
    current_user: Annotated[User, Depends(require_permission("write"))],
) -> CategoryResponse:
    service = CategoryService(db)
    try:
        category = await service.update(category_id, payload, current_user)
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for this department")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if category is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    asyncio.create_task(log_operation_async(
        operator_id=current_user.id,
        operator_name=current_user.display_name or current_user.username,
        operation_type="update",
        target_table="knowledge_category",
        target_id=category_id,
    ))
    return category  # type: ignore[return-value]


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: int,
    db: DbDep,
    current_user: Annotated[User, Depends(require_permission("write"))],
) -> None:
    service = CategoryService(db)
    try:
        deleted = await service.delete(category_id, current_user)
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized for this department")
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    asyncio.create_task(log_operation_async(
        operator_id=current_user.id,
        operator_name=current_user.display_name or current_user.username,
        operation_type="delete",
        target_table="knowledge_category",
        target_id=category_id,
    ))


@router.post("/bulk-delete")
async def bulk_delete_categories(
    payload: BulkIds, db: DbDep, current_user: Annotated[User, Depends(require_permission("write"))],
) -> dict:
    service = CategoryService(db)
    deleted, failed = 0, []
    for cid in payload.ids:
        try:
            ok = await service.delete(cid, current_user)
        except PermissionError:
            failed.append({"id": cid, "reason": "permission denied"})
            continue
        if not ok:
            failed.append({"id": cid, "reason": "not found"})
            continue
        deleted += 1
        asyncio.create_task(log_operation_async(
            operator_id=current_user.id,
            operator_name=current_user.display_name or current_user.username,
            operation_type="delete", target_table="knowledge_category", target_id=cid,
        ))
    return {"deleted": deleted, "failed": failed}
