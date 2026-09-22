"""文章批量生成 — ORM 模型

遵循项目现有 SQLAlchemy 2.0 Mapped[] 风格。
参照: app/models/document.py
"""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ArticleBatch(Base):
    __tablename__ = "article_batch"
    __table_args__ = (
        Index("idx_ab_user", "user_id"),
        Index("idx_ab_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    topic: Mapped[str] = mapped_column(String(500), nullable=False)
    # 目标账号类型: user/designer/dealer，None=通用
    account_type: Mapped[str | None] = mapped_column(String(20), default=None)
    photo_count: Mapped[int] = mapped_column(Integer, default=0)
    photo_object_names: Mapped[list | None] = mapped_column(JSON, default=None)
    photo_descriptions: Mapped[str | None] = mapped_column(Text, default=None)
    selected_angle_keys: Mapped[list | None] = mapped_column(JSON, default=None)
    article_count: Mapped[int] = mapped_column(Integer, default=5)
    generated_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    error_message: Mapped[str | None] = mapped_column(Text, default=None)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class Article(Base):
    __tablename__ = "article"
    __table_args__ = (
        Index("idx_a_batch", "batch_id"),
        Index("idx_a_angle", "angle"),
        Index("idx_a_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    angle: Mapped[str] = mapped_column(String(100), nullable=False)
    # 目标账号类型: user/designer/dealer，None=通用
    account_type: Mapped[str | None] = mapped_column(String(20), default=None)
    image_placement: Mapped[list | None] = mapped_column(JSON, default=None)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    review_status: Mapped[str] = mapped_column(String(20), default="pending")
    user_id: Mapped[int | None] = mapped_column(Integer, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class PlatformAccount(Base):
    """平台发布账号 — 支持同一平台多账号绑定"""
    __tablename__ = "platform_account"
    __table_args__ = (
        Index("idx_pa_user", "user_id"),
        Index("idx_pa_platform", "platform_id"),
        Index("idx_pa_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform_id: Mapped[str] = mapped_column(String(50), nullable=False, comment="平台标识 wechat_mp/toutiao...")
    account_name: Mapped[str] = mapped_column(String(100), nullable=False, comment="显示名称")
    account_group: Mapped[str | None] = mapped_column(String(20), default=None, comment="账号组 2113/2114/2119/9023")
    ws_token: Mapped[str | None] = mapped_column(Text, default=None, comment="加密存储的 Chrome 扩展 Token")
    credentials: Mapped[str | None] = mapped_column(Text, default=None, comment="加密存储的凭证(微信 direct_api)")
    credentials_type: Mapped[str] = mapped_column(String(20), default="token", comment="凭证类型")
    status: Mapped[str] = mapped_column(String(20), default="active")
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    error_message: Mapped[str | None] = mapped_column(Text, default=None)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class PublishingRecord(Base):
    __tablename__ = "publishing_record"
    __table_args__ = (
        Index("idx_pr_article", "article_id"),
        Index("idx_pr_platform", "platform"),
        Index("idx_pr_account", "account_id"),
        Index("idx_pr_scheduled", "scheduled_at"),
        Index("idx_pr_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    article_id: Mapped[int] = mapped_column(Integer, nullable=False)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    platform_name: Mapped[str | None] = mapped_column(String(100), default=None)
    account_id: Mapped[int | None] = mapped_column(Integer, default=None)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    published_url: Mapped[str | None] = mapped_column(String(1000), default=None)
    remote_article_id: Mapped[str | None] = mapped_column(String(50), default=None, comment="远端平台文章 ID")
    error_message: Mapped[str | None] = mapped_column(Text, default=None)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime, default=None, comment="定时发布时间")
    stats: Mapped[dict | None] = mapped_column(JSON, default=None, comment="发布后统计数据")
    stats_updated_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Photo(Base):
    """照片资产库 — 每张照片带 AI 标签和描述，可被不同批次复用"""
    __tablename__ = "photo"
    __table_args__ = (
        Index("idx_p_user", "user_id"),
        Index("idx_p_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    object_name: Mapped[str] = mapped_column(String(500), nullable=False, comment="MinIO 对象路径")
    filename: Mapped[str] = mapped_column(String(200), nullable=False)
    tags: Mapped[list] = mapped_column(JSON, default=list, comment="标签数组")
    description: Mapped[str | None] = mapped_column(Text, default=None, comment="Vision AI 分析描述")
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    content_type: Mapped[str] = mapped_column(String(50), default="image/jpeg")
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class BatchPhoto(Base):
    """批次-照片关联 — 追踪照片使用记录，支持防重复窗口"""
    __tablename__ = "batch_photo"
    __table_args__ = (
        Index("idx_bp_batch", "batch_id"),
        Index("idx_bp_photo", "photo_id"),
        Index("idx_bp_used_at", "used_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(Integer, nullable=False)
    photo_id: Mapped[int] = mapped_column(Integer, nullable=False)
    article_id: Mapped[int | None] = mapped_column(Integer, default=None)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class WritingTemplate(Base):
    """写作模板 — 系统预设 + 用户自定义"""
    __tablename__ = "writing_template"
    __table_args__ = (
        Index("idx_wt_user", "user_id"),
        Index("idx_wt_type", "type"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False, default="structure")
    # 适用账号类型: user/designer/dealer，None=通用
    account_type: Mapped[str | None] = mapped_column(String(20), default=None)
    prompt_instruction: Mapped[str] = mapped_column(Text, nullable=False)
    is_preset: Mapped[int] = mapped_column(Integer, default=0)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
