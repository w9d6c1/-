"""FAQ 结构化问答 SQLAlchemy 模型"""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class KnowledgeFAQ(Base):
    __tablename__ = "knowledge_faq"
    __table_args__ = (
        Index("idx_kf_status", "status"),
        Index("idx_kf_department", "department"),
        Index("idx_kf_scope", "scope"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category_id: Mapped[int] = mapped_column(Integer, nullable=False)
    question: Mapped[str] = mapped_column(String(500), nullable=False)
    similar_questions: Mapped[list | None] = mapped_column(JSON, default=None)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list | None] = mapped_column(JSON, default=None)
    scope: Mapped[str] = mapped_column(String(20), nullable=False, default="public")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    version: Mapped[int] = mapped_column(Integer, default=1)
    effective_start: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    effective_end: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    reviewer_id: Mapped[int | None] = mapped_column(Integer, default=None)
    review_status: Mapped[str] = mapped_column(String(20), default="pending")
    review_comment: Mapped[str | None] = mapped_column(String(500), default=None)
    department: Mapped[str | None] = mapped_column(String(100), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
