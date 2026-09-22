"""add platform_account + extend publishing_record

Revision ID: a001_platform_account
Revises: 95506ee7b94e
Create Date: 2026-07-28 12:00:00.000000

NOTE — 孤儿 head（2026-07-31 整理）:
  本迁移与 a002 从 baseline (95506ee7b94e) 分叉，与主链 (327b...→b001→b002) 形成双 head。
  platform_account / publishing_record 等相关表由 SQLAlchemy 模型（app.articles.models）
  通过 Base.metadata.create_all() 在启动时创建，alembic_version 仅追踪主链。
  ─ 请始终使用显式目标升级: alembic upgrade b002_add_collector_models（或最新 revision）。
  ─ 请勿执行 alembic upgrade head（多 head 歧义）或 alembic stamp a002（会覆盖 DB 版本链）。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a001_platform_account"
down_revision: Union[str, Sequence[str], None] = "95506ee7b94e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "platform_account",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("platform_id", sa.String(50), nullable=False),
        sa.Column("account_name", sa.String(100), nullable=False),
        sa.Column("credentials", sa.Text(), nullable=False),
        sa.Column("credentials_type", sa.String(20), server_default="appid_secret"),
        sa.Column("status", sa.String(20), server_default="active"),
        sa.Column("last_verified_at", sa.DateTime(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index("idx_pa_user", "platform_account", ["user_id"])
    op.create_index("idx_pa_platform", "platform_account", ["platform_id"])
    op.create_index("idx_pa_status", "platform_account", ["status"])

    op.add_column("publishing_record", sa.Column("account_id", sa.Integer(), nullable=True))
    op.add_column("publishing_record", sa.Column("scheduled_at", sa.DateTime(), nullable=True))
    op.add_column("publishing_record", sa.Column("remote_article_id", sa.String(50), nullable=True))
    op.add_column("publishing_record", sa.Column("stats", sa.JSON(), nullable=True))
    op.add_column("publishing_record", sa.Column("stats_updated_at", sa.DateTime(), nullable=True))
    op.create_index("idx_pr_account", "publishing_record", ["account_id"])
    op.create_index("idx_pr_scheduled", "publishing_record", ["scheduled_at"])


def downgrade() -> None:
    op.drop_index("idx_pr_scheduled", table_name="publishing_record")
    op.drop_index("idx_pr_account", table_name="publishing_record")
    op.drop_column("publishing_record", "stats_updated_at")
    op.drop_column("publishing_record", "stats")
    op.drop_column("publishing_record", "remote_article_id")
    op.drop_column("publishing_record", "scheduled_at")
    op.drop_column("publishing_record", "account_id")

    op.drop_index("idx_pa_status", table_name="platform_account")
    op.drop_index("idx_pa_platform", table_name="platform_account")
    op.drop_index("idx_pa_user", table_name="platform_account")
    op.drop_table("platform_account")
