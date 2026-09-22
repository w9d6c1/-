"""add_video_script_and_manual_hot

短视频文案模块新增两张表：
- video_script       短视频脚本（口播稿 + 分镜头）
- manual_hot_item    手动热榜（馋妈妈等登录墙平台手动粘贴）

NOTE — 与文章模块一致，新表在启动时由 Base.metadata.create_all() 创建（新库自动含）。
本迁移仅用于已存在的库补表，请显式目标升级：
    alembic upgrade c002_video_script_manual_hot

Revision ID: c002_video_script_manual_hot
Revises: c001_add_article_account_type
Create Date: 2026-08-10 16:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c002_video_script_manual_hot"
down_revision: Union[str, Sequence[str], None] = "c001_add_article_account_type"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "video_script",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(500), nullable=False, server_default=""),
        sa.Column("hot_word", sa.String(200), nullable=True),
        sa.Column("hot_url", sa.String(1000), nullable=True),
        sa.Column("voiceover", sa.Text(), nullable=False, server_default=""),
        sa.Column("storyboard", sa.Text(), nullable=True),
        sa.Column("material_notes", sa.Text(), nullable=True),
        sa.Column("requirement", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), server_default="draft"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("idx_vs_user", "video_script", ["user_id"])
    op.create_index("idx_vs_created", "video_script", ["created_at"])

    op.create_table(
        "manual_hot_item",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("url", sa.String(1000), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0"),
        sa.Column("source", sa.String(50), server_default="chanmama"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("idx_mh_user", "manual_hot_item", ["user_id"])
    op.create_index("idx_mh_source", "manual_hot_item", ["source"])


def downgrade() -> None:
    op.drop_index("idx_mh_source", table_name="manual_hot_item")
    op.drop_index("idx_mh_user", table_name="manual_hot_item")
    op.drop_table("manual_hot_item")
    op.drop_index("idx_vs_created", table_name="video_script")
    op.drop_index("idx_vs_user", table_name="video_script")
    op.drop_table("video_script")
