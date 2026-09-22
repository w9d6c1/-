"""FAQ 版本历史 SQLAlchemy 模型"""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FAQVersion(Base):
    __tablename__ = "faq_version"
    __table_args__ = (
        Index("idx_fv_faq", "faq_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    faq_id: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    question: Mapped[str] = mapped_column(String(500), nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    similar_questions: Mapped[list | None] = mapped_column(JSON, default=None)
    tags: Mapped[list | None] = mapped_column(JSON, default=None)
    scope: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    effective_start: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    effective_end: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    created_by: Mapped[int | None] = mapped_column(Integer, default=None)
