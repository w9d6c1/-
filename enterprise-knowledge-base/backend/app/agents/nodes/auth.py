"""身份鉴权节点 — JWT + 部门权限映射 (动态 DB 加载)"""

import asyncio
import copy

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.state import AgentState
from app.core.logging import logger

_SCOPE_CACHE: dict[str, list[str]] = {}
_cache_lock = asyncio.Lock()


def _reset_scope_cache() -> None:
    global _SCOPE_CACHE, _cache_loaded
    _SCOPE_CACHE = {}
    _cache_loaded = False
_cache_loaded = False

_DEFAULT_ROLE_SCOPE_MAP: dict[str, list[str]] = {
    "superadmin": ["public", "internal", "customer"],
    "dept_admin": ["public", "internal"],
    "operator": ["public", "internal"],
    "readonly": ["public"],
}


async def load_scope_permissions_from_db(
    db: AsyncSession,
) -> dict[str, list[str]]:
    from app.models.scope_permission import ScopePermission

    result_map: dict[str, set[str]] = {}
    try:
        r = await db.execute(
            select(ScopePermission).where(ScopePermission.is_active == 1)
        )
        for row in r.scalars():
            result_map.setdefault(row.role, set()).add(row.scope)
    except Exception:
        logger.debug("load_scope_permissions_failed", exc_info=True)
        return dict(_DEFAULT_ROLE_SCOPE_MAP)

    final_map: dict[str, list[str]] = {}
    for role, scopes in result_map.items():
        ordered = [s for s in ["public", "internal", "customer"] if s in scopes]
        for s in scopes:
            if s not in ordered:
                ordered.append(s)
        final_map[role] = ordered
    return final_map


async def _build_cache(db: AsyncSession) -> dict[str, list[str]]:
    loaded = await load_scope_permissions_from_db(db)
    return loaded if loaded else dict(_DEFAULT_ROLE_SCOPE_MAP)


async def refresh_scope_permission_cache(db: AsyncSession) -> None:
    global _SCOPE_CACHE, _cache_loaded
    async with _cache_lock:
        _SCOPE_CACHE = await _build_cache(db)
        _cache_loaded = True
    logger.info("scope_permission_cache_refreshed", count=len(_SCOPE_CACHE))


async def _ensure_cache(db: AsyncSession) -> None:
    global _cache_loaded
    if not _cache_loaded:
        await refresh_scope_permission_cache(db)


async def map_role_to_scopes(
    db: AsyncSession,
    role: str,
    department: str | None = None,
) -> list[str]:
    await _ensure_cache(db)
    scopes = _SCOPE_CACHE.get(role)
    if scopes is None:
        scopes = _DEFAULT_ROLE_SCOPE_MAP.get(role, ["public"])
    return list(scopes)


def authenticate_node(state: AgentState) -> AgentState:
    result = copy.deepcopy(state)
    role = state.get("user_role", "readonly")
    department = state.get("user_department")
    scopes = _SCOPE_CACHE.get(role) or _DEFAULT_ROLE_SCOPE_MAP.get(role, ["public"])
    result["user_scopes"] = list(scopes)
    return result
