"""知乎公开页正文提取 — 优先 js-initialData JSON，兜底 RichText HTML。

文章页与回答页均在 ``<script id="js-initialData">`` 中内嵌全文 JSON
（initialState.entities.articles / answers 下的 content 字段）；
JSON 缺失或解析失败时回退提取 SSR 的 ``RichText`` 外层 div 内部 HTML。
"""

import json
import re

_INITIAL_DATA_RE = re.compile(r'<script[^>]*id="js-initialData"[^>]*>(.*?)</script>', re.S)
_RICHTEXT_OPEN_RE = re.compile(r'<div[^>]*class="[^"]*RichText[^"]*"[^>]*>', re.S)
_DIV_TAG_RE = re.compile(r"</?div\b[^>]*>", re.I)


def _load_initial_data(html: str) -> dict | None:
    match = _INITIAL_DATA_RE.search(html)
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def _content_from_entities(data: dict) -> str | None:
    state = data.get("initialState")
    if not isinstance(state, dict):
        state = data
    entities = state.get("entities")
    if not isinstance(entities, dict):
        return None
    for key in ("articles", "answers"):
        bucket = entities.get(key)
        if not isinstance(bucket, dict):
            continue
        for item in bucket.values():
            content = item.get("content") if isinstance(item, dict) else None
            if isinstance(content, str) and content.strip():
                return content
    return None


def _extract_richtext(html: str) -> str | None:
    """提取首个 RichText div 的内部 HTML（div 配平扫描）。"""
    open_match = _RICHTEXT_OPEN_RE.search(html)
    if not open_match:
        return None
    start = open_match.end()
    depth = 1
    for tag in _DIV_TAG_RE.finditer(html, start):
        depth += -1 if tag.group(0).startswith("</") else 1
        if depth == 0:
            inner = html[start:tag.start()]
            return inner or None
    return None


def extract_content_html(html: str) -> str | None:
    """从知乎公开页提取正文 HTML；无法提取返回 None。"""
    if not html or not html.strip():
        return None
    data = _load_initial_data(html)
    if data is not None:
        content = _content_from_entities(data)
        if content:
            return content
    return _extract_richtext(html)
