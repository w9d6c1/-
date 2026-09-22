"""应急与回滚方案 — 版本回滚测试

要求:
- Docker 镜像打版本标签
- 代码变更保留上一版可快速回退
- 回滚操作控制在 5 分钟内完成
"""

import re
from pathlib import Path

import pytest
import yaml

# ── 容器内跳过：路径解析依赖宿主仓库根目录 ──
from pathlib import Path as _Path
_PROJECT = _Path(__file__).resolve().parent.parent.parent.parent
pytestmark = pytest.mark.skipif(
    not (_PROJECT / "backend" / "app").exists(),
    reason=f"需从宿主仓库根目录运行（{_PROJECT}/backend/app 不存在）",
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
BACKEND_DOCKERFILE = PROJECT_ROOT / "backend" / "docker" / "Dockerfile"
FRONTEND_DOCKERFILE = PROJECT_ROOT / "frontend" / "docker" / "Dockerfile"
DOCKER_COMPOSE_DEV = PROJECT_ROOT / "docker-compose.yml"
DOCKER_COMPOSE_PROD = PROJECT_ROOT / "docker-compose.prod.yml"
DEPLOY_SCRIPT = PROJECT_ROOT / "deploy.sh"
CONFIG_PY = PROJECT_ROOT / "backend" / "app" / "core" / "config.py"


def _load_compose(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


# ============================================================
# ROL-01: Dockerfile 有版本标签
# ============================================================
def test_dockerfile_has_version_label_or_arg():
    """验证后端/前端 Dockerfile 有 LABEL version 或 ARG VERSION 声明"""
    for label, path in [("Backend", BACKEND_DOCKERFILE), ("Frontend", FRONTEND_DOCKERFILE)]:
        content = path.read_text(encoding="utf-8")
        has_version = any(
            kw in content for kw in ("LABEL version", "ARG VERSION", "ARG APP_VERSION")
        )
        assert has_version, (
            f"{label} Dockerfile 中缺少版本标签。"
            f"请添加 `ARG APP_VERSION` 和 `LABEL version=$APP_VERSION`"
        )


# ============================================================
# ROL-02: docker-compose 中所有镜像版本固定
# ============================================================
def test_all_compose_services_pinned_version():
    compose = _load_compose(DOCKER_COMPOSE_PROD)
    services = compose.get("services", {})
    unpinned = []

    for name, svc in services.items():
        img = svc.get("image", "")
        if isinstance(img, str) and img:
            # 从 Dockerfile 构建的 backend/frontend 没有 image 字段 (用 build)
            if img.endswith(":latest") or (":" not in img and "/" in img):
                unpinned.append(f"{name}: {img}")

    assert not unpinned, (
        f"docker-compose.prod.yml 中 {len(unpinned)} 个服务使用 :latest 镜像:\n"
        + "\n".join(unpinned)
        + "\n请固定为明确版本号（如 minio:RELEASE.2024-01-...）"
    )


# ============================================================
# ROL-03: deploy.sh 中有 docker tag 版本标签
# ============================================================
def test_deploy_script_tags_images_with_version():
    content = DEPLOY_SCRIPT.read_text(encoding="utf-8", errors="ignore")
    has_tag = re.search(r"docker\s+(tag|image tag)", content)
    has_label = re.search(r"(--build-arg\s+VERSION|APP_VERSION)", content)
    assert has_tag or has_label, (
        "deploy.sh 中 build 后未执行 docker tag 或设置 --build-arg VERSION。"
        "请添加:\n"
        "  VERSION=$(git rev-parse --short HEAD)\n"
        "  docker compose build --build-arg APP_VERSION=$VERSION\n"
        "  docker tag kb-backend kb-backend:$VERSION"
    )


# ============================================================
# ROL-04: deploy.sh 保留上一版用于快速回退
# ============================================================
def test_previous_version_retained_for_quick_rollback():
    content = DEPLOY_SCRIPT.read_text(encoding="utf-8", errors="ignore")
    has_prev = any(kw in content for kw in ("previous", "rollback", "backup", "上一版"))
    assert has_prev, (
        "deploy.sh 中未保留上一版镜像/容器信息。"
        "请在部署前执行 `docker tag kb-backend:latest kb-backend:previous` 保留旧版，"
        "回滚时直接 `docker compose up -d` 使用上一版镜像。"
    )


# ============================================================
# ROL-05: 存在回滚操作文档或脚本
# ============================================================
def test_rollback_documentation_exists():
    rollback_paths = [
        PROJECT_ROOT / "docs" / "ops" / "ROLLBACK.md",
        PROJECT_ROOT / "docs" / "ROLLBACK.md",
        PROJECT_ROOT / "ROLLBACK.md",
    ]
    found = [p for p in rollback_paths if p.exists()]

    deploy_content = DEPLOY_SCRIPT.read_text(encoding="utf-8", errors="ignore")
    has_rollback_flag = "--rollback" in deploy_content

    assert found or has_rollback_flag, (
        "缺少回滚文档 (docs/ops/ROLLBACK.md) 或 deploy.sh --rollback 选项。"
        "回滚操作应可 5 分钟内完成。"
    )


# ============================================================
# ROL-06: app_version 在 config 中定义且非默认值
# ============================================================
def test_app_version_in_config_defined():
    content = CONFIG_PY.read_text(encoding="utf-8")
    m = re.search(r'app_version\s*:\s*str\s*=\s*"([^"]*)"', content)
    assert m, "config.py 中缺少 app_version 字段"
    version = m.group(1)
    assert version, "app_version 为空字符串"
    assert version not in ("0.0.0", "dev"), (
        f"app_version='{version}' 疑似占位符，请使用语义化版本号"
    )


# ============================================================
# ROL-07: FAQ 回滚 API 端点存在
# ============================================================
def test_faq_rollback_api_endpoint_exists():
    faq_api = PROJECT_ROOT / "backend" / "app" / "api" / "admin" / "faq.py"
    content = faq_api.read_text(encoding="utf-8")

    has_rollback_route = "rollback" in content.lower()
    assert has_rollback_route, (
        "faq.py 中缺少回滚 API 端点。"
        "请确保 POST /api/admin/faqs/{faq_id}/rollback/{version_id} 存在"
    )

    faq_service = PROJECT_ROOT / "backend" / "app" / "services" / "faq_service.py"
    svc_content = faq_service.read_text(encoding="utf-8")
    assert "def rollback" in svc_content, (
        "faq_service.py 中缺少 rollback() 方法"
    )


# ============================================================
# ROL-08: /health 端点快速响应（回滚后验证）
# ============================================================
@pytest.mark.asyncio
async def test_health_endpoint_responds_for_rollback_verify():
    import time
    from httpx import AsyncClient, ASGITransport
    from app.main import create_app

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        start = time.monotonic()
        response = await client.get("/health")
        elapsed = time.monotonic() - start
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert elapsed < 2.0, (
        f"/health 响应耗时 {elapsed:.2f}s 超过 2s 阈值，"
        f"回滚后无法快速验证服务状态"
    )
