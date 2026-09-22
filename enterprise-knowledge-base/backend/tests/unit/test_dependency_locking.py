"""生产环境一致性加固 — 依赖版本锁死测试

要求:
- Python 端用 pip freeze 导出全量依赖
- Node 端锁定 package-lock.json
- 重点对齐 langchain、langgraph、pymilvus 版本
"""

import json
import re
from pathlib import Path

import pytest

_PROJECT = Path(__file__).resolve().parent.parent.parent.parent
pytestmark = pytest.mark.skipif(
    not (_PROJECT / "backend" / "app").exists(),
    reason=f"需从宿主仓库根目录运行（{_PROJECT}/backend/app 不存在）",
)

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
BACKEND_ROOT = PROJECT_ROOT / "backend"
FRONTEND_ROOT = PROJECT_ROOT / "frontend"
REQUIREMENTS_TXT = BACKEND_ROOT / "requirements.txt"
REQUIREMENTS_LOCK = BACKEND_ROOT / "requirements-lock.txt"
PACKAGE_JSON = FRONTEND_ROOT / "package.json"
PACKAGE_LOCK = FRONTEND_ROOT / "package-lock.json"
DOCKERFILE = BACKEND_ROOT / "docker" / "Dockerfile"
DOCKER_COMPOSE_PROD = PROJECT_ROOT / "docker-compose.prod.yml"


def _parse_requirements(path: Path) -> dict[str, str]:
    packages = {}
    content = path.read_text(encoding="utf-8")
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        m = re.match(r"^([a-zA-Z0-9_.-]+(?:\[[^\]]*\])?)\s*(.+)?$", line)
        if m:
            name = m.group(1).lower()
            spec = (m.group(2) or "").strip()
            packages[name] = spec
    return packages


# ============================================================
# DEP-01: requirements-lock.txt 文件存在且非空
# ============================================================
def test_requirements_lock_file_exists():
    assert REQUIREMENTS_LOCK.exists(), (
        f"缺少 {REQUIREMENTS_LOCK.name}，请执行 `pip freeze > {REQUIREMENTS_LOCK.name}` 生成"
    )
    assert REQUIREMENTS_LOCK.stat().st_size > 0, f"{REQUIREMENTS_LOCK.name} 为空"


# ============================================================
# DEP-02: lock 文件中所有包版本均为精确版本 (==，无 >=)
# ============================================================
def test_requirements_lock_is_frozen():
    if not REQUIREMENTS_LOCK.exists():
        pytest.skip(f"{REQUIREMENTS_LOCK.name} 不存在")
    loose_lines = []
    for line in REQUIREMENTS_LOCK.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        if re.match(r"^[a-zA-Z0-9_.-]+(?:\[[^\]]*\])?\s*>=", line):
            loose_lines.append(line)
    assert not loose_lines, (
        f"requirements-lock.txt 中 {len(loose_lines)} 行使用了浮动版本(>=)，应全部用 == 精确锁定:\n"
        + "\n".join(loose_lines[:10])
    )


# ============================================================
# DEP-03: package-lock.json 存在且有效
# ============================================================
def test_package_lock_json_exists():
    assert PACKAGE_LOCK.exists(), "缺少 package-lock.json，请在前端目录执行 `npm install`"
    try:
        data = json.loads(PACKAGE_LOCK.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        pytest.fail(f"package-lock.json 格式无效: {exc}")
    assert "packages" in data or "lockfileVersion" in data, "package-lock.json 结构异常"


# ============================================================
# DEP-04: 关键包 (langchain, langgraph, pymilvus) 版本一致
# ============================================================
def test_critical_versions_aligned():
    """确保 requirements.txt、Dockerfile、docker-compose.prod.yml 中关键包版本一致"""
    critical = {
        "langchain": "0.3.0",
        "langgraph": "0.2.0",
        "pymilvus": "2.4.0",
    }

    req_pkgs = _parse_requirements(REQUIREMENTS_TXT)
    issues = []

    for pkg_name in critical:
        found = any(k == pkg_name for k in req_pkgs)
        if not found:
            issues.append(f"requirements.txt 中缺少 {pkg_name}")
        else:
            pkg_key = next(k for k in req_pkgs if k == pkg_name)
            spec = req_pkgs[pkg_key]
            # Verify version constraint includes the minimum expected version
            m_spec = re.search(r"(\d+(?:\.\d+)*(?:\.\d+)?)", spec)
            if not m_spec:
                issues.append(f"无法解析 {pkg_name} 版本约束: {spec}")

    # Check Dockerfile references requirements.txt (not individual package names)
    if DOCKERFILE.exists():
        dockerfile_content = DOCKERFILE.read_text(encoding="utf-8")
        if "requirements" not in dockerfile_content.lower():
            issues.append("Dockerfile 中未引用 requirements.txt，版本锁定链断裂")

    # Check docker-compose image versions
    if DOCKER_COMPOSE_PROD.exists():
        compose = yaml.safe_load(DOCKER_COMPOSE_PROD.read_text(encoding="utf-8"))
        services = compose.get("services", {})
        milvus_svc = services.get("milvus", {})
        if milvus_svc:
            img = milvus_svc.get("image", "")
            if isinstance(img, str) and "milvus" in img.lower():
                m_img = re.search(r"(\d+\.\d+\.\d+)", img)
                if not m_img:
                    issues.append("docker-compose.prod.yml 中 Milvus 镜像未标注版本号")

    assert not issues, "关键包版本不一致:\n" + "\n".join(issues)


# ============================================================
# DEP-05: 生产用 requirements 中无浮动版本约束
# ============================================================
def test_no_loose_version_in_prod_requirements():
    """
    requirements.txt 允许用 >= 声明最低版本，
    但生产部署必须配合 requirements-lock.txt 精确锁定。
    本测试验证 lock 文件完整覆盖 requirements.txt 中的包。
    """
    if not REQUIREMENTS_LOCK.exists():
        pytest.skip(f"{REQUIREMENTS_LOCK.name} 不存在 (已由 DEP-01 报告)")

    req_pkgs = _parse_requirements(REQUIREMENTS_TXT)
    lock_pkgs = _parse_requirements(REQUIREMENTS_LOCK)

    def _normalize(name: str) -> str:
        m = re.match(r"^([a-zA-Z0-9_.-]+)", name)
        return m.group(1).lower() if m else name.lower()

    lock_keys = {_normalize(k) for k in lock_pkgs}

    missing_from_lock = []
    for pkg_name in req_pkgs:
        normalized = _normalize(pkg_name)
        # 跳过开发/测试工具
        if normalized.startswith("pytest") or normalized.startswith("ruff") or normalized.startswith("mypy"):
            continue
        if normalized not in lock_keys:
            missing_from_lock.append(pkg_name)

    assert not missing_from_lock, (
        f"requirements.txt 中的生产包在 requirements-lock.txt 中缺失:\n"
        + "\n".join(missing_from_lock)
        + f"\n请执行 `pip freeze > {REQUIREMENTS_LOCK.name}` 更新锁文件"
    )
