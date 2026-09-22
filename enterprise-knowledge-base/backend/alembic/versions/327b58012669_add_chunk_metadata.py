"""add_chunk_metadata

Revision ID: 327b58012669
Revises: 95506ee7b94e
Create Date: 2026-07-22 01:53:58.747854
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "327b58012669"
down_revision: Union[str, Sequence[str], None] = "95506ee7b94e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "doc_chunk",
        sa.Column("page_number", sa.Integer(), nullable=True, comment="页码（PDF/文档）"),
    )
    op.add_column(
        "doc_chunk",
        sa.Column(
            "heading_path",
            sa.String(500),
            nullable=True,
            comment="标题层级路径",
        ),
    )


def downgrade() -> None:
    op.drop_column("doc_chunk", "heading_path")
    op.drop_column("doc_chunk", "page_number")
