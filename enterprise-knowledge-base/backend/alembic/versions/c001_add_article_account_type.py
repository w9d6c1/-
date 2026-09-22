"""add_article_account_type

文章创作按目标账号类型（用户/设计师/经销商）分流：
- article_batch.account_type       批次目标人群
- article.account_type             文章目标人群
- writing_template.account_type    模板适用人群

NOTE — article 相关表由 Base.metadata.create_all() 启动创建（新库自动含新列），
本迁移仅用于已存在的库补列。请使用显式目标升级：
    alembic upgrade c001_add_article_account_type
请勿执行 alembic upgrade head（多 head 歧义）。

Revision ID: c001_add_article_account_type
Revises: b004_add_doc_image
Create Date: 2026-08-10 12:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c001_add_article_account_type"
down_revision: Union[str, Sequence[str], None] = "b004_add_doc_image"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "article_batch",
        sa.Column("account_type", sa.String(20), nullable=True, comment="目标账号类型: user/designer/dealer, NULL=通用"),
    )
    op.add_column(
        "article",
        sa.Column("account_type", sa.String(20), nullable=True, comment="目标账号类型: user/designer/dealer, NULL=通用"),
    )
    op.add_column(
        "writing_template",
        sa.Column("account_type", sa.String(20), nullable=True, comment="适用账号类型: user/designer/dealer, NULL=通用"),
    )


def downgrade() -> None:
    op.drop_column("writing_template", "account_type")
    op.drop_column("article", "account_type")
    op.drop_column("article_batch", "account_type")
