"""监控告警全链路覆盖 — 安全告警测试

要求:
- 敏感词高频命中告警
- 越权尝试告警
- 隔离测试失败告警
- 守住数据安全红线
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
BACKEND_ROOT = PROJECT_ROOT / "backend"
ALERT_RULES_YML = PROJECT_ROOT / "docker" / "prometheus" / "alert.rules.yml"
WAF_DIR = PROJECT_ROOT / "docker" / "waf"
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


def _search_code(pattern: str) -> list[str]:
    matches = []
    app_dir = BACKEND_ROOT / "app"
    for py_file in app_dir.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue
        try:
            content = py_file.read_text(encoding="utf-8")
        except Exception:
            continue
        if re.search(pattern, content, re.IGNORECASE):
            matches.append(str(py_file.relative_to(BACKEND_ROOT)))
    return matches


# ============================================================
# SEC-01: 敏感词高频命中告警
# ============================================================
def test_sensitive_word_alert_exists():
    alerts = _get_alerts(ALERT_RULES_YML)
    sw_alerts = [a for a in alerts if a["alert"] == "SensitiveWordHit"]
    assert len(sw_alerts) == 1, "缺少 SensitiveWordHit 敏感词命中告警"

    alert = sw_alerts[0]
    assert "kb_security_events_total" in alert["expr"], (
        "SensitiveWordHit 应基于 kb_security_events_total 指标"
    )
    assert "sensitive_word" in alert["expr"], (
        "SensitiveWordHit 应筛选 event_type='sensitive_word'"
    )
    # 验证阈值合理： > 2 次/5min
    m = re.search(r">\s*(\d+)", alert["expr"])
    assert m, f"无法解析 SensitiveWordHit 阈值: {alert['expr']}"
    threshold = int(m.group(1))
    assert threshold <= 5, f"敏感词命中阈值 {threshold} 过高，建议 ≤2"


# ============================================================
# SEC-02: 越权尝试告警
# ============================================================
def test_unauthorized_access_alert_exists():
    alerts = _get_alerts(ALERT_RULES_YML)
    ua_alerts = [a for a in alerts if a["alert"] == "UnauthorizedAccessSpike"]
    assert len(ua_alerts) == 1, "缺少 UnauthorizedAccessSpike 越权访问告警"

    alert = ua_alerts[0]
    assert 'status="401"' in alert["expr"], "越权告警应基于 401 状态码"
    assert alert["labels"]["severity"] == "high", "越权告警应为 high 级别"


# ============================================================
# SEC-03: 跨库隔离泄漏告警
# ============================================================
def test_cross_scope_leak_alert_exists():
    alerts = _get_alerts(ALERT_RULES_YML)
    leak_alerts = [a for a in alerts if a["alert"] == "CrossScopeLeakageDetected"]
    assert len(leak_alerts) == 1, "缺少 CrossScopeLeakageDetected 跨库泄漏告警"

    alert = leak_alerts[0]
    assert "kb_cross_scope_leak_total" in alert["expr"], (
        "跨库泄漏告警应基于 kb_cross_scope_leak_total 指标"
    )
    assert alert["labels"]["severity"] == "critical", "跨库泄漏告警应为 critical 级别"


# ============================================================
# SEC-04: SQL 注入攻击告警
# ============================================================
def test_sql_injection_alert_exists():
    alerts = _get_alerts(ALERT_RULES_YML)
    sql_alerts = [a for a in alerts if a["alert"] == "SQLInjectionAttempt"]
    assert len(sql_alerts) == 1, "缺少 SQLInjectionAttempt 告警"

    alert = sql_alerts[0]
    assert "sql_injection" in alert["expr"], "SQL 注入告警应筛选 event_type='sql_injection'"
    assert alert["labels"]["severity"] == "high", "SQL 注入告警应为 high 级别"


# ============================================================
# SEC-05: Prompt 注入攻击告警
# ============================================================
def test_prompt_injection_alert_exists():
    alerts = _get_alerts(ALERT_RULES_YML)
    pi_alerts = [a for a in alerts if a["alert"] == "PromptInjectionAttempt"]
    assert len(pi_alerts) == 1, "缺少 PromptInjectionAttempt 告警"

    alert = pi_alerts[0]
    assert "prompt_injection" in alert["expr"], (
        "Prompt 注入告警应筛选 event_type='prompt_injection'"
    )
    assert alert["labels"]["severity"] == "high", "Prompt 注入告警应为 high 级别"


# ============================================================
# SEC-06: kb_security_events_total 指标已埋点
# ============================================================
def test_security_events_counter_instrumented():
    """验证代码中注册了 kb_security_events_total Counter"""
    matches = _search_code(r"kb_security_events_total|SecurityEventsCounter|security_events")
    assert matches, (
        f"代码中未找到 kb_security_events_total 指标注册。\n"
        f"请在安全事件处理代码中注册 Prometheus Counter:\n"
        f"  from prometheus_client import Counter\n"
        f"  kb_security_events_total = Counter(\n"
        f"      'kb_security_events_total',\n"
        f"      'Security events count',\n"
        f"      ['event_type']\n"
        f"  )\n"
        f"然后在 SQL注入/敏感词命中/Prompt注入的处理代码中调用:\n"
        f"  kb_security_events_total.labels(event_type='sql_injection').inc()"
    )


# ============================================================
# SEC-07: high/critical 安全事件触发 Webhook 通知
# ============================================================
def test_security_notification_on_high_severity():
    """验证 notifier.py 中 notify_security_event 针对高危事件发送通知"""
    notifier_path = BACKEND_ROOT / "app" / "core" / "notifier.py"
    content = notifier_path.read_text(encoding="utf-8")

    assert "notify_security_event" in content, "notifier.py 中缺少 notify_security_event 函数"
    assert "send_notification" in content, "notifier.py 中缺少 send_notification 函数"
    assert "severity" in content, "notify_security_event 应接受 severity 参数"

    # 验证调用方对 high/critical 事件触发通知
    agent_file = BACKEND_ROOT / "app" / "api" / "agent" / "__init__.py"
    if agent_file.exists():
        agent_content = agent_file.read_text(encoding="utf-8")
        notifier_referenced = (
            "notify_security_event" in agent_content
            or "send_notification" in agent_content
        )
        assert notifier_referenced, (
            "agent/__init__.py 中未调用 notify_security_event，"
            "high/critical 安全事件将不会触发 Webhook 通知"
        )


# ============================================================
# SEC-08: WAF 监控已接入
# ============================================================
def test_waf_monitoring_enabled():
    """验证 WAF 容器配置中存在且日志可被采集"""
    # WAF 目录存在
    assert WAF_DIR.exists(), "docker/waf/ 目录缺失"

    # WAF 日志配置在 docker-compose 中存在
    for compose_path in [DOCKER_COMPOSE_DEV, DOCKER_COMPOSE_PROD]:
        content = compose_path.read_text(encoding="utf-8")
        assert "waf" in content.lower(), f"{compose_path.name} 中未定义 WAF 服务"

    # Promtail 应采集容器日志（docker_sd_configs 已配置）
    promtail_config = PROJECT_ROOT / "docker" / "loki" / "promtail-config.yml"
    pt_content = promtail_config.read_text(encoding="utf-8")
    assert "docker_sd_configs" in pt_content, "promtail 未配置 Docker 服务发现"
    assert "loki:3100" in pt_content or "loki" in pt_content.lower(), (
        "promtail 未配置 Loki 推送地址"
    )


# ============================================================
# SEC-09: 安全告警分类完整性
# ============================================================
def test_security_alerts_have_all_types():
    """验证安全类别告警覆盖了所有必需的安全事件类型"""
    alerts = _get_alerts(ALERT_RULES_YML)
    security_alerts = [a for a in alerts if a["labels"].get("category") == "security"]

    required_types = {"sql_injection", "prompt_injection", "sensitive_word"}
    found_types = set()
    for alert in security_alerts:
        expr = alert["expr"]
        for event_type in required_types:
            if event_type in expr:
                found_types.add(event_type)

    missing_types = required_types - found_types
    assert not missing_types, (
        f"安全告警中缺少以下事件类型的规则: {', '.join(missing_types)}"
    )
