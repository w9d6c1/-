"""配置热重载端点 — 重新加载运行时可配置项

POST /api/admin/config/reload
  → 重新加载禁答词/敏感词模式
  → 无需重启服务即可生效

环境变量级配置（DB连接/LLM Key等）需重启。
"""

from fastapi import APIRouter, Depends

from app.core.dependencies import require_auth
from app.core.logging import logger

router = APIRouter(prefix="/config", tags=["配置管理"])


@router.post("/reload", dependencies=[Depends(require_auth)])
async def reload_runtime_config():
    from app.agents.nodes.validate import load_blocked_patterns
    from app.agents.nodes.output import load_sensitive_patterns

    reloaded = {}

    try:
        from app.agents.nodes.validate import update_blocked_patterns
        patterns = load_blocked_patterns()
        update_blocked_patterns(patterns)
        reloaded["blocked_patterns"] = len(patterns)
    except Exception as e:
        logger.warning("config_reload_blocked_failed", error=str(e))
        reloaded["blocked_patterns"] = "error"

    try:
        from app.agents.nodes.output import update_sensitive_rules
        from app.core.database import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            result = await db.execute(text("SELECT word, answer FROM sensitive_word WHERE word_type='sensitive'"))
            rules = [{"pattern": row[0], "replacement": row[1] if row[1] else "***"} for row in result.fetchall()]
            update_sensitive_rules(rules)
            reloaded["sensitive_patterns"] = len(rules)
    except Exception as e:
        logger.warning("config_reload_sensitive_failed", error=str(e))
        reloaded["sensitive_patterns"] = "error"

    logger.info("config_reloaded", **reloaded)
    return {"success": True, "reloaded": reloaded}
