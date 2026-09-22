"""后台管理 API 路由聚合"""

from fastapi import APIRouter

from app.api.admin.auth import router as auth_router
from app.api.admin.category import router as category_router
from app.api.admin.faq import router as faq_router
from app.api.admin.dictionary import router as dict_router
from app.api.admin.document import router as doc_router
from app.api.admin.source_content import router as source_content_router
from app.api.admin.dashboard import router as dashboard_router
from app.api.admin.scope_permission import router as scope_permission_router
from app.api.admin.audit import router as audit_router
from app.api.admin.config import router as config_router
from app.api.admin.user import router as user_router
from app.api.articles import router as articles_router
from app.api.ai_write import router as ai_write_router
from app.api.copywriting import router as copywriting_router

router = APIRouter()
router.include_router(auth_router)
router.include_router(category_router)
router.include_router(faq_router)
router.include_router(dict_router)
router.include_router(doc_router)
router.include_router(source_content_router)
router.include_router(dashboard_router, prefix="/dashboard")
router.include_router(scope_permission_router)
router.include_router(audit_router)
router.include_router(config_router)
router.include_router(user_router)
router.include_router(articles_router)
router.include_router(ai_write_router, prefix="/articles/ai-write")
router.include_router(copywriting_router)


@router.get("/status")
async def admin_status():
    return {"status": "ok", "module": "admin"}
