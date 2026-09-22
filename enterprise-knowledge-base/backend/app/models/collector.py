"""采集层持久化模型 — 文档来源链接、增量同步状态、同步日志。"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DocSourceLink(Base):
    """文档来源链接 — 一篇文档可对应多个平台来源（跨平台去重合并后保留全部出处）。"""

    __tablename__ = "doc_source_link"
    __table_args__ = (
        Index("idx_dsl_doc_id", "doc_id"),
        Index("idx_dsl_platform_external", "platform", "external_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doc_id: Mapped[int] = mapped_column(Integer, nullable=False, comment="所属文档 ID")
    platform: Mapped[str] = mapped_column(String(32), nullable=False, comment="来源平台 source_type")
    external_id: Mapped[str] = mapped_column(
        String(255), nullable=False, default="", comment="平台内唯一 ID（增量去重）"
    )
    original_url: Mapped[str | None] = mapped_column(String(512), default=None, comment="原文永久链接")
    source_name: Mapped[str | None] = mapped_column(String(64), default=None, comment="来源展示名")
    publish_time: Mapped[datetime | None] = mapped_column(DateTime, default=None, comment="官方发布时间")
    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, comment="是否主来源"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CollectorSyncState(Base):
    """采集增量同步游标状态（每平台一条，唯一）。"""

    __tablename__ = "collector_sync_state"
    __table_args__ = (Index("idx_css_platform", "platform", unique=True),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False, comment="平台 source_type")
    last_cursor: Mapped[str | None] = mapped_column(String(255), default=None, comment="增量游标")
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime, default=None, comment="最近同步时间")
    last_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="idle", comment="idle/running/success/failed"
    )
    last_error: Mapped[str | None] = mapped_column(String(500), default=None)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class CollectorSyncLog(Base):
    """采集同步日志（每次同步每平台一条）。"""

    __tablename__ = "collector_sync_log"
    __table_args__ = (Index("idx_csl_platform_time", "platform", "started_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    platform: Mapped[str] = mapped_column(String(32), nullable=False, comment="平台 source_type")
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    fetched_count: Mapped[int] = mapped_column(Integer, default=0)
    ingested_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicated_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="running", comment="running/success/failed"
    )
    error: Mapped[str | None] = mapped_column(Text, default=None)
