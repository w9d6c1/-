"""文案标题推荐 — 热点(抖音+手动) + 知识库 → 今天要拍的文案标题

每条推荐含：title(文案标题) / hot_word(关联热点词) / hot_url(原视频跳转链接) / reason(切入理由)
"""

import json
import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.llm import call_llm_with_retry, create_llm
from app.articles.hot_topics import build_knowledge_digest
from app.core.logging import logger

_RECOMMEND_PROMPT = """你是短视频编导与内容策划专家，服务于一家企业的短视频团队。该企业拥有一个私有知识库。

今日热点（含可跳转的原视频链接）：
{hot_lines}

知识库领域概况：
{knowledge_digest}

任务要求：
1. 从上述热点中挑选 {count} 个以内适合今天拍摄短视频的热点，结合知识库领域自然切入（可直接同领域，也可借势角度）；
2. 每个选题输出：
   - title: 吸引眼球的短视频文案标题（15-35 字，符合短视频传播习惯，可带悬念/情绪/数字）
   - hot_word: 关联的热点词（必须来自输入热点）
   - hot_url: 该热点对应的原视频跳转链接（必须原样取自输入热点，不得编造）
   - reason: 一句话切入理由（说明结合点）
3. 完全无法结合的热点跳过，宁缺毋滥。

直接返回 JSON 数组，不要有任何额外文字。若无可结合热点，返回空数组 []。"""


async def recommend_copy_titles(
    db: AsyncSession,
    hot_items: list[dict],
    count: int = 10,
) -> list[dict]:
    """根据热点列表 + 知识库生成文案标题推荐。"""
    if not hot_items:
        return []

    hot_lines = [
        f"[{it.get('rank', i + 1)}] {it['title']} | 链接: {it.get('url') or '无'}"
        for i, it in enumerate(hot_items)
    ]

    knowledge_digest = await build_knowledge_digest(db)
    if not knowledge_digest:
        knowledge_digest = "（知识库暂无内容）"

    prompt = _RECOMMEND_PROMPT.format(
        hot_lines="\n".join(hot_lines),
        knowledge_digest=knowledge_digest,
        count=count,
    )

    llm = create_llm(temperature=0.6, max_tokens=3000, top_p=0.9)
    try:
        raw = await call_llm_with_retry(
            llm, [{"role": "user", "content": prompt}], max_retries=2
        )
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if not match:
            return []
        parsed = json.loads(match.group(0))
        results: list[dict] = []
        for item in parsed[:count]:
            if not isinstance(item, dict) or not item.get("title"):
                continue
            results.append({
                "title": str(item.get("title", "")).strip(),
                "hot_word": str(item.get("hot_word", "")).strip(),
                "hot_url": str(item.get("hot_url", "")).strip(),
                "reason": str(item.get("reason", "")).strip(),
            })
        logger.info("copy_titles_recommend_done", count=len(results))
        return results
    except Exception as exc:
        logger.error("copy_titles_recommend_failed", error=str(exc))
        return []
