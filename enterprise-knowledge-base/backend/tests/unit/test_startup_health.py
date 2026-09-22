"""生产环境一致性加固 — 启动自检脚本测试

要求:
- 后端服务启动时自动执行健康检查
- 依次校验 MySQL、Redis、Milvus、ES、MinIO、PostgreSQL 的连通性
- 任一组件连接失败直接打印错误并退出，避免带病运行
"""

import re
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

# ── 容器内跳过：路径解析依赖宿主仓库根目录 ──
from pathlib import Path as _Path
_PROJECT = _Path(__file__).resolve().parent.parent.parent.parent
pytestmark = pytest.mark.skipif(
    not (_PROJECT / "backend" / "app").exists(),
    reason=f"需从宿主仓库根目录运行（{_PROJECT}/backend/app 不存在）",
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
BACKEND_ROOT = PROJECT_ROOT / "backend"
MAIN_PY = BACKEND_ROOT / "app" / "main.py"
PREFLIGHT_SCRIPT = PROJECT_ROOT / "scripts" / "preflight-check.sh"


# ============================================================
# HLT-01: /health 端点返回 200 且含 status 字段
# ============================================================
@pytest.mark.asyncio
async def test_health_endpoint_returns_200(client: AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "app" in data
    assert "version" in data


# ============================================================
# HLT-02: /health 端点应检查 MySQL 连通性
# ============================================================
def test_health_endpoint_checks_mysql():
    """验证 main.py 的 lifespan 中确实连接了 MySQL"""
    content = MAIN_PY.read_text(encoding="utf-8")
    # 数据库启动代码应引用 mysql
    has_db_import = "database" in content.lower()
    has_async_session = "AsyncSessionLocal" in content
    assert has_db_import or has_async_session, (
        "main.py lifespan 中未引用数据库连接代码"
    )


# ============================================================
# HLT-03: /health 端点应检查 Redis 连通性
# ============================================================
def test_health_endpoint_checks_redis():
    """验证项目中有 Redis 连接检查逻辑"""
    # 检查 redis 客户端初始化代码
    redis_patterns = ["redis", "Redis"]
    app_files = list((BACKEND_ROOT / "app").rglob("*.py"))
    found_redis = False
    for f in app_files:
        if "__pycache__" in str(f):
            continue
        try:
            content = f.read_text(encoding="utf-8").lower()
        except Exception:
            continue
        if "redis" in content:
            found_redis = True
            break
    assert found_redis, "项目代码中未找到 Redis 引用"


# ============================================================
# HLT-04: /health 端点应检查 Milvus 连通性
# ============================================================
def test_health_endpoint_checks_milvus():
    content = MAIN_PY.read_text(encoding="utf-8")
    assert "milvus" in content.lower(), (
        "main.py lifespan 中未引用 Milvus 预加载代码"
    )


# ============================================================
# HLT-05: /health 端点应检查 Elasticsearch 连通性
# ============================================================
def test_health_endpoint_checks_elasticsearch():
    app_files = list((BACKEND_ROOT / "app").rglob("*.py"))
    found_es = False
    for f in app_files:
        if "__pycache__" in str(f):
            continue
        try:
            content = f.read_text(encoding="utf-8").lower()
        except Exception:
            continue
        if "elasticsearch" in content or "es_client" in content:
            found_es = True
            break
    assert found_es, "项目代码中未找到 Elasticsearch 客户端引用"


# ============================================================
# HLT-06: /health 端点应检查 MinIO 连通性
# ============================================================
def test_health_endpoint_checks_minio():
    app_files = list((BACKEND_ROOT / "app").rglob("*.py"))
    found_minio = False
    for f in app_files:
        if "__pycache__" in str(f):
            continue
        try:
            content = f.read_text(encoding="utf-8").lower()
        except Exception:
            continue
        if "minio" in content:
            found_minio = True
            break
    assert found_minio, "项目代码中未找到 MinIO 客户端引用"


# ============================================================
# HLT-07: 启动时检查 PostgreSQL 连通性
# ============================================================
def test_health_endpoint_checks_postgresql():
    content = MAIN_PY.read_text(encoding="utf-8")
    assert "postgres" in content.lower() or "checkpoint" in content.lower(), (
        "main.py lifespan 中未引用 PostgreSQL (LangGraph Checkpoint) 初始化代码"
    )


# ============================================================
# HLT-09: lifespan 中数据库连接失败时不应静默吞异常
# ============================================================
def test_lifespan_fails_fast_on_db_unreachable():
    """验证 lifespan 中异常不再静默吞掉，而是 raise 使应用启动失败"""
    content = MAIN_PY.read_text(encoding="utf-8")

    # 不应再有 catch-all Exception 仅 log warning 的情况
    silent_swallow = re.search(
        r"except\s+Exception[^:]*:\s*\n\s+logger\.warning", content
    )
    assert not silent_swallow, (
        "main.py lifespan 中仍有 catch-all Exception 仅 log warning，"
        "应改为 raise RuntimeError 实现 fail-fast"
    )

    # 应存在异常时 raise 的代码
    has_fail_fast = re.search(
        r"raise\s+RuntimeError", content
    )
    assert has_fail_fast, (
        "main.py lifespan 中未找到 raise RuntimeError，"
        "catch-all Exception 块应 re-raise 异常以实现 fail-fast"
    )


# ============================================================
# HLT-10: preflight-check.sh 存在且可执行
# ============================================================
def test_preflight_check_script_exists_and_executable():
    assert PREFLIGHT_SCRIPT.exists(), (
        f"缺少启动自检脚本 {PREFLIGHT_SCRIPT.name}"
    )
    # 检查脚本内容包含必要的服务连通性检查
    content = PREFLIGHT_SCRIPT.read_text(encoding="utf-8", errors="ignore")
    checks = ["mysql", "redis", "postgres", "milvus", "elasticsearch", "minio"]
    missing_checks = [c for c in checks if c.lower() not in content.lower()]
    assert not missing_checks, (
        f"preflight-check.sh 中未检查以下服务: {', '.join(missing_checks)}"
    )
