"""短视频文案生成 — ORM 模型

遵循项目现有 SQLAlchemy 2.0 Mapped[] 风格。
参照: app/articles/models.py
"""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class VideoScript(Base):
    """短视频脚本 — 口播稿 + 分镜头脚本，可编辑"""

    __tablename__ = "video_script"
    __table_args__ = (
        Index("idx_vs_user", "user_id"),
        Index("idx_vs_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    hot_word: Mapped[str | None] = mapped_column(String(200), default=None, comment="关联热点词")
    hot_url: Mapped[str | None] = mapped_column(String(1000), default=None, comment="原视频链接")
    voiceover: Mapped[str] = mapped_column(Text, nullable=False, default="", comment="口播稿全文")
    storyboard: Mapped[str | None] = mapped_column(Text, default=None, comment="分镜头脚本")
    material_notes: Mapped[str | None] = mapped_column(Text, default=None, comment="素材摘要")
    requirement: Mapped[str | None] = mapped_column(Text, default=None, comment="AI 创作要求")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class ManualHotItem(Base):
    """手动热榜条目 — 馋妈妈等登录墙平台，管理员手动粘贴标题+链接入库"""

    __tablename__ = "manual_hot_item"
    __table_args__ = (
        Index("idx_mh_user", "user_id"),
        Index("idx_mh_source", "source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str | None] = mapped_column(String(1000), default=None)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(50), default="chanmama")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
