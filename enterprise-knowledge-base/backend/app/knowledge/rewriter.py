"""查询改写 — 同义词扩展 + 查询标准化"""

import re
import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin.dictionary import Synonym

_synonym_cache: dict[str, list[str]] | None = None
_synonym_cache_time: float = 0.0
_SYNONYM_CACHE_TTL: float = 300.0  # 5 minutes


def normalize_query(query: str) -> str:
    query = re.sub(r"[^\w\s\u4e00-\u9fff]", "", query)
    query = re.sub(r"\s+", " ", query).strip()
    return query.lower()


def expand_synonyms(query: str, synonym_map: dict[str, list[str]]) -> str:
    if not query or not synonym_map:
        return query

    for word, syns in synonym_map.items():
        if word in query:
            parts = [query] + syns
            return " OR ".join(parts)
    return query


def rewrite_query(
    query: str,
    synonym_map: dict[str, list[str]],
    history: list[dict[str, str]] | None = None,
) -> str:
    normalized = normalize_query(query)
    if not normalized:
        return ""

    expanded = expand_synonyms(normalized, synonym_map)

    if history:
        context = " ".join(h.get("content", "") for h in history[-3:])
        if context:
            expanded = f"{context} {expanded}"

    return expanded


async def load_synonym_map(db: AsyncSession) -> dict[str, list[str]]:
    global _synonym_cache, _synonym_cache_time
    now = time.time()
    if _synonym_cache is not None and (now - _synonym_cache_time) < _SYNONYM_CACHE_TTL:
        return _synonym_cache

    result = await db.execute(select(Synonym))
    syn_map: dict[str, list[str]] = {}
    for row in result.scalars():
        syn_map[row.word] = row.synonyms

    _synonym_cache = syn_map
    _synonym_cache_time = now
    return syn_map


def invalidate_synonym_cache() -> None:
    global _synonym_cache, _synonym_cache_time
    _synonym_cache = None
    _synonym_cache_time = 0.0
