"""add_collector_models

阶段二数据层：knowledge_doc 增加去重字段（content_hash/content_simhash），
新增 doc_source_link（多来源链接）、collector_sync_state（增量游标）、collector_sync_log（同步日志）。

Revision ID: b002_add_collector_models
Revises: b001_add_doc_source_fields
Create Date: 2026-07-31 10:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b002_add_collector_models"
down_revision: Union[str, Sequence[str], None] = "b001_add_doc_source_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "knowledge_doc",
        sa.Column("content_hash", sa.String(64), nullable=True, comment="归一化内容 SHA-256（精确去重键）"),
    )
    op.add_column(
        "knowledge_doc",
        sa.Column("content_simhash", sa.BigInteger(), nullable=True, comment="内容 SimHash 指纹（63 位非负，近似去重）"),
    )
    op.create_index("idx_kd_content_hash", "knowledge_doc", ["content_hash"])

    op.create_table(
        "doc_source_link",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("doc_id", sa.Integer(), nullable=False, comment="所属文档 ID"),
        sa.Column("platform", sa.String(32), nullable=False, comment="来源平台 source_type"),
        sa.Column("external_id", sa.String(255), nullable=False, server_default="", comment="平台内唯一 ID（增量去重）"),
        sa.Column("original_url", sa.String(512), nullable=True, comment="原文永久链接"),
        sa.Column("source_name", sa.String(64), nullable=True, comment="来源展示名"),
        sa.Column("publish_time", sa.DateTime(), nullable=True, comment="官方发布时间"),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("0"), comment="是否主来源"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("idx_dsl_doc_id", "doc_source_link", ["doc_id"])
    op.create_index("idx_dsl_platform_external", "doc_source_link", ["platform", "external_id"])

    op.create_table(
        "collector_sync_state",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("platform", sa.String(32), nullable=False, comment="平台 source_type"),
        sa.Column("last_cursor", sa.String(255), nullable=True, comment="增量游标"),
        sa.Column("last_sync_at", sa.DateTime(), nullable=True, comment="最近同步时间"),
        sa.Column("last_status", sa.String(20), nullable=False, server_default="idle", comment="idle/running/success/failed"),
        sa.Column("last_error", sa.String(500), nullable=True),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("idx_css_platform", "collector_sync_state", ["platform"], unique=True)

    op.create_table(
        "collector_sync_log",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("platform", sa.String(32), nullable=False, comment="平台 source_type"),
        sa.Column("started_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("fetched_count", sa.Integer(), server_default="0"),
        sa.Column("ingested_count", sa.Integer(), server_default="0"),
        sa.Column("duplicated_count", sa.Integer(), server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="running", comment="running/success/failed"),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index("idx_csl_platform_time", "collector_sync_log", ["platform", "started_at"])


def downgrade() -> None:
    op.drop_index("idx_csl_platform_time", table_name="collector_sync_log")
    op.drop_table("collector_sync_log")
    op.drop_index("idx_css_platform", table_name="collector_sync_state")
    op.drop_table("collector_sync_state")
    op.drop_index("idx_dsl_platform_external", table_name="doc_source_link")
    op.drop_index("idx_dsl_doc_id", table_name="doc_source_link")
    op.drop_table("doc_source_link")
    op.drop_index("idx_kd_content_hash", table_name="knowledge_doc")
    op.drop_column("knowledge_doc", "content_simhash")
    op.drop_column("knowledge_doc", "content_hash")
