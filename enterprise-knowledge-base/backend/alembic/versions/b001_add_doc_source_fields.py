"""add_doc_source_fields

为 knowledge_doc 扩展多源溯源字段（来源类型/来源名/原文链接/发布时间）。
所有外部官方内容入库时 source_type 标记为对应平台，scope 强制为 public。

Revision ID: b001_add_doc_source_fields
Revises: 327b58012669
Create Date: 2026-07-31 09:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b001_add_doc_source_fields"
down_revision: Union[str, Sequence[str], None] = "327b58012669"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "knowledge_doc",
        sa.Column(
            "source_type",
            sa.String(32),
            nullable=False,
            server_default="internal",
            comment="来源类型：internal/wechat/toutiao/official_website/zhihu/bilibili",
        ),
    )
    op.add_column(
        "knowledge_doc",
        sa.Column(
            "source_name",
            sa.String(64),
            nullable=True,
            comment="来源展示名，如「公司官方公众号」",
        ),
    )
    op.add_column(
        "knowledge_doc",
        sa.Column(
            "original_url",
            sa.String(512),
            nullable=True,
            comment="原文永久链接，内部文档为空",
        ),
    )
    op.add_column(
        "knowledge_doc",
        sa.Column(
            "publish_time",
            sa.DateTime(),
            nullable=True,
            comment="官方发布时间，用于排序与展示",
        ),
    )
    op.create_index("idx_kd_source_type", "knowledge_doc", ["source_type"])


def downgrade() -> None:
    op.drop_index("idx_kd_source_type", table_name="knowledge_doc")
    op.drop_column("knowledge_doc", "publish_time")
    op.drop_column("knowledge_doc", "original_url")
    op.drop_column("knowledge_doc", "source_name")
    op.drop_column("knowledge_doc", "source_type")
