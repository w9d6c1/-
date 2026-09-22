"""API 路由聚合"""

from fastapi import APIRouter

from app.api.admin import router as admin_router
from app.api.agent import router as agent_router
from app.api.public_files import router as public_files_router
from app.channels.wecom.router import router as wecom_router
from app.core.config import settings

api_router = APIRouter()
api_router.include_router(admin_router, prefix="/admin")
api_router.include_router(agent_router, prefix="/agent")
api_router.include_router(public_files_router, prefix="/public")
api_router.include_router(wecom_router, prefix="/channels")


@api_router.get("/health")
async def api_health_check():
    return {"status": "healthy", "app": settings.app_name, "version": settings.app_version}
