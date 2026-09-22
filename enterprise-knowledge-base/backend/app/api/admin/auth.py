"""后台管理 — 认证路由 (注册/登录/当前用户/手机号验证码)"""

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import settings
from app.core.dependencies import DbDep, require_auth, require_role, require_superadmin
from app.core.logging import logger as _auth_logger

limiter = Limiter(key_func=get_remote_address)


def _rate_limit(limit: str):
    """仅在非 debug 模式下启用速率限制"""

    def decorator(func):
        if settings.debug:
            return func
        return limiter.limit(limit)(func)

    return decorator
from app.core.database import AsyncSessionLocal
from app.core.middleware import request_id_var
from app.models.user import User
from app.schemas.user import (
    PhoneLoginRequest,
    SendCodeRequest,
    UserCreate,
    UserResponse,
)
from app.services.user_service import (
    DuplicateUserError,
    UserService,
    _sms_configured,
    check_rate_limit,
    generate_sms_code,
    send_sms_via_aliyun,
    store_sms_code,
    verify_sms_code,
)

router = APIRouter(prefix="/auth", tags=["admin-auth"])


async def _log_auth_failure(event_type: str, detail: str, user_id: int | None = None) -> None:
    from app.services.audit_service import AuditLogService

    try:
        async with AsyncSessionLocal() as db:
            svc = AuditLogService(db)
            await svc.log_security(
                event_type=event_type,
                request_id=request_id_var.get(),
                user_id=user_id,
                detail={"reason": detail},
                severity="medium",
            )
    except Exception:
        _auth_logger.warning("auth_failure_log_failed", event_type=event_type, exc_info=True)


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@_rate_limit("10/minute")
async def register(request: Request, payload: UserCreate, db: DbDep) -> UserResponse:
    payload.role = "readonly"  # 注册接口强制默认角色
    service = UserService(db)
    try:
        user = await service.create(payload)
    except DuplicateUserError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists")
    return user


@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@_rate_limit("30/minute")
async def create_user(
    request: Request,
    payload: UserCreate,
    db: DbDep,
    _current_user: Annotated[User, Depends(require_superadmin)],
) -> UserResponse:
    """管理员创建用户（保留请求中指定的角色）"""
    if not payload.role:
        payload.role = "readonly"
    service = UserService(db)
    try:
        user = await service.create(payload)
    except DuplicateUserError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already exists")
    return user


@router.post("/send-code")
@_rate_limit("5/minute")
async def send_code(request: Request, payload: SendCodeRequest) -> dict[str, str]:
    phone = payload.phone
    if await check_rate_limit(phone):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="请60秒后再试")
    code = generate_sms_code()
    await store_sms_code(phone, code)

    if _sms_configured():
        if not await send_sms_via_aliyun(phone, code):
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="短信发送失败，请稍后再试")
        return {"status": "ok"}

    return {"status": "ok", "code": code}


@router.post("/phone-login")
async def phone_login(payload: PhoneLoginRequest, db: DbDep) -> dict[str, object]:
    if not await verify_sms_code(payload.phone, payload.code):
        asyncio.create_task(_log_auth_failure("auth_failure", f"Wrong SMS code for {payload.phone}"))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="验证码错误或已过期")
    service = UserService(db)
    token, user = await service.authenticate_or_register_by_phone(payload.phone)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "phone": user.phone,
            "display_name": user.display_name,
            "role": user.role,
        },
    }


@router.post("/login")
@_rate_limit("10/minute")
async def login(
    request: Request,
    db: DbDep,
    username: str = Form(...),
    password: str = Form(...),
) -> dict[str, object]:
    if not username or not password:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="用户名和密码不能为空")
    service = UserService(db)
    token = await service.authenticate(username, password)
    if token is None:
        await _log_auth_failure("auth_failure", f"Invalid credentials for {username}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    user = await service.get_by_username(username)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "role": user.role,
            "department": user.department,
        },
    }


@router.get("/me", response_model=UserResponse)
async def get_me(db: DbDep, current_user: Annotated[User, Depends(require_auth)]) -> UserResponse:
    return current_user


@router.post("/protected-write", status_code=status.HTTP_201_CREATED)
async def protected_write(
    current_user: Annotated[User, Depends(require_role("superadmin", "dept_admin", "operator"))],
) -> dict[str, str]:
    return {"status": "ok", "role": current_user.role}
