"""Prometheus 自定义指标注册 — 企业知识库系统

所有业务级指标统一在此注册，供 alert.rules.yml 和 Grafana 仪表板引用。
"""

from prometheus_client import Counter, Histogram


# ── 安全事件 (按 event_type 分类) ──
kb_security_events_total = Counter(
    "kb_security_events_total",
    "安全事件计数",
    ["event_type"],
)

# ── 跨库泄漏 ──
kb_cross_scope_leak_total = Counter(
    "kb_cross_scope_leak_total",
    "跨库隔离泄漏次数",
)

# ── FAQ 匹配延迟 ──
kb_faq_match_duration_seconds = Histogram(
    "kb_faq_match_duration_seconds",
    "FAQ 匹配耗时 (秒)",
    buckets=(0.01, 0.05, 0.1, 0.2, 0.3, 0.5, 1.0, 2.0, 5.0),
)

# ── 检索命中/总数 ──
kb_retrieval_total = Counter(
    "kb_retrieval_total",
    "检索请求总数",
    ["source"],
)

kb_retrieval_hit_total = Counter(
    "kb_retrieval_hit_total",
    "检索命中次数",
    ["source"],
)

# ── 转人工 ──
kb_needs_human_total = Counter(
    "kb_needs_human_total",
    "转人工请求次数",
)

# ── 满意度评价 ──
kb_rating_like_total = Counter(
    "kb_rating_like_total",
    "用户点赞次数",
)

kb_rating_dislike_total = Counter(
    "kb_rating_dislike_total",
    "用户点踩次数",
)
