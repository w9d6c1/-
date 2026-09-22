"""FastAPI 主入口"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import ValidationError
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.core.config import settings
from app.core.exceptions import (
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.core.logging import setup_logging
from app.core.middleware import RequestIDMiddleware

limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
    setup_logging()
    from app.core.logging import logger

    logger.info("app_starting", name=settings.app_name, version=settings.app_version)

    if not settings.jwt_secret_key or len(settings.jwt_secret_key) < 32:
        logger.warning("jwt_secret_key_weak_or_missing", min_length=32)
    if settings.jwt_algorithm not in ("HS256", "HS384", "HS512", "RS256", "RS384", "RS512"):
        raise RuntimeError(f"Unsupported JWT algorithm: {settings.jwt_algorithm}")

    try:
        # 建表自愈：01-schema.sql 已裁剪为仅建库，业务表统一由 create_all 幂等创建。
        # 失败仅告警不阻断（DB 未就绪时后续初始化也会失败并统一报错）。
        try:
            from app.scripts.init_schema import create_tables as _bootstrap_create_all

            await _bootstrap_create_all()
            logger.info("db_schema_create_all_done")
        except Exception:
            logger.warning("db_schema_create_all_failed", exc_info=True)

        from app.agents.graph import init_checkpointer
        from app.agents.nodes.faq import load_faq_vectors_from_db
        from app.agents.nodes.output import update_sensitive_rules
        from app.agents.nodes.validate import load_words_from_db
        from app.core.database import AsyncSessionLocal

        await init_checkpointer()
        logger.info("checkpointer_startup_loaded")

        async with AsyncSessionLocal() as db:
            count = await load_faq_vectors_from_db(db)
            logger.info("faq_vectors_startup_loaded", count=count)

        async with AsyncSessionLocal() as db:
            words = await load_words_from_db(db)
            update_sensitive_rules(words["sensitive_rules"])
            logger.info(
                "safety_words_loaded",
                forbid_count=len(words["forbid"]),
                sensitive_count=len(words["sensitive"]),
                sensitive_rules_count=len(words["sensitive_rules"]),
            )

        from app.agents.nodes.auth import refresh_scope_permission_cache

        async with AsyncSessionLocal() as db:
            await refresh_scope_permission_cache(db)
            logger.info("scope_permission_cache_loaded")

        from app.services.scheduler import start_scheduler

        start_scheduler()

        import asyncio as _asyncio

        from app.core.retention import retention_scheduler
        _asyncio.create_task(retention_scheduler())
        logger.info("retention_scheduler_started", retention_days=settings.chat_log_retention_days)

        from app.retrieval.milvus_client import preload_collections

        _asyncio.create_task(_asyncio.to_thread(preload_collections))
        logger.info("milvus_preload_started")
    except Exception as exc:
        logger.error("startup_failed", exc_info=True)
        raise RuntimeError(f"启动失败: {exc}") from exc

    yield

    from app.services.scheduler import shutdown_scheduler

    shutdown_scheduler()
    logger.info("app_shutdown")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_exception_handler(ValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    instrumentator = Instrumentator().instrument(app)
    instrumentator.expose(app)

    from app.api.router import api_router

    app.include_router(api_router, prefix="/api")

    @app.get("/health")
    async def health_check():
        return {"status": "healthy", "app": settings.app_name, "version": settings.app_version}

    return app


app = create_app()
