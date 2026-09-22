"""后台管理 — 用户管理 CRUD（仅 superadmin）"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.core.dependencies import DbDep, require_superadmin
from app.models.user import User
from app.schemas.user import UserCreate, UserResponse, UserUpdate
from app.services.user_service import DuplicateUserError, UserService

router = APIRouter(prefix="/users", tags=["admin-users"])


class BulkIds(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=200)


class UserListResponse(BaseModel):
    items: list[UserResponse]
    total: int
    page: int
    page_size: int


@router.get("", response_model=UserListResponse)
async def list_users(
    db: DbDep,
    _u: Annotated[User, Depends(require_superadmin)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> UserListResponse:
    service = UserService(db)
    users, total = await service.list_users(page, page_size)
    return UserListResponse(items=users, total=total, page=page, page_size=page_size)


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    db: DbDep,
    _u: Annotated[User, Depends(require_superadmin)],
) -> UserResponse:
    service = UserService(db)
    user = await service.get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    payload: UserCreate,
    db: DbDep,
    _u: Annotated[User, Depends(require_superadmin)],
) -> UserResponse:
    service = UserService(db)
    try:
        user = await service.create(payload)
    except DuplicateUserError:
        raise HTTPException(status_code=400, detail="Username already exists")
    return user


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    payload: UserUpdate,
    db: DbDep,
    current_user: Annotated[User, Depends(require_superadmin)],
) -> UserResponse:
    if user_id == current_user.id and payload.role is not None:
        raise HTTPException(status_code=400, detail="不能修改自己的角色")
    if user_id == current_user.id and payload.is_active is False:
        raise HTTPException(status_code=400, detail="不能禁用自己")

    service = UserService(db)
    user = await service.update(
        user_id,
        role=payload.role,
        department=payload.department,
        display_name=payload.display_name,
        is_active=payload.is_active,
    )
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.delete("/{user_id}", status_code=status.HTTP_200_OK)
async def delete_user(
    user_id: int,
    db: DbDep,
    current_user: Annotated[User, Depends(require_superadmin)],
) -> dict[str, str]:
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="不能删除自己")

    service = UserService(db)
    target = await service.get_by_id(user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    if target.role == "superadmin":
        raise HTTPException(status_code=400, detail="超管账号受保护，不能被禁用")

    user = await service.update(user_id, is_active=False)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return {"status": "ok", "detail": "用户已禁用"}


@router.post("/bulk-delete")
async def bulk_disable_users(
    payload: BulkIds, db: DbDep,
    current_user: Annotated[User, Depends(require_superadmin)],
) -> dict:
    service = UserService(db)
    deleted, failed = 0, []
    for uid in payload.ids:
        if uid == current_user.id:
            failed.append({"id": uid, "reason": "cannot disable self"})
            continue
        target = await service.get_by_id(uid)
        if target is None:
            failed.append({"id": uid, "reason": "not found"})
            continue
        if target.role == "superadmin":
            failed.append({"id": uid, "reason": "superadmin protected"})
            continue
        user = await service.update(uid, is_active=False)
        if user is None:
            failed.append({"id": uid, "reason": "not found"})
            continue
        deleted += 1
    return {"deleted": deleted, "failed": failed}
