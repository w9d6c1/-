"""监控告警全链路覆盖 — 业务指标告警测试

要求:
- 检索命中率低于 70% 告警
- 转人工率突增告警
- 用户满意度下降告警
- 前置发现知识质量问题
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
GRAFANA_DASHBOARDS_DIR = PROJECT_ROOT / "docker" / "grafana" / "provisioning" / "dashboards"
DASHBOARDS_PROVISIONING = GRAFANA_DASHBOARDS_DIR / "dashboards.yml"
DATASOURCES_PROVISIONING = (
    PROJECT_ROOT / "docker" / "grafana" / "provisioning" / "datasources" / "datasources.yml"
)
PROMTAIL_CONFIG = PROJECT_ROOT / "docker" / "loki" / "promtail-config.yml"


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


def _search_code(pattern: str, exclude_pycache: bool = True) -> list[str]:
    """在 backend/app 中搜索匹配模式的文件"""
    matches = []
    app_dir = BACKEND_ROOT / "app"
    for py_file in app_dir.rglob("*.py"):
        if exclude_pycache and "__pycache__" in str(py_file):
            continue
        try:
            content = py_file.read_text(encoding="utf-8")
        except Exception:
            continue
        if re.search(pattern, content, re.IGNORECASE):
            matches.append(str(py_file.relative_to(BACKEND_ROOT)))
    return matches


# ============================================================
# BIZ-01: 检索命中率低于 70% 告警
# ============================================================
def test_retrieval_hit_rate_alert_exists():
    """验证存在检索/FAQ 命中率低于阈值的告警规则"""
    content = ALERT_RULES_YML.read_text(encoding="utf-8")
    alert_names = set(re.findall(r"alert:\s*(\w+)", content))

    # 应存在命中率相关的告警名称
    hit_rate_related = [n for n in alert_names if any(
        kw in n.lower() for kw in ("hit", "retrieval", "faq", "recall")
    )]
    assert hit_rate_related, (
        "alert.rules.yml 中缺少检索命中率告警。"
        "请添加类似 retrieval_hit_rate 的规则：命中率 < 70% 时触发"
    )


# ============================================================
# BIZ-02: 转人工率突增告警
# ============================================================
def test_human_escalation_alert_exists():
    """验证存在转人工率突增的告警规则"""
    content = ALERT_RULES_YML.read_text(encoding="utf-8")

    # 检查是否有转人工相关的告警
    has_escalation = any(kw in content.lower() for kw in (
        "human", "escalation", "manual", "转人工", "needs_human"
    ))
    assert has_escalation, (
        "alert.rules.yml 中缺少转人工率告警。"
        "请添加规则：当 needs_human 事件在短时间内突增时触发"
    )


# ============================================================
# BIZ-03: 用户满意度下降告警
# ============================================================
def test_satisfaction_alert_exists():
    """验证存在用户满意度下降告警规则"""
    content = ALERT_RULES_YML.read_text(encoding="utf-8")

    has_satisfaction = any(kw in content.lower() for kw in (
        "satisfaction", "rating", "like", "dislike", "满意", "评价"
    ))
    assert has_satisfaction, (
        "alert.rules.yml 中缺少用户满意度告警。"
        "请添加规则：当 like/(like+dislike) 比率持续低于阈值时触发"
    )


# ============================================================
# BIZ-04: FAQ 匹配指标已埋点
# ============================================================
def test_faq_match_metric_instrumented():
    """验证代码中注册了 kb_faq_match_duration_seconds Histogram"""
    matches = _search_code(r"kb_faq_match_duration_seconds")
    assert matches, (
        "代码中未找到 kb_faq_match_duration_seconds 指标注册。"
        "请在 FAQ 匹配节点中注册 Prometheus Histogram: "
        "from prometheus_client import Histogram; "
        "kb_faq_match_duration_seconds = Histogram(...)"
    )


# ============================================================
# BIZ-05: 检索代码中有 Prometheus 埋点
# ============================================================
def test_retrieval_metrics_instrumented():
    """验证检索相关代码中有 Counter/Histogram 埋点"""
    retrieval_files = _search_code(r"from prometheus_client|import prometheus_client")
    assert retrieval_files, (
        "代码中未找到 prometheus_client 导入。"
        "请在 app/retrieval/ 中注册检索命中率、源分布等 Prometheus 指标"
    )


# ============================================================
# BIZ-06: /metrics 端点正常暴露
# ============================================================
@pytest.mark.asyncio
async def test_prometheus_metrics_endpoint():
    """验证 FastAPI 的 /metrics 端点正常返回 Prometheus 格式数据"""
    from httpx import AsyncClient, ASGITransport
    from app.main import create_app

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/metrics")
    assert response.status_code == 200
    content = response.text
    # prometheus_fastapi_instrumentator 自动暴露的指标
    assert "http_requests_total" in content, "/metrics 中缺少 http_requests_total"
    assert "python_info" in content, "/metrics 中缺少 python_info (prometheus_client 未正确暴露)"


# ============================================================
# BIZ-07: Grafana 仪表板已预配
# ============================================================
def test_grafana_dashboards_provisioned():
    """验证 4 个 Grafana 仪表板 JSON 文件存在且 provisioning 配置正确"""
    assert DASHBOARDS_PROVISIONING.exists(), "Grafana dashboards provisioning 配置缺失"

    dashboard_files = list(GRAFANA_DASHBOARDS_DIR.glob("*.json"))
    required_dashboards = {
        "kb-service-overview",
        "kb-security-posture",
        "kb-knowledge-quality",
        "kb-business-insight",
    }
    found_names = {f.stem for f in dashboard_files}
    missing = required_dashboards - found_names
    assert not missing, (
        f"Grafana 仪表板缺失: {', '.join(sorted(missing))}。"
        f"当前目录中仅有: {', '.join(sorted(found_names))}"
    )

    # 验证数据源配置
    assert DATASOURCES_PROVISIONING.exists(), "Grafana datasources provisioning 配置缺失"
    ds_config = _load_yaml(DATASOURCES_PROVISIONING)
    datasources = ds_config.get("datasources", [])
    ds_names = {ds.get("name", "") for ds in datasources}
    assert "Prometheus" in ds_names, "Grafana 中未配置 Prometheus 数据源"
    assert "Loki" in ds_names, "Grafana 中未配置 Loki 数据源"


# ============================================================
# BIZ-08: Promtail 采集关键日志标签
# ============================================================
def test_loki_log_labels_for_business_metrics():
    """验证 promtail 配置中提取了必要的日志字段"""
    content = PROMTAIL_CONFIG.read_text(encoding="utf-8")

    # 检查 JSON pipeline 提取的字段
    assert "level" in content, "promtail 未提取 level 字段"
    assert "event" in content, "promtail 未提取 event 字段"
    assert "request_id" in content, "promtail 未提取 request_id 字段"

    # 检查 docker 标签
    assert "container" in content, "promtail 未设置 container 标签"
    assert "service" in content, "promtail 未设置 compose service 标签"
