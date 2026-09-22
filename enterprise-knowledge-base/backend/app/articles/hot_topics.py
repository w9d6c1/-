"""今日热点 — 多平台热榜抓取 + 结合知识库的智能选题推荐

热榜源（均为实测可用的官方端点）:
- 百度热搜: top.baidu.com/api/board
- 微博热搜: weibo.com/ajax/side/hotSearch（需 Referer + XHR 头）
- 知乎热榜: api.zhihu.com/topstory/hot-list（移动端 API，免 Cookie）
- 头条热榜: toutiao.com/hot-event/hot-board

缓存策略: 模块级内存缓存，TTL 30 分钟；单源失败隔离，不影响其他源。
"""

import asyncio
import json
import re
import time
from urllib.parse import quote

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.llm import call_llm_with_retry, create_llm
from app.core.logging import logger
from app.models.document import KnowledgeDoc
from app.models.faq import KnowledgeFAQ

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
CACHE_TTL_SECONDS = 1800
HTTP_TIMEOUT = 15.0
_MAX_ITEMS_PER_SOURCE = 30

SOURCES = ("baidu", "weibo", "zhihu", "toutiao")
SOURCE_LABELS = {
    "baidu": "百度热搜",
    "weibo": "微博热搜",
    "zhihu": "知乎热榜",
    "toutiao": "头条热榜",
}


# ============================================================
# 各平台抓取器（统一返回 [{rank, title, hot_value, url}]）
# ============================================================

async def _fetch_baidu(client: httpx.AsyncClient) -> list[dict]:
    resp = await client.get(
        "https://top.baidu.com/api/board",
        params={"platform": "wise", "tab": "realtime"},
        headers={"User-Agent": _UA},
    )
    resp.raise_for_status()
    data = resp.json()
    cards = data.get("data", {}).get("cards", [])
    items: list[dict] = []
    for card in cards:
        for group in card.get("content", []):
            for it in group.get("content", []):
                word = (it.get("word") or "").strip()
                if not word:
                    continue
                items.append({
                    "rank": len(items) + 1,
                    "title": word,
                    "hot_value": int(it.get("hotScore") or 0),
                    "url": it.get("url") or it.get("rawUrl") or "",
                })
    return items[:_MAX_ITEMS_PER_SOURCE]


async def _fetch_weibo(client: httpx.AsyncClient) -> list[dict]:
    resp = await client.get(
        "https://weibo.com/ajax/side/hotSearch",
        headers={
            "User-Agent": _UA,
            "Referer": "https://weibo.com/hot/search",
            "Accept": "application/json, text/plain, */*",
            "X-Requested-With": "XMLHttpRequest",
        },
    )
    resp.raise_for_status()
    data = resp.json()
    items: list[dict] = []
    for it in data.get("data", {}).get("realtime", []):
        word = (it.get("word") or "").strip()
        if not word or it.get("is_ad"):
            continue
        items.append({
            "rank": len(items) + 1,
            "title": word,
            "hot_value": int(it.get("num") or 0),
            "url": f"https://s.weibo.com/weibo?q={quote(word)}",
        })
    return items[:_MAX_ITEMS_PER_SOURCE]


async def _fetch_zhihu(client: httpx.AsyncClient) -> list[dict]:
    resp = await client.get(
        "https://api.zhihu.com/topstory/hot-list",
        params={"limit": 50},
        headers={"User-Agent": _UA},
    )
    resp.raise_for_status()
    data = resp.json()
    items: list[dict] = []
    for it in data.get("data", []):
        target = it.get("target") or {}
        title = (target.get("title") or "").strip()
        if not title:
            continue
        detail_text = it.get("detail_text", "")
        hot_value = int(re.sub(r"[^\d]", "", detail_text) or 0)
        items.append({
            "rank": len(items) + 1,
            "title": title,
            "hot_value": hot_value,
            "url": target.get("url") or "",
        })
    return items[:_MAX_ITEMS_PER_SOURCE]


async def _fetch_toutiao(client: httpx.AsyncClient) -> list[dict]:
    resp = await client.get(
        "https://www.toutiao.com/hot-event/hot-board/",
        params={"origin": "toutiao_pc"},
        headers={"User-Agent": _UA},
    )
    resp.raise_for_status()
    data = resp.json()
    items: list[dict] = []
    for it in data.get("data", []):
        title = (it.get("Title") or "").strip()
        if not title:
            continue
        items.append({
            "rank": len(items) + 1,
            "title": title,
            "hot_value": int(it.get("HotValue") or 0),
            "url": it.get("Url") or "",
        })
    return items[:_MAX_ITEMS_PER_SOURCE]


_FETCHERS = {
    "baidu": _fetch_baidu,
    "weibo": _fetch_weibo,
    "zhihu": _fetch_zhihu,
    "toutiao": _fetch_toutiao,
}


# ============================================================
# 内存缓存（TTL 30 分钟，单源独立）
# ============================================================

_cache: dict[str, tuple[float, list[dict]]] = {}
_lock = asyncio.Lock()


async def _fetch_source(source: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True) as client:
        for attempt in range(2):
            try:
                items = await _FETCHERS[source](client)
                if items:
                    return items
            except Exception as exc:
                logger.warning(
                    "hot_topics_fetch_failed",
                    source=source,
                    attempt=attempt + 1,
                    error=str(exc),
                )
                if attempt == 0:
                    await asyncio.sleep(1)
    return []


async def get_hot_topics(refresh: bool = False) -> dict:
    """抓取四源热榜（带缓存）。

    返回:
        {
          "sources": {source: {"label", "ok", "items", "cached_at"}},
          "updated_at": float,
        }
    """
    now = time.time()
    result: dict = {"sources": {}, "updated_at": now}

    async with _lock:
        to_fetch: list[str] = []
        for source in SOURCES:
            cached = _cache.get(source)
            if not refresh and cached and now - cached[0] < CACHE_TTL_SECONDS:
                result["sources"][source] = {
                    "label": SOURCE_LABELS[source],
                    "ok": True,
                    "items": cached[1],
                    "cached_at": cached[0],
                }
            else:
                to_fetch.append(source)

        if to_fetch:
            fetched = await asyncio.gather(
                *[_fetch_source(s) for s in to_fetch], return_exceptions=False
            )
            for source, items in zip(to_fetch, fetched, strict=True):
                ts = time.time()
                if items:
                    _cache[source] = (ts, items)
                    result["sources"][source] = {
                        "label": SOURCE_LABELS[source],
                        "ok": True,
                        "items": items,
                        "cached_at": ts,
                    }
                else:
                    stale = _cache.get(source)
                    if stale:
                        result["sources"][source] = {
                            "label": SOURCE_LABELS[source],
                            "ok": True,
                            "items": stale[1],
                            "cached_at": stale[0],
                            "stale": True,
                        }
                    else:
                        result["sources"][source] = {
                            "label": SOURCE_LABELS[source],
                            "ok": False,
                            "items": [],
                            "cached_at": None,
                        }
                    logger.warning("hot_topics_source_unavailable", source=source)

    return result


# ============================================================
# 知识库摘要（作为 LLM 领域上下文）
# ============================================================

async def build_knowledge_digest(db: AsyncSession, limit: int = 30) -> str:
    """从知识库文档标题 + FAQ 问题构建领域摘要，供推荐 LLM 使用。"""
    doc_rows = await db.execute(
        select(KnowledgeDoc.title)
        .where(KnowledgeDoc.status == "published")
        .order_by(KnowledgeDoc.updated_at.desc())
        .limit(limit)
    )
    doc_titles = [r[0] for r in doc_rows.all()]

    faq_rows = await db.execute(
        select(KnowledgeFAQ.question)
        .where(KnowledgeFAQ.status == "online")
        .order_by(KnowledgeFAQ.updated_at.desc())
        .limit(limit)
    )
    faq_questions = [r[0] for r in faq_rows.all()]

    parts: list[str] = []
    if doc_titles:
        parts.append("知识库文档标题：\n" + "\n".join(f"- {t}" for t in doc_titles))
    if faq_questions:
        parts.append("知识库 FAQ 问题：\n" + "\n".join(f"- {q}" for q in faq_questions))
    return "\n\n".join(parts)


# ============================================================
# 智能选题推荐（一次 LLM 调用）
# ============================================================

_RECOMMEND_PROMPT = """你是内容营销选题专家，服务于一家企业的内容团队。该企业拥有一个私有知识库，你需要从今日全网热点中挑选能与知识库领域自然结合的热点，策划文章选题。

知识库领域概况：
{knowledge_digest}

{company_direction}

今日热点列表（格式：[来源] 标题）：
{hot_list}

任务要求：
1. 从热点中挑选 {max_topics} 个以内能与知识库领域产生关联的热点；关联可以是直接的（同领域），也可以是间接的（借势角度、类比、场景延伸），但必须自然不牵强；
2. 完全无法关联的热点直接跳过，宁缺毋滥；
3. 每个选中的热点输出：
   - hot_title: 热点原标题
   - source: 热点来源（baidu/weibo/zhihu/toutiao）
   - reason: 为什么这个热点适合结合（一句话，说明切入角度）
   - suggested_topic: 建议的文章创作主题（20-50字，可直接用于文章生成）
   - titles: 2-3 个吸引眼球的文章标题（结合热点与知识库内容，符合中文新媒体传播习惯）

直接返回 JSON 数组，不要有任何额外文字。若没有任何可结合的热点，返回空数组 []。"""


async def recommend_titles(
    db: AsyncSession,
    max_topics: int = 8,
    company_direction: str = "",
) -> dict:
    """抓取热榜 + 知识库摘要 → LLM 推荐选题。

    company_direction: 公司创作方向（自由文本），用于约束选题贴合企业想覆盖的方面；
                       为空时保持原行为（不加入方向约束）。
    """
    hot_data = await get_hot_topics(refresh=False)

    hot_lines: list[str] = []
    for source in SOURCES:
        src = hot_data["sources"].get(source)
        if not src or not src.get("ok"):
            continue
        for it in src["items"]:
            hot_lines.append(f"[{source}] {it['title']}")

    if not hot_lines:
        return {"recommendations": [], "hot_count": 0, "message": "热榜抓取失败，请稍后重试"}

    knowledge_digest = await build_knowledge_digest(db)
    if not knowledge_digest:
        knowledge_digest = "（知识库暂无内容）"

    company_section = ""
    if company_direction and company_direction.strip():
        company_section = (
            f"公司本次创作的指定方向（请优先挑选能自然契合此方向的热点）：\n"
            f"{company_direction.strip()}\n"
        )

    prompt = _RECOMMEND_PROMPT.format(
        knowledge_digest=knowledge_digest,
        company_direction=company_section,
        hot_list="\n".join(hot_lines),
        max_topics=max_topics,
    )

    llm = create_llm(temperature=0.5, max_tokens=3000, top_p=0.9)
    try:
        raw = await call_llm_with_retry(llm, [{"role": "user", "content": prompt}], max_retries=2)
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        recommendations: list[dict] = []
        if match:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, list):
                for item in parsed[:max_topics]:
                    if not isinstance(item, dict) or not item.get("hot_title"):
                        continue
                    recommendations.append({
                        "hot_title": str(item.get("hot_title", "")),
                        "source": str(item.get("source", "")),
                        "reason": str(item.get("reason", "")),
                        "suggested_topic": str(item.get("suggested_topic", "")),
                        "titles": [str(t) for t in item.get("titles", []) if str(t).strip()],
                    })
        logger.info("hot_topics_recommend_done", count=len(recommendations))
        return {
            "recommendations": recommendations,
            "hot_count": len(hot_lines),
            "message": "",
        }
    except Exception as exc:
        logger.error("hot_topics_recommend_failed", error=str(exc))
        return {
            "recommendations": [],
            "hot_count": len(hot_lines),
            "message": f"推荐生成失败: {exc}",
        }
