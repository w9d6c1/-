"""数据库建表与基础种子数据引导（幂等）

背景：docker/mysql/init/01-schema.sql 已裁剪为仅创建数据库。
业务表统一在此由 Base.metadata.create_all() 全量创建（checkfirst 幂等，
按当前 ORM 模型的最终 schema），并幂等写入基础种子数据（分类/超管/敏感词/权限）。

用法:
    python -m app.scripts.init_schema            # 建表 + 基础种子
    python -m app.scripts.init_schema --no-seed  # 仅建表（不动数据）
"""

import argparse
import asyncio
import logging

from sqlalchemy import inspect, select

# ---------------------------------------------------------------
# 导入全部模型，确保 Base.metadata 完整注册（与 alembic/env.py 同源）
# ---------------------------------------------------------------
from app.api.admin.dictionary import (  # noqa: F401
    Feedback,
    SensitiveWord,
    Synonym,
    UnansweredQuestion,
)
from app.articles.models import (  # noqa: F401
    Article,
    ArticleBatch,
    BatchPhoto,
    Photo,
    PlatformAccount,
    PublishingRecord,
    WritingTemplate,
)
from app.copywriting.models import ManualHotItem, VideoScript  # noqa: F401
from app.core.database import AsyncSessionLocal, Base, engine
from app.models.audit import ChatLog, OperateLog, SecurityLog  # noqa: F401
from app.models.category import KnowledgeCategory  # noqa: F401
from app.models.collector import CollectorSyncLog, CollectorSyncState, DocSourceLink  # noqa: F401
from app.models.document import DocChunk, KnowledgeDoc  # noqa: F401
from app.models.faq import KnowledgeFAQ  # noqa: F401
from app.models.faq_version import FAQVersion  # noqa: F401
from app.models.scope_permission import ScopePermission  # noqa: F401
from app.models.user import User  # noqa: F401

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("init_schema")

# 种子写入引用的实体
_CATEGORY = KnowledgeCategory
_USER = User
_SENSITIVE = SensitiveWord
_SCOPE_PERM = ScopePermission

_DEFAULT_CATEGORIES = [
    {"id": 1, "parent_id": None, "name": "公共知识", "scope": "public"},
    {"id": 2, "parent_id": None, "name": "内部知识", "scope": "internal"},
    {"id": 3, "parent_id": None, "name": "客服知识", "scope": "customer"},
]
_ADMIN = {
    "username": "admin",
    "password_hash": "$2b$12$LJ3m4ys3GZfnYLpOoFJ5XOzAQ0b5jFG1Qq5PyOoKrY1BgLM7xSPPm",
    "display_name": "超级管理员",
    "role": "superadmin",
}
_SENSITIVE_WORDS = [
    {"word": "敏感词示例", "word_type": "sensitive"},
    {"word": "禁止讨论", "word_type": "forbid"},
]
_SCOPE_PERMS = [
    ("superadmin", "public"),
    ("superadmin", "internal"),
    ("superadmin", "customer"),
    ("dept_admin", "public"),
    ("dept_admin", "internal"),
    ("operator", "public"),
    ("operator", "internal"),
    ("readonly", "public"),
]


async def create_tables() -> list[str]:
    """全量 create_all（checkfirst 幂等），返回本次新建的表名。"""
    async with engine.connect() as conn:
        before = set(await conn.run_sync(
            lambda sync_conn: inspect(sync_conn).get_table_names()
        ))

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with engine.connect() as conn:
        after = set(await conn.run_sync(
            lambda sync_conn: inspect(sync_conn).get_table_names()
        ))

    created = sorted(after - before)
    logger.info("init_schema_create_all total=%s created=%s", len(after), created)
    return created


async def seed_base() -> None:
    """幂等写入基础种子数据（缺则补，存在则跳过）。"""
    async with AsyncSessionLocal() as db:
        for c in _DEFAULT_CATEGORIES:
            if await db.get(_CATEGORY, c["id"]) is None:
                db.add(
                    _CATEGORY(
                        id=c["id"],
                        parent_id=c["parent_id"],
                        name=c["name"],
                        scope=c["scope"],
                    )
                )

        admin = (
            await db.execute(select(_USER).where(_USER.username == _ADMIN["username"]))
        ).scalar_one_or_none()
        if admin is None:
            db.add(_USER(**_ADMIN))

        for s in _SENSITIVE_WORDS:
            existing = (
                await db.execute(select(_SENSITIVE).where(_SENSITIVE.word == s["word"]))
            ).scalar_one_or_none()
            if existing is None:
                db.add(_SENSITIVE(**s))

        for role, scope in _SCOPE_PERMS:
            existing = (
                await db.execute(
                    select(_SCOPE_PERM).where(
                        _SCOPE_PERM.role == role, _SCOPE_PERM.scope == scope
                    )
                )
            ).scalar_one_or_none()
            if existing is None:
                db.add(_SCOPE_PERM(role=role, scope=scope))

        await db.commit()
        logger.info("init_schema_seed_done")


async def main(no_seed: bool) -> None:
    try:
        created = await create_tables()
        if no_seed:
            logger.info("init_schema_no_seed")
        else:
            await seed_base()
        logger.info("init_schema_ok created_count=%s", len(created))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="建表 + 基础种子数据（幂等）")
    parser.add_argument("--no-seed", action="store_true", help="仅建表，不写种子数据")
    args = parser.parse_args()
    asyncio.run(main(args.no_seed))
