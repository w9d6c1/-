"""审计日志 SQLAlchemy 模型 — operate_log / chat_log / security_log"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, Index, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class OperateLog(Base):
    __tablename__ = "operate_log"
    __table_args__ = (
        Index("idx_ol_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    operator_id: Mapped[int | None] = mapped_column(Integer, default=None)
    operator_name: Mapped[str | None] = mapped_column(String(100), default=None)
    operation_type: Mapped[str] = mapped_column(String(20), nullable=False)
    target_table: Mapped[str] = mapped_column(String(100), nullable=False)
    target_id: Mapped[int | None] = mapped_column(Integer, default=None)
    content_before: Mapped[dict | None] = mapped_column(JSON, default=None)
    content_after: Mapped[dict | None] = mapped_column(JSON, default=None)
    ip_address: Mapped[str | None] = mapped_column(String(50), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ChatLog(Base):
    __tablename__ = "chat_log"
    __table_args__ = (
        Index("idx_cl_thread_id", "thread_id"),
        Index("idx_cl_created_at", "created_at"),
        Index("idx_cl_source", "source"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    thread_id: Mapped[str] = mapped_column(String(100), nullable=False)
    request_id: Mapped[str] = mapped_column(String(100), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="customer")
    user_id: Mapped[int | None] = mapped_column(Integer, default=None)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str | None] = mapped_column(Text, default=None)
    node_name: Mapped[str | None] = mapped_column(String(100), default=None)
    node_input: Mapped[dict | None] = mapped_column(JSON, default=None)
    node_output: Mapped[dict | None] = mapped_column(JSON, default=None)
    node_status: Mapped[str] = mapped_column(String(20), default="running")
    node_latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    hit_faq_id: Mapped[int | None] = mapped_column(Integer, default=None)
    hit_chunk_ids: Mapped[dict | None] = mapped_column(JSON, default=None)
    confidence: Mapped[float | None] = mapped_column(Float, default=None)
    sensitive_hit: Mapped[int] = mapped_column(Integer, default=0)
    transfer_human: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class SecurityLog(Base):
    __tablename__ = "security_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(100), default=None)
    user_id: Mapped[int | None] = mapped_column(Integer, default=None)
    ip_address: Mapped[str | None] = mapped_column(String(50), default=None)
    detail: Mapped[dict | None] = mapped_column(JSON, default=None)
    severity: Mapped[str] = mapped_column(String(20), default="medium")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
