"""分类管理业务逻辑层"""

from __future__ import annotations

import asyncio

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.models.category import KnowledgeCategory
from app.models.user import User
from app.schemas.category import CategoryCreate, CategoryResponse, CategoryUpdate


class CategoryService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def _dept_scoped(self, stmt, current_user: User):
        if current_user.role != "superadmin" and current_user.department:
            return stmt.where(KnowledgeCategory.department == current_user.department)
        return stmt

    async def list(
        self, current_user: User, page: int = 1, page_size: int = 100
    ) -> tuple[list[KnowledgeCategory], int]:
        count_stmt = self._dept_scoped(select(func.count()).select_from(KnowledgeCategory), current_user)
        stmt = self._dept_scoped(select(KnowledgeCategory).order_by(KnowledgeCategory.sort_order), current_user)
        total = (await self.db.execute(count_stmt)).scalar() or 0
        offset = (page - 1) * page_size
        result = await self.db.execute(stmt.offset(offset).limit(page_size))
        return list(result.scalars()), total

    async def tree(self, current_user: User) -> list[CategoryResponse]:
        """构建树形分类结构 — 返回根节点列表，children 递归嵌套"""
        stmt = self._dept_scoped(select(KnowledgeCategory).order_by(KnowledgeCategory.sort_order), current_user)
        result = await self.db.execute(stmt)
        rows = list(result.scalars())

        nodes: dict[int, CategoryResponse] = {
            row.id: CategoryResponse.model_validate(row) for row in rows
        }
        roots: list[CategoryResponse] = []
        for row in rows:
            node = nodes[row.id]
            parent = nodes.get(row.parent_id) if row.parent_id is not None else None
            if parent is not None:
                parent.children.append(node)
            else:
                roots.append(node)
        return roots

    async def create(self, payload: CategoryCreate, current_user: User) -> KnowledgeCategory:
        dept = payload.department or current_user.department
        if payload.parent_id is not None:
            parent = await self.db.get(KnowledgeCategory, payload.parent_id)
            if parent is None:
                raise ValueError("parent category not found")
        category = KnowledgeCategory(
            name=payload.name,
            parent_id=payload.parent_id,
            sort_order=payload.sort_order,
            scope=payload.scope,
            department=dept,
        )
        self.db.add(category)
        try:
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        await self.db.refresh(category)
        return category

    async def update(
        self, category_id: int, payload: CategoryUpdate, current_user: User
    ) -> KnowledgeCategory | None:
        category = await self.db.get(KnowledgeCategory, category_id)
        if category is None:
            return None
        if current_user.role != "superadmin" and category.department != current_user.department:
            raise PermissionError

        old_status = category.status
        if payload.name is not None:
            category.name = payload.name  # type: ignore[assignment]
        if payload.parent_id is not None:
            await self._guard_no_cycle(category_id, payload.parent_id)
            category.parent_id = payload.parent_id  # type: ignore[assignment]
        if payload.sort_order is not None:
            category.sort_order = payload.sort_order  # type: ignore[assignment]
        if payload.scope is not None:
            category.scope = payload.scope  # type: ignore[assignment]
        if payload.status is not None:
            category.status = payload.status  # type: ignore[assignment]
        try:
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        await self.db.refresh(category)

        if payload.status is not None and payload.status != old_status:
            if payload.status == "disabled":
                asyncio.create_task(_deindex_category_async(category_id))
            elif payload.status == "enabled":
                asyncio.create_task(_resync_category_async(category_id))
        return category

    async def delete(self, category_id: int, current_user: User) -> bool:
        category = await self.db.get(KnowledgeCategory, category_id)
        if category is None:
            return False
        if current_user.role != "superadmin" and category.department != current_user.department:
            raise PermissionError
        await self.db.delete(category)
        try:
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        asyncio.create_task(_deindex_category_async(category_id))
        return True

    async def _guard_no_cycle(self, category_id: int, new_parent_id: int) -> None:
        """防止将分类挂到自身或其子孙节点下形成环"""
        if new_parent_id == category_id:
            raise ValueError("category cannot be its own parent")
        cursor: int | None = new_parent_id
        visited: set[int] = set()
        while cursor is not None and cursor not in visited:
            if cursor == category_id:
                raise ValueError("cannot move category under its own descendant")
            visited.add(cursor)
            parent = await self.db.get(KnowledgeCategory, cursor)
            cursor = parent.parent_id if parent is not None else None


async def _deindex_category_async(category_id: int) -> None:
    from app.core.database import AsyncSessionLocal
    from app.retrieval.sync import deindex_category

    try:
        async with AsyncSessionLocal() as db:
            await deindex_category(db, category_id)
    except Exception:
        logger.warning("category_deindex_failed", category_id=category_id, exc_info=True)


async def _resync_category_async(category_id: int) -> None:
    from app.core.database import AsyncSessionLocal
    from app.retrieval.sync import resync_category

    try:
        async with AsyncSessionLocal() as db:
            await resync_category(db, category_id)
    except Exception:
        logger.warning("category_resync_failed", category_id=category_id, exc_info=True)
