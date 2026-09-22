"""知识库分类 SQLAlchemy 模型"""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class KnowledgeCategory(Base):
    __tablename__ = "knowledge_category"
    __table_args__ = (
        Index("idx_kc_department", "department"),
        Index("idx_kc_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    parent_id: Mapped[int | None] = mapped_column(Integer, default=None)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    scope: Mapped[str] = mapped_column(String(20), nullable=False, default="public")
    status: Mapped[str] = mapped_column(String(20), default="enabled")
    department: Mapped[str | None] = mapped_column(String(100), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
