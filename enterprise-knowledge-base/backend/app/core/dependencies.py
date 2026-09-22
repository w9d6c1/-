"""依赖注入 - 鉴权与权限"""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal, get_db
from app.models.user import User

security_scheme = HTTPBearer(auto_error=False)

_credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security_scheme)],
) -> dict | None:
    if credentials is None:
        return None
    try:
        payload = jwt.decode(credentials.credentials, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        sub = payload.get("sub")
        if sub is None:
            raise _credentials_exception
        return {"user_id": int(sub), "role": payload.get("role", "readonly"), "department": payload.get("department")}
    except (JWTError, TypeError, ValueError):
        raise _credentials_exception


async def require_auth(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    if credentials is None:
        raise _credentials_exception
    try:
        payload = jwt.decode(credentials.credentials, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        user_id_str = payload.get("sub")
        if user_id_str is None:
            raise _credentials_exception
        user_id = int(user_id_str)
    except (JWTError, TypeError, ValueError):
        raise _credentials_exception

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise _credentials_exception
    return user


def require_role(*roles: str):
    """返回依赖函数：要求用户属于指定角色之一"""

    async def _check_role(
        current_user: Annotated[User, Depends(require_auth)],
    ) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user

    return _check_role


_PERMISSION_ROLES: dict[str, tuple[str, ...]] = {
    "read": ("superadmin", "dept_admin", "operator", "readonly"),
    "write": ("superadmin", "dept_admin", "operator"),
    "delete": ("superadmin", "dept_admin"),
}


def require_permission(permission: str):
    """返回依赖函数：要求用户拥有指定权限级别"""

    async def _check_perm(
        current_user: Annotated[User, Depends(require_auth)],
    ) -> User:
        allowed_roles = _PERMISSION_ROLES.get(permission, ("superadmin",))
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
            )
        return current_user

    return _check_perm


require_superadmin = require_role("superadmin")


async def get_db_session() -> AsyncSession:  # type: ignore[misc]
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


DbDep = Annotated[AsyncSession, Depends(get_db)]
CurrentUserDep = Annotated[dict | None, Depends(get_current_user)]

