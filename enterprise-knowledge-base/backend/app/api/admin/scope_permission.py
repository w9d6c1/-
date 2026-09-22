"""后台管理 — scope_permission 动态权限 CRUD"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select, func

from app.core.dependencies import DbDep, require_permission
from app.models.scope_permission import ScopePermission
from app.models.user import User
from app.schemas.common import PaginatedResponse

router = APIRouter(prefix="/scope-permissions", tags=["admin-scope-permissions"])


class ScopePermissionCreate(BaseModel):
    role: str = Field(min_length=1, max_length=20)
    scope: str = Field(min_length=1, max_length=20)
    is_active: bool = True


class ScopePermissionUpdate(BaseModel):
    is_active: bool | None = None


class ScopePermissionResponse(BaseModel):
    id: int
    role: str
    scope: str
    is_active: bool

    model_config = {"from_attributes": True}


@router.get("", response_model=PaginatedResponse[ScopePermissionResponse])
async def list_permissions(
    db: DbDep,
    _u: Annotated[User, Depends(require_permission("read"))],
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
) -> PaginatedResponse[ScopePermissionResponse]:
    count_r = await db.execute(select(func.count()).select_from(ScopePermission))
    total = count_r.scalar() or 0
    offset = (page - 1) * page_size
    r = await db.execute(select(ScopePermission).order_by(ScopePermission.id).offset(offset).limit(page_size))
    items = list(r.scalars())
    total_pages = max(1, (total + page_size - 1) // page_size)
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size, total_pages=total_pages)


@router.post("", response_model=ScopePermissionResponse, status_code=status.HTTP_201_CREATED)
async def create_permission(
    payload: ScopePermissionCreate,
    db: DbDep,
    _u: Annotated[User, Depends(require_permission("write"))],
) -> ScopePermissionResponse:
    sp = ScopePermission(
        role=payload.role, scope=payload.scope,
        is_active=1 if payload.is_active else 0,
    )
    db.add(sp)
    await db.commit()
    await db.refresh(sp)
    return sp


@router.put("/{perm_id}", response_model=ScopePermissionResponse)
async def update_permission(
    perm_id: int,
    payload: ScopePermissionUpdate,
    db: DbDep,
    _u: Annotated[User, Depends(require_permission("write"))],
) -> ScopePermissionResponse:
    sp = await db.get(ScopePermission, perm_id)
    if sp is None:
        raise HTTPException(status_code=404, detail="Not found")
    if payload.is_active is not None:
        sp.is_active = 1 if payload.is_active else 0
    await db.commit()
    await db.refresh(sp)
    return sp


@router.delete("/{perm_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_permission(
    perm_id: int,
    db: DbDep,
    _u: Annotated[User, Depends(require_permission("write"))],
) -> None:
    sp = await db.get(ScopePermission, perm_id)
    if sp is None:
        raise HTTPException(status_code=404, detail="Not found")
    await db.delete(sp)
    await db.commit()


_DEFAULT_PERMISSIONS = [
    {"role": "superadmin", "scope": "public"},
    {"role": "superadmin", "scope": "internal"},
    {"role": "superadmin", "scope": "customer"},
    {"role": "dept_admin", "scope": "public"},
    {"role": "dept_admin", "scope": "internal"},
    {"role": "operator", "scope": "public"},
    {"role": "operator", "scope": "internal"},
    {"role": "readonly", "scope": "public"},
]


@router.post("/defaults", status_code=status.HTTP_201_CREATED)
async def create_default_permissions(
    db: DbDep,
    _u: Annotated[User, Depends(require_permission("write"))],
) -> dict[str, int]:
    count = 0
    for perm in _DEFAULT_PERMISSIONS:
        existing = await db.execute(
            select(ScopePermission).where(
                ScopePermission.role == perm["role"],
                ScopePermission.scope == perm["scope"],
            )
        )
        if existing.scalar_one_or_none() is None:
            db.add(ScopePermission(role=perm["role"], scope=perm["scope"], is_active=1))
            count += 1
    await db.commit()
    return {"created": count}


@router.post("/reload")
async def reload_permission_cache(
    db: DbDep,
    _u: Annotated[User, Depends(require_permission("write"))],
) -> dict:
    from app.agents.nodes.auth import refresh_scope_permission_cache

    await refresh_scope_permission_cache(db)
    return {"status": "ok"}
