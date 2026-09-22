"""add account_group + ws_token to platform_account

Revision ID: a002_account_group
Revises: a001_platform_account
Create Date: 2026-07-29 15:30:00.000000

NOTE — 孤儿 head（2026-07-31 整理）:
  本迁移为 a001 的子迁移，整体从 baseline (95506ee7b94e) 分叉，与主链形成双 head。
  相关表由 SQLAlchemy 模型管理，未通过 alembic 执行。详见 a001_platform_account.py 注释。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a002_account_group"
down_revision: Union[str, Sequence[str], None] = "a001_platform_account"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("platform_account", sa.Column("account_group", sa.String(20), nullable=True))
    op.add_column("platform_account", sa.Column("ws_token", sa.Text(), nullable=True))
    op.alter_column("platform_account", "credentials", existing_type=sa.Text(), nullable=True)
    op.alter_column("platform_account", "credentials_type", existing_type=sa.String(20), server_default="token")


def downgrade() -> None:
    op.alter_column("platform_account", "credentials_type", existing_type=sa.String(20), server_default="appid_secret")
    op.alter_column("platform_account", "credentials", existing_type=sa.Text(), nullable=False)
    op.drop_column("platform_account", "ws_token")
    op.drop_column("platform_account", "account_group")
