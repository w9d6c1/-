"""生产环境一致性加固 — Docker 容器资源限制测试

要求:
- 给每个 Docker 容器配置 CPU、内存上限
- 避免单组件（比如 Milvus）吃光资源导致整台服务器宕机
"""

import re
from pathlib import Path

import pytest
import yaml

from pathlib import Path

_PROJECT = Path(__file__).resolve().parent.parent.parent.parent
pytestmark = pytest.mark.skipif(
    not (_PROJECT / "backend" / "app").exists(),
    reason=f"需从宿主仓库根目录运行（{_PROJECT}/backend/app 不存在）",
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DOCKER_COMPOSE_DEV = PROJECT_ROOT / "docker-compose.yml"
DOCKER_COMPOSE_PROD = PROJECT_ROOT / "docker-compose.prod.yml"
DOCKER_COMPOSE_TENCENT = PROJECT_ROOT / "docker-compose.tencent.yml"

# 生产环境总资源估算（32G / 8核 典型服务器）
HOST_MEMORY_GB = 32
HOST_CPU_CORES = 8


def _load_compose(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _get_services(compose: dict) -> dict:
    return compose.get("services", {})


def _parse_memory_mb(mem_str: str) -> float:
    """将 '512M'、'2G'、'4G' 等转为 MB"""
    mem_str = str(mem_str).upper().strip()
    m = re.match(r"^(\d+(?:\.\d+)?)\s*([MGT])?B?$", mem_str)
    if not m:
        return 0
    val = float(m.group(1))
    unit = m.group(2) or "M"
    if unit == "G":
        val *= 1024
    elif unit == "T":
        val *= 1024 * 1024
    return val


def _parse_cpu(cpu_str: str) -> float:
    return float(str(cpu_str))


# ============================================================
# DKR-01: docker-compose.prod.yml 中所有 service 都有资源限制
# ============================================================
def test_prod_all_services_have_resource_limits():
    compose = _load_compose(DOCKER_COMPOSE_PROD)
    services = _get_services(compose)
    assert services, "docker-compose.prod.yml 中未定义任何 service"

    missing_limits = []
    for name, svc in services.items():
        deploy = svc.get("deploy", {})
        resources = deploy.get("resources", {})
        limits = resources.get("limits", {})
        if not limits:
            missing_limits.append(name)

    assert not missing_limits, (
        f"docker-compose.prod.yml 中以下 {len(missing_limits)} 个 service 缺少资源限制:\n"
        + "\n".join(missing_limits)
    )


# ============================================================
# DKR-02: 每个 service 的 limits 包含 memory 字段
# ============================================================
def test_prod_all_services_have_memory_limit():
    compose = _load_compose(DOCKER_COMPOSE_PROD)
    services = _get_services(compose)

    missing_memory = []
    for name, svc in services.items():
        limits = svc.get("deploy", {}).get("resources", {}).get("limits", {})
        if "memory" not in limits and "mem_limit" not in limits:
            missing_memory.append(name)

    assert not missing_memory, (
        f"以下 {len(missing_memory)} 个 service 缺少 memory 限制:\n"
        + "\n".join(missing_memory)
    )


# ============================================================
# DKR-03: 每个 service 的 limits 包含 cpus 字段
# ============================================================
def test_prod_all_services_have_cpu_limit():
    compose = _load_compose(DOCKER_COMPOSE_PROD)
    services = _get_services(compose)

    missing_cpu = []
    for name, svc in services.items():
        limits = svc.get("deploy", {}).get("resources", {}).get("limits", {})
        if "cpus" not in limits and "cpu" not in limits:
            missing_cpu.append(name)

    assert not missing_cpu, (
        f"以下 {len(missing_cpu)} 个 service 缺少 CPU 限制:\n"
        + "\n".join(missing_cpu)
    )


# ============================================================
# DKR-04: 每个 service 有 restart 策略
# ============================================================
def test_prod_all_services_have_restart_policy():
    compose = _load_compose(DOCKER_COMPOSE_PROD)
    services = _get_services(compose)

    missing_restart = []
    for name, svc in services.items():
        if "restart" not in svc:
            missing_restart.append(name)

    assert not missing_restart, (
        f"以下 {len(missing_restart)} 个 service 缺少 restart 策略:\n"
        + "\n".join(missing_restart)
    )


# ============================================================
# DKR-05: 每个 service 有日志轮转配置
# ============================================================
def test_prod_all_services_have_log_rotation():
    compose = _load_compose(DOCKER_COMPOSE_PROD)
    services = _get_services(compose)

    missing_logging = []
    for name, svc in services.items():
        logging = svc.get("logging", {})
        if not logging:
            missing_logging.append(name)

    assert not missing_logging, (
        f"以下 {len(missing_logging)} 个 service 缺少 logging 配置:\n"
        + "\n".join(missing_logging)
    )


# ============================================================
# DKR-06: 每个 service 有 healthcheck
# ============================================================
def test_prod_all_services_have_healthcheck():
    compose = _load_compose(DOCKER_COMPOSE_PROD)
    services = _get_services(compose)

    # 基础设施组件可豁免
    exempt = {"loki", "promtail", "redis", "prometheus", "grafana"}
    missing_hc = []
    for name, svc in services.items():
        if name in exempt:
            continue
        if "healthcheck" not in svc:
            missing_hc.append(name)

    assert not missing_hc, (
        f"以下 {len(missing_hc)} 个 service 缺少 healthcheck 定义:\n"
        + "\n".join(missing_hc)
    )


# ============================================================
# DKR-07: 所有服务内存总和 ≤ 主机总内存的 80%
# ============================================================
def test_limits_within_host_capacity():
    compose = _load_compose(DOCKER_COMPOSE_PROD)
    services = _get_services(compose)

    total_memory_mb = 0
    for name, svc in services.items():
        limits = svc.get("deploy", {}).get("resources", {}).get("limits", {})
        mem = limits.get("memory", "")
        if mem:
            total_memory_mb += _parse_memory_mb(mem)

    total_memory_gb = total_memory_mb / 1024
    max_allowed_gb = HOST_MEMORY_GB * 0.8

    assert total_memory_gb <= max_allowed_gb, (
        f"所有容器内存总和 {total_memory_gb:.1f}GB 超过主机内存的 80% ({max_allowed_gb:.1f}GB)，"
        f"存在 OOM 风险。请降低容器内存限制或增加主机内存。"
    )


# ============================================================
# DKR-08: docker-compose.yml 开发环境也应有资源上限
# ============================================================
def test_dev_compose_has_resource_limits():
    compose = _load_compose(DOCKER_COMPOSE_DEV)
    services = _get_services(compose)

    services_with_limits = 0
    total_services = len(services)
    for name, svc in services.items():
        limits = svc.get("deploy", {}).get("resources", {}).get("limits", {})
        if limits:
            services_with_limits += 1

    # 开发环境至少核心服务应有资源限制（milvus, elasticsearch, mysql）
    # 至少 50% 的 service 有资源限制
    ratio = services_with_limits / total_services if total_services > 0 else 0
    assert ratio >= 0.5, (
        f"docker-compose.yml 中仅 {services_with_limits}/{total_services} 个 service "
        f"配置了资源限制 ({ratio:.0%})，开发环境也应为所有容器设置资源上限 "
        f"避免本地资源耗尽"
    )
