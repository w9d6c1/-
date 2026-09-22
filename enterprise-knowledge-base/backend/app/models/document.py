"""文档与切片 SQLAlchemy 模型"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Integer, String, Text, func
from sqlalchemy.dialects.mysql import MEDIUMTEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class KnowledgeDoc(Base):
    __tablename__ = "knowledge_doc"
    __table_args__ = (
        Index("idx_kd_status", "status"),
        Index("idx_kd_department", "department"),
        Index("idx_kd_scope", "scope"),
        Index("idx_kd_category_id", "category_id"),
        Index("idx_kd_review_status", "review_status"),
        Index("idx_kd_source_type", "source_type"),
        Index("idx_kd_content_hash", "content_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category_id: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    file_type: Mapped[str] = mapped_column(String(20), nullable=False, default="txt")
    file_size: Mapped[int] = mapped_column(BigInteger, default=0)
    plain_text: Mapped[str | None] = mapped_column(Text().with_variant(MEDIUMTEXT(), "mysql"), default=None)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    scope: Mapped[str] = mapped_column(String(20), nullable=False, default="public")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    chunk_strategy: Mapped[str] = mapped_column(String(20), default="recursive")
    chunk_size: Mapped[int] = mapped_column(Integer, default=512)
    chunk_overlap: Mapped[int] = mapped_column(Integer, default=80)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    department: Mapped[str | None] = mapped_column(String(100), default=None)
    reviewer_id: Mapped[int | None] = mapped_column(Integer, default=None)
    review_status: Mapped[str] = mapped_column(String(20), default="pending")
    review_comment: Mapped[str | None] = mapped_column(String(500), default=None)
    source_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="internal",
        comment="来源类型：internal/wechat/toutiao/official_website/zhihu/bilibili",
    )
    source_name: Mapped[str | None] = mapped_column(
        String(64), default=None, comment="来源展示名，如「公司官方公众号」"
    )
    original_url: Mapped[str | None] = mapped_column(
        String(512), default=None, comment="原文永久链接，内部文档为空"
    )
    publish_time: Mapped[datetime | None] = mapped_column(
        DateTime, default=None, comment="官方发布时间，用于排序与展示"
    )
    clean_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending",
        comment="清洗状态：pending/cleaned/skipped/failed",
    )
    clean_report: Mapped[str | None] = mapped_column(
        Text, default=None, comment="清洗统计报告（JSON）"
    )
    raw_text: Mapped[str | None] = mapped_column(
        Text().with_variant(MEDIUMTEXT(), "mysql"), default=None, comment="清洗前原文，用于回滚与前后对比"
    )
    content_hash: Mapped[str | None] = mapped_column(
        String(64), default=None, comment="归一化内容 SHA-256（精确去重键）"
    )
    content_simhash: Mapped[int | None] = mapped_column(
        BigInteger, default=None, comment="内容 SimHash 指纹（63 位非负，存 BIGINT，近似去重）"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class DocImage(Base):
    __tablename__ = "doc_image"
    __table_args__ = (
        Index("idx_di_doc_id", "doc_id"),
        Index("idx_di_doc_chunk", "doc_id", "chunk_index"),
        Index("idx_di_content_hash", "content_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doc_id: Mapped[int] = mapped_column(Integer, nullable=False, comment="所属文档 ID")
    chunk_index: Mapped[int | None] = mapped_column(
        Integer, default=None, comment="所属切片序号（无法关联时为空）"
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="图片在正文中的顺序")
    object_name: Mapped[str] = mapped_column(
        String(500), nullable=False, comment="MinIO 对象名（article-images/...）"
    )
    original_url: Mapped[str | None] = mapped_column(
        String(1024), default=None, comment="原始外链图片地址"
    )
    content_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="图片内容 SHA-256（去重键）"
    )
    width: Mapped[int | None] = mapped_column(Integer, default=None, comment="图片宽度（像素）")
    height: Mapped[int | None] = mapped_column(Integer, default=None, comment="图片高度（像素）")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)


class DocChunk(Base):
    __tablename__ = "doc_chunk"
    __table_args__ = (
        Index("idx_dc_doc_id", "doc_id"),
        Index("idx_dc_doc_chunk", "doc_id", "chunk_index"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doc_id: Mapped[int] = mapped_column(Integer, nullable=False, comment="所属文档 ID")
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False, comment="切片序号")
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="切片文本")
    scope: Mapped[str] = mapped_column(String(20), nullable=False, default="public")
    page_number: Mapped[int | None] = mapped_column(Integer, default=None, comment="页码（PDF/文档）")
    heading_path: Mapped[str | None] = mapped_column(String(500), default=None, comment="标题层级路径")
    vector_id: Mapped[str | None] = mapped_column(String(100), default=None)
    bm25_id: Mapped[str | None] = mapped_column(String(100), default=None)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
