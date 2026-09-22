"""监控告警全链路覆盖 — 基础指标告警测试

要求:
- 服务可用性、P95 延迟、错误率、CPU/内存/磁盘使用率的告警阈值
- 超标立即通知
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
PROMETHEUS_YML = PROJECT_ROOT / "docker" / "prometheus" / "prometheus.yml"
ALERT_RULES_YML = PROJECT_ROOT / "docker" / "prometheus" / "alert.rules.yml"
DOCKER_COMPOSE_DEV = PROJECT_ROOT / "docker-compose.yml"
DOCKER_COMPOSE_PROD = PROJECT_ROOT / "docker-compose.prod.yml"


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _get_alerts(path: Path) -> list[dict]:
    rules = _load_yaml(path)
    alerts = []
    for group in rules.get("groups", []):
        for rule in group.get("rules", []):
            if "alert" in rule:
                alerts.append(rule)
    return alerts


def _compose_has_volume(compose_path: Path, volume_part: str) -> bool:
    content = compose_path.read_text(encoding="utf-8")
    return volume_part in content


# ============================================================
# BAS-01: alert.rules.yml 文件存在且有效 YAML
# ============================================================
def test_alert_rules_file_exists():
    assert ALERT_RULES_YML.exists(), "alert.rules.yml 文件缺失"
    rules = _load_yaml(ALERT_RULES_YML)
    assert "groups" in rules, "alert.rules.yml 缺少 groups 顶级键"
    assert len(rules["groups"]) > 0, "alert.rules.yml 中无告警分组"


# ============================================================
# BAS-02: prometheus.yml 中有 rule_files 配置
# ============================================================
def test_prometheus_loads_alert_rules():
    """验证 Prometheus 配置中有 rule_files 引用告警规则文件"""
    config = _load_yaml(PROMETHEUS_YML)
    rule_files = config.get("rule_files", [])
    assert rule_files, (
        "prometheus.yml 中缺少 rule_files 配置，告警规则不会被加载。"
        "请添加 rule_files: ['/etc/prometheus/alert.rules.yml']"
    )
    has_alert_file = any("alert.rules.yml" in f for f in rule_files)
    assert has_alert_file, (
        f"prometheus.yml 的 rule_files 中未引用 alert.rules.yml，当前值: {rule_files}"
    )


# ============================================================
# BAS-03: docker-compose 中 alert.rules.yml 已挂载到 Prometheus 容器
# ============================================================
def test_alert_rules_mounted_in_compose():
    """验证 docker-compose.yml 和 prod 版本都将 alert.rules.yml 挂载到 Prometheus"""
    mount_str = "alert.rules.yml:/etc/prometheus/alert.rules.yml"

    assert _compose_has_volume(DOCKER_COMPOSE_DEV, mount_str), (
        "docker-compose.yml 中未挂载 alert.rules.yml 到 Prometheus 容器"
    )
    assert _compose_has_volume(DOCKER_COMPOSE_PROD, mount_str), (
        "docker-compose.prod.yml 中未挂载 alert.rules.yml 到 Prometheus 容器"
    )


# ============================================================
# BAS-04: 服务可用性告警
# ============================================================
def test_service_availability_alert_exists():
    alerts = _get_alerts(ALERT_RULES_YML)
    backend_alerts = [a for a in alerts if a["alert"] == "BackendDown"]
    assert len(backend_alerts) == 1, "缺少 BackendDown 服务可用性告警"

    alert = backend_alerts[0]
    assert "up{" in alert["expr"], "BackendDown 告警表达式应基于 up 指标"
    assert alert["labels"]["severity"] == "critical", "BackendDown 应为 critical 级别"


# ============================================================
# BAS-05: P95 延迟告警
# ============================================================
def test_latency_p95_alert_exists():
    alerts = _get_alerts(ALERT_RULES_YML)
    latency_alerts = [a for a in alerts if a["alert"] == "HighLatency"]
    assert len(latency_alerts) == 1, "缺少 HighLatency P95 延迟告警"

    alert = latency_alerts[0]
    assert "histogram_quantile(0.95" in alert["expr"], "HighLatency 应使用 P95 分位数"
    m = re.search(r">\s*(\d+(?:\.\d+)?)", alert["expr"])
    assert m, f"无法解析 HighLatency 阈值: {alert['expr']}"
    threshold = float(m.group(1))
    assert threshold <= 5, f"P95 延迟阈值 {threshold}s 过高，建议 ≤3s"


# ============================================================
# BAS-06: 错误率告警
# ============================================================
def test_error_rate_alert_exists():
    alerts = _get_alerts(ALERT_RULES_YML)
    err_alerts = [a for a in alerts if a["alert"] == "HighErrorRate"]
    assert len(err_alerts) == 1, "缺少 HighErrorRate 错误率告警"

    alert = err_alerts[0]
    assert "5.." in alert["expr"], "HighErrorRate 应基于 5xx 状态码"
    assert alert["labels"]["severity"] == "critical", "错误率告警应为 critical 级别"


# ============================================================
# BAS-07: CPU/内存/磁盘资源告警
# ============================================================
def test_resource_alerts_exist():
    alerts = _get_alerts(ALERT_RULES_YML)
    alert_names = {a["alert"] for a in alerts}

    required = {"HighCPUUsage", "HighMemoryUsage", "DiskSpaceLow"}
    missing = required - alert_names
    assert not missing, (
        f"缺少以下资源告警规则: {', '.join(sorted(missing))}"
    )

    # CPU 告警应基于 process_cpu_seconds_total
    cpu_alert = next(a for a in alerts if a["alert"] == "HighCPUUsage")
    assert "process_cpu_seconds_total" in cpu_alert["expr"], "CPU 告警应基于 process_cpu_seconds_total"

    # 内存告警应基于 process_resident_memory_bytes
    mem_alert = next(a for a in alerts if a["alert"] == "HighMemoryUsage")
    assert "process_resident_memory_bytes" in mem_alert["expr"], "内存告警应基于 process_resident_memory_bytes"

    # 磁盘告警应基于 node_filesystem
    disk_alert = next(a for a in alerts if a["alert"] == "DiskSpaceLow")
    assert "node_filesystem" in disk_alert["expr"], "磁盘告警应基于 node_filesystem 指标"
    assert disk_alert["labels"]["severity"] == "critical", "磁盘告警应为 critical 级别"


# ============================================================
# BAS-08: 所有告警规则都有 severity label
# ============================================================
def test_all_alerts_have_severity_labels():
    alerts = _get_alerts(ALERT_RULES_YML)
    valid_severities = {"critical", "high", "medium", "warning", "info"}

    for alert in alerts:
        name = alert["alert"]
        labels = alert.get("labels", {})
        severity = labels.get("severity", "")
        assert severity, f"告警 {name} 缺少 severity label"
        assert severity in valid_severities, (
            f"告警 {name} 的 severity='{severity}' 无效，应为 {valid_severities} 之一"
        )
        assert "category" in labels, f"告警 {name} 缺少 category label"
