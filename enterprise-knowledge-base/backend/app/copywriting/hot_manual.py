"""手动热榜 — 馋妈妈等登录墙平台，手动粘贴标题+链接入库"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.copywriting.models import ManualHotItem
from app.core.logging import logger


class ManualHotService:
    """手动热榜 CRUD"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_items(self, user_id: int | None = None, limit: int = 100) -> list[ManualHotItem]:
        base = select(ManualHotItem)
        if user_id is not None:
            base = base.where(ManualHotItem.user_id == user_id)
        base = base.order_by(ManualHotItem.sort_order, ManualHotItem.id.desc()).limit(limit)
        result = await self.db.execute(base)
        return list(result.scalars().all())

    async def create_item(
        self,
        user_id: int,
        title: str,
        url: str | None,
        source: str = "chanmama",
        sort_order: int = 0,
    ) -> ManualHotItem:
        obj = ManualHotItem(
            user_id=user_id,
            title=title,
            url=url or None,
            source=source or "chanmama",
            sort_order=sort_order,
        )
        self.db.add(obj)
        await self.db.commit()
        await self.db.refresh(obj)
        logger.info("manual_hot_created", item_id=obj.id, source=obj.source)
        return obj

    async def delete_item(self, item_id: int, user_id: int) -> bool:
        obj = await self.db.get(ManualHotItem, item_id)
        if not obj:
            return False
        if obj.user_id != user_id:
            return False
        await self.db.delete(obj)
        await self.db.commit()
        logger.info("manual_hot_deleted", item_id=item_id)
        return True

    async def clear_all(self, user_id: int) -> int:
        """清空当前用户全部手动热榜"""
        result = await self.db.execute(
            select(func.count(ManualHotItem.id)).where(ManualHotItem.user_id == user_id)
        )
        total = result.scalar() or 0
        if total:
            rows = await self.db.execute(
                select(ManualHotItem).where(ManualHotItem.user_id == user_id)
            )
            for row in rows.scalars().all():
                await self.db.delete(row)
            await self.db.commit()
            logger.info("manual_hot_cleared", user_id=user_id, count=total)
        return total
