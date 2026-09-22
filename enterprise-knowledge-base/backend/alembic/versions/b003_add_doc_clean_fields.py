"""add_doc_clean_fields

文档清洗优化功能：knowledge_doc 增加清洗状态、清洗报告与清洗前原文字段。

Revision ID: b003_add_doc_clean_fields
Revises: b002_add_collector_models
Create Date: 2026-08-04 09:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b003_add_doc_clean_fields"
down_revision: Union[str, Sequence[str], None] = "b002_add_collector_models"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "knowledge_doc",
        sa.Column(
            "clean_status",
            sa.String(20),
            nullable=False,
            server_default="pending",
            comment="清洗状态：pending/cleaned/skipped/failed",
        ),
    )
    op.add_column(
        "knowledge_doc",
        sa.Column("clean_report", sa.Text(), nullable=True, comment="清洗统计报告（JSON）"),
    )
    op.add_column(
        "knowledge_doc",
        sa.Column("raw_text", sa.Text(), nullable=True, comment="清洗前原文，用于回滚与前后对比"),
    )


def downgrade() -> None:
    op.drop_column("knowledge_doc", "raw_text")
    op.drop_column("knowledge_doc", "clean_report")
    op.drop_column("knowledge_doc", "clean_status")
