"""测试基础设施 — 异步 SQLite + httpx 客户端"""

import asyncio

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base, get_db
from app.main import create_app

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

engine = create_async_engine(TEST_DATABASE_URL)
TestingSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def pytest_sessionfinish(session, exitstatus):
    """异步释放引擎连接池，避免 aiosqlite 工作线程残留导致退出挂起。"""
    asyncio.run(engine.dispose())


@pytest_asyncio.fixture(autouse=True)
async def _reset_scope_perms():
    from app.agents.nodes.auth import _reset_scope_cache

    _reset_scope_cache()
    yield


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    from app.api.admin.dictionary import (  # noqa: F401
        Feedback,
        SensitiveWord,
        Synonym,
        UnansweredQuestion,
    )
    from app.articles.models import Article, ArticleBatch, PublishingRecord  # noqa: F401
    from app.copywriting.models import ManualHotItem, VideoScript  # noqa: F401
    from app.models.audit import ChatLog  # noqa: F401
    from app.models.category import KnowledgeCategory  # noqa: F401
    from app.models.collector import (  # noqa: F401
        CollectorSyncLog,
        CollectorSyncState,
        DocSourceLink,
    )
    from app.models.document import DocChunk, DocImage, KnowledgeDoc  # noqa: F401
    from app.models.faq import KnowledgeFAQ  # noqa: F401
    from app.models.faq_version import FAQVersion  # noqa: F401
    from app.models.scope_permission import ScopePermission  # noqa: F401
    from app.models.user import User  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session():
    async with TestingSessionLocal() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession):
    app = create_app()

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
def token_factory(db_session: AsyncSession):
    """直接经 service 层预置带角色的用户并签发 token。

    公开注册接口 (/auth/register) 强制 readonly 以防提权，因此测试通过
    此工厂 (等价于生产 SQL 种子) provision 需要更高权限的账号。
    """
    from app.schemas.user import UserCreate
    from app.services.user_service import UserService

    async def _make(
        username: str,
        role: str = "operator",
        department: str | None = None,
        password: str = "SecureP@ss1",
    ) -> str:
        service = UserService(db_session)
        await service.create(
            UserCreate(
                username=username,
                password=password,
                password_confirm=password,
                role=role,
                department=department,
            )
        )
        token = await service.authenticate(username, password)
        assert token is not None
        return token

    return _make
