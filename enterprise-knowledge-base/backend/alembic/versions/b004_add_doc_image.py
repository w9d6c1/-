"""add_doc_image

问答带图功能：新增 doc_image 表，记录采集文章正文图片的转存对象与切片关联。

Revision ID: b004_add_doc_image
Revises: b003_add_doc_clean_fields
Create Date: 2026-08-06 01:30:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b004_add_doc_image"
down_revision: Union[str, Sequence[str], None] = "b003_add_doc_clean_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "doc_image",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("doc_id", sa.Integer(), nullable=False, comment="所属文档 ID"),
        sa.Column("chunk_index", sa.Integer(), nullable=True, comment="所属切片序号（无法关联时为空）"),
        sa.Column("seq", sa.Integer(), nullable=False, server_default="0", comment="图片在正文中的顺序"),
        sa.Column("object_name", sa.String(500), nullable=False, comment="MinIO 对象名（article-images/...）"),
        sa.Column("original_url", sa.String(1024), nullable=True, comment="原始外链图片地址"),
        sa.Column("content_hash", sa.String(64), nullable=False, comment="图片内容 SHA-256（去重键）"),
        sa.Column("width", sa.Integer(), nullable=True, comment="图片宽度（像素）"),
        sa.Column("height", sa.Integer(), nullable=True, comment="图片高度（像素）"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_di_doc_id", "doc_image", ["doc_id"])
    op.create_index("idx_di_doc_chunk", "doc_image", ["doc_id", "chunk_index"])
    op.create_index("idx_di_content_hash", "doc_image", ["content_hash"])


def downgrade() -> None:
    op.drop_index("idx_di_content_hash", table_name="doc_image")
    op.drop_index("idx_di_doc_chunk", table_name="doc_image")
    op.drop_index("idx_di_doc_id", table_name="doc_image")
    op.drop_table("doc_image")
