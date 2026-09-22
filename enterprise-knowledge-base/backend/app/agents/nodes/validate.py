"""输入校验节点 — 敏感词预设回答 / 禁答词（按渠道隔离） / SQL注入 / Prompt注入检测 🔒"""

import copy
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.state import AgentState
from app.core.logging import logger

_BLOCKED_RULES: list[dict] = []       # [{word: str, scope: str}]
_SENSITIVE_RESPONSES: list[dict] = [] # [{word: str, answer: str, scope: str}]

_SQL_INJECTION_RE = re.compile(
    r"\b(DROP\s+TABLE|DELETE\s+FROM|INSERT\s+INTO|UNION\s+SELECT|ALTER\s+TABLE|TRUNCATE\s+TABLE|EXEC\s*\(|EXECUTE\s+|SELECT\s+[\*\w,\s]+\s+FROM)\b",
    re.IGNORECASE,
)

_PROMPT_INJECTION_RE = re.compile(
    r"\b(ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|rules?|directives?|prompts?)|"
    r"system\s+prompt|"
    r"you\s+are\s+(now\s+)?(a\s+)?(different|not|no\s+longer)|"
    r"bypass\s+security|"
    r"jailbreak|"
    r"<\|im_start\|>|<\|im_end\|>|"
    r"disregard\s+(all\s+)?(instructions?|rules?|safeguards?)|"
    r"reveal\s+(your\s+)?(system\s+)?(prompt|instructions?))\b",
    re.IGNORECASE,
)


async def load_words_from_db(db: AsyncSession) -> dict[str, list]:
    from app.api.admin.dictionary import SensitiveWord

    result_dict: dict[str, list] = {"forbid": [], "sensitive": [], "sensitive_rules": []}
    blocked_rules: list[dict] = []
    response_rules: list[dict] = []
    try:
        r = await db.execute(select(SensitiveWord))
        for row in r.scalars():
            w_scope = row.scope or "all"
            if row.word_type == "forbid":
                result_dict["forbid"].append(row.word)
                blocked_rules.append({"word": row.word, "scope": w_scope})
                if row.answer:
                    response_rules.append({"word": row.word, "answer": row.answer, "scope": w_scope})
            elif row.word_type == "sensitive":
                result_dict["sensitive"].append(row.word)
                result_dict["sensitive_rules"].append({
                    "pattern": row.word,
                    "replacement": row.answer if row.answer else "***",
                })
    except Exception:
        logger.debug("load_words_from_db_failed", exc_info=True)
    update_blocked_rules(blocked_rules)
    update_sensitive_response_rules(response_rules)
    return result_dict


def update_blocked_patterns(patterns: list[str]) -> None:
    global _BLOCKED_RULES
    _BLOCKED_RULES = _to_rules(patterns)


def update_blocked_rules(rules: list[dict]) -> None:
    global _BLOCKED_RULES
    _BLOCKED_RULES = list(rules)


def load_blocked_patterns() -> list[str]:
    return [r["word"] for r in _BLOCKED_RULES]


def _to_rules(words: list[str]) -> list[dict]:
    return [{"word": w, "scope": "all"} for w in words if w]


def update_sensitive_response_map(response_map: dict[str, str]) -> None:
    global _SENSITIVE_RESPONSES
    _SENSITIVE_RESPONSES = [{"word": k, "answer": v, "scope": "all"} for k, v in response_map.items()]


def update_sensitive_response_rules(rules: list[dict]) -> None:
    global _SENSITIVE_RESPONSES
    _SENSITIVE_RESPONSES = list(rules)


def load_sensitive_response_map() -> dict[str, str]:
    return {r["word"]: r["answer"] for r in _SENSITIVE_RESPONSES}


def _scope_match(rule_scope: str, channel: str) -> bool:
    return rule_scope == "all" or rule_scope == channel


def detect_sql_injection(query: str) -> bool:
    return bool(_SQL_INJECTION_RE.search(query))


def detect_prompt_injection(query: str) -> bool:
    return bool(_PROMPT_INJECTION_RE.search(query))


def validate_input_node(state: AgentState) -> AgentState:
    result = copy.deepcopy(state)
    query = state.get("original_query", "")
    channel = state.get("channel", "")

    if not query or not query.strip():
        result["is_blocked"] = True
        result["block_reason"] = "empty_query"
        result["route"] = "reject"
        return result

    if detect_sql_injection(query):
        result["is_blocked"] = True
        result["block_reason"] = "sql_injection_detected"
        result["route"] = "reject"
        return result

    if detect_prompt_injection(query):
        result["is_blocked"] = True
        result["block_reason"] = "prompt_injection_detected"
        result["route"] = "reject"
        return result

    for rule in _SENSITIVE_RESPONSES:
        kw = rule["word"]
        if not kw or kw not in query:
            continue
        if not _scope_match(rule["scope"], channel):
            continue
        result["final_answer"] = rule["answer"]
        result["is_blocked"] = False
        result["block_reason"] = ""
        result["route"] = "sensitive_canned"
        result["confidence"] = 1.0
        result["faq_hit"] = True
        return result

    for rule in _BLOCKED_RULES:
        kw = rule["word"]
        if not kw or kw not in query:
            continue
        if not _scope_match(rule["scope"], channel):
            continue
        result["is_blocked"] = True
        result["block_reason"] = f"blocked_pattern: {kw}"
        result["route"] = "reject"
        return result

    result["is_blocked"] = False
    result["block_reason"] = ""
    return result
