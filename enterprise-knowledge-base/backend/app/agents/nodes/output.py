"""输出合规校验节点 — 敏感词过滤 + 正则脱敏 + 置信度 🔒"""

import copy
import re

from app.agents.state import AgentState

_SENSITIVE_RULES: list[dict] = []  # [{pattern: str, replacement: str}]

_IMG_MARKER_RE = re.compile(r"\[图(\d+)\]")


def strip_invalid_image_markers(text: str, valid_image_ids: set[int]) -> str:
    """剥离 LLM 编造的图片标记，仅保留注册表中真实存在的 [图N]。

    同时清理标记独占一行被移除后残留的连续空行。
    """
    if "[图" not in text:
        return text

    def _sub(m: re.Match) -> str:
        return m.group(0) if int(m.group(1)) in valid_image_ids else ""

    cleaned = _IMG_MARKER_RE.sub(_sub, text)
    cleaned = re.sub(r"[ \t]*\n[ \t]*\n[ \t]*\n+", "\n\n", cleaned)
    return cleaned.strip()


def update_sensitive_rules(rules: list[dict]) -> None:
    global _SENSITIVE_RULES
    _SENSITIVE_RULES = list(rules)


def filter_sensitive_words(text: str, rules: list[dict]) -> str:
    normalized: list[dict] = []
    for r in rules:
        if isinstance(r, str):
            normalized.append({"pattern": r, "replacement": "***"})
        elif isinstance(r, dict):
            normalized.append(r)
    rules_sorted = sorted(normalized, key=lambda r: len(str(r.get("pattern", "") or "")), reverse=True)
    result = text
    for rule in rules_sorted:
        pattern = str(rule.get("pattern", "") or "")
        replacement = str(rule.get("replacement", "") or "***")
        if not pattern:
            continue
        safe_pattern = pattern
        if len(pattern) <= 2 and pattern.isascii() and pattern.replace("\\", "").isalnum():
            safe_pattern = rf"\b{pattern}\b"
        try:
            compiled = re.compile(safe_pattern)
            result = compiled.sub(replacement, result)
        except re.error:
            result = result.replace(pattern, replacement)
    return result


# backward compat — kept for callers that pass list[str]
def update_sensitive_patterns(patterns: list[str]) -> None:
    rules = [{"pattern": p, "replacement": "***"} for p in patterns if p]
    update_sensitive_rules(rules)


def compute_confidence(
    faq_hit: bool = False,
    avg_retrieval_score: float = 0.0,
) -> float:
    if faq_hit:
        return 0.95
    if avg_retrieval_score >= 0.85:
        return 0.85
    if avg_retrieval_score >= 0.7:
        return 0.7
    if avg_retrieval_score >= 0.5:
        return 0.5
    return 0.3


def validate_output_node(state: AgentState) -> AgentState:
    result = copy.deepcopy(state)
    answer = state.get("final_answer", "")

    # 后处理：清除 LLM 可能残留的机器标签、Markdown 标记和思考过程
    answer = re.sub(r'\[来源[：:][^\]]*\]', '', answer)
    answer = re.sub(r'\[FAQ\s*精准匹配\]', '', answer)
    answer = re.sub(r'(?m)^#{1,6}\s+', '', answer)
    answer = re.sub(r'(?m)^-{3,}$', '', answer)
    answer = re.sub(r'(?m)^\s*[-*]\s+', '', answer)
    answer = re.sub(r'\n{3,}', '\n\n', answer)

    valid_image_ids = {img["id"] for img in state.get("doc_images", [])}
    answer = strip_invalid_image_markers(answer, valid_image_ids)
    answer = re.sub(
        r'(?:^(?:首先|我[先再]|根据已有|基于上述|接下来|用户|未找到|让我)'
        r'[^。\n]*?(?:搜索|检索|查找|查看|分析|判断|关键词|尝试|工具|换个)[^。\n]*?[。\n]+)',
        '', answer, flags=re.MULTILINE
    )
    answer = answer.strip()

    filtered = filter_sensitive_words(answer, _SENSITIVE_RULES)
    result["final_answer"] = filtered

    faq_hit = state.get("faq_hit", False)
    docs = state.get("retrieved_docs", [])
    avg_score = sum(d.fused_score for d in docs) / len(docs) if docs else 0.0
    rrf_max = 0.020
    normalized_score = min(avg_score / rrf_max, 1.0) if avg_score > 0 else 0.0
    confidence = compute_confidence(faq_hit=faq_hit, avg_retrieval_score=normalized_score)
    result["confidence"] = confidence

    compliance_issues: list[str] = []
    if filtered != answer:
        compliance_issues.append("sensitive_words_filtered")
    if confidence < 0.5:
        compliance_issues.append("low_confidence")
        result["needs_human"] = True
        result["human_reason"] = f"confidence={confidence:.2f}"

    result["is_compliant"] = len(compliance_issues) == 0
    result["compliance_issues"] = compliance_issues
    return result
