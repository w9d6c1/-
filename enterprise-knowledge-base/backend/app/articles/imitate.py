"""文章模仿生成 — 分析参考文章风格并模仿创作新文章

复用: app.agents.llm (create_llm, call_llm_with_retry), app.retrieval.fusion (hybrid_retrieve)
"""

import json
import re

import httpx

from app.agents.llm import call_llm_with_retry, create_llm
from app.core.config import settings
from app.core.logging import logger
from app.retrieval.fusion import FusionResult, hybrid_retrieve


# ============================================================
# 通用网页正文抓取 — 三层 fallback
# ============================================================

_FETCH_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


async def fetch_article_content(url: str, use_jina_fallback: bool = True) -> str:
    """通用网页正文抓取，三层 fallback。

    1. trafilatura — 快速，覆盖大多数博客/新闻站（无 JS 渲染）
    2. readability-lxml — Mozilla 可读性算法，对简单 HTML 更稳定
    3. Jina Reader API — 免费 API，自动处理 JS 渲染站点（微信/知乎等）
    """

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        resp = await client.get(url, headers={"User-Agent": _FETCH_UA})
        resp.raise_for_status()

        cl = resp.headers.get("content-length")
        if cl and int(cl) > 10 * 1024 * 1024:
            raise ValueError("网页内容过大（超过 10MB），请直接粘贴文章内容")

        content_type = resp.headers.get("content-type", "")
        if "html" not in content_type.lower() and "text" not in content_type.lower():
            raise ValueError("网页不是文本内容，请直接粘贴文章或提供文章链接")

        html = resp.text

    # --- Tier 1: trafilatura ---
    try:
        import trafilatura

        text = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=False,
            output_format="txt",
        )
        if text and len(text.strip()) >= 100:
            logger.info("fetch_article_tier1_trafilatura", url=url[:80])
            return text.strip()
    except Exception as exc:
        logger.debug("trafilatura_failed", url=url[:80], error=str(exc))

    # --- Tier 2: readability-lxml ---
    try:
        from readability import Document

        doc = Document(html)
        raw = doc.summary()
        raw = re.sub(r"<[^>]+>", "\n", raw)
        raw = re.sub(r"\n\s*\n", "\n", raw)
        lines = [line.strip() for line in raw.split("\n") if len(line.strip()) > 20]
        text = "\n\n".join(lines)
        if text and len(text.strip()) >= 100:
            logger.info("fetch_article_tier2_readability", url=url[:80])
            return text.strip()
    except Exception as exc:
        logger.debug("readability_failed", url=url[:80], error=str(exc))

    # --- Tier 3: Jina Reader API ---
    if use_jina_fallback:
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                jina_resp = await client.get(
                    f"https://r.jina.ai/{url}",
                    headers={"Accept": "text/markdown"},
                )
                if jina_resp.status_code == 200:
                    text = jina_resp.text
                    if text and len(text.strip()) >= 100:
                        logger.info("fetch_article_tier3_jina", url=url[:80])
                        return text.strip()
        except Exception as exc:
            logger.debug("jina_failed", url=url[:80], error=str(exc))

    raise ValueError("无法从该网页提取有效正文，请尝试直接粘贴文章内容")

# ============================================================
# Step 1: 风格分析
# ============================================================

_STYLE_ANALYSIS_PROMPT = """你是一位专业内容编辑。请分析下面这篇文章的写作风格和结构模板，用于后续模仿创作。

## 参考文章
{source_text}

## 分析要求
请从以下 5 个维度分析，返回 **纯 JSON**（不要 markdown 代码块）：

1. **tone** (语气): 专业权威 / 亲切顾问 / 营销说服 / 故事叙述 / 数据分析
2. **opening_style** (开头方式): 场景故事引入 / 痛点提问直击 / 数据震撼 / 定义先行
3. **structure** (段落结构): 总分总 / 问题→方案→结果 / 原理→案例→对比 / 并列论述
4. **argument_pattern** (论证手法): 理论分析 / 案例佐证 / 数据支撑 / 对比突出
5. **closing_style** (结尾方式): 行动号召 / 总结升华 / 引导咨询 / 留白思考

另外提炼一个 **style_description**（50 字以内）简要概括这篇文章的写作特征。

返回格式：
{{"tone": "...", "opening_style": "...", "structure": "...", "argument_pattern": "...", "closing_style": "...", "style_description": "..."}}"""


async def analyze_style(source_text: str) -> dict:
    """分析参考文章的风格，返回结构化模板"""
    llm = create_llm(temperature=0.2, max_tokens=800, top_p=0.85)
    prompt = _STYLE_ANALYSIS_PROMPT.format(source_text=source_text[:6000])
    messages = [{"role": "user", "content": prompt}]

    try:
        raw = await call_llm_with_retry(llm, messages, max_retries=2)
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            result = json.loads(match.group(0))
            logger.info("style_analyzed", tone=result.get("tone"))
            return result
    except Exception as exc:
        logger.warning("style_analysis_failed", error=str(exc))

    # 兜底默认风格
    return {
        "tone": "专业权威",
        "opening_style": "痛点提问直击",
        "structure": "问题→方案→结果",
        "argument_pattern": "理论分析+案例佐证",
        "closing_style": "引导咨询",
        "style_description": "专业技术分析类文章，先提痛点再给方案",
    }


# ============================================================
# Step 2: 检索知识库
# ============================================================

async def retrieve_knowledge(topic: str, top_k: int = 8) -> str:
    """检索知识库，返回上下文文本"""
    try:
        results = await hybrid_retrieve(topic, scope="public", top_k=top_k)
        parts = [r.content for r in results[:5]]
        return "\n\n---\n\n".join(parts) if parts else ""
    except Exception as exc:
        logger.warning("imitate_retrieve_failed", error=str(exc))
        return ""


# ============================================================
# Step 3: 模仿生成
# ============================================================

_IMITATE_PROMPT = """你是专业文章撰写助手，请模仿指定风格创作一篇新文章。严格遵守以下硬性规则：

硬性规则：
1. 全文只输出纯净正文，禁止使用 Markdown 排版符号（#、*、-、>、分割线、加粗标记等），但配图标记 [IMAGE: 照片N: 配图建议: xxx] 不受此规则限制；
2. 禁止输出任何内心思考、推理过程、分析草稿、步骤拆解、内心独白，不能出现"思考、分析、首先、第一步、接下来"这类推理类文字；
3. 不要分段标题、不要分点罗列，全文流畅连贯成完整段落；
4. 只输出最终成品文章，不得输出前置说明、后置总结注释；
5. 如果需要分层表达，只用自然文字衔接，严禁使用任何符号区分层级；
6. 目标字数：正文（不含配图标记）必须达到 {min_words}-{max_words} 字，字数不足或超标都会被判定任务失败。

配图规则（此规则优先级高于规则 1）：
- 根据下方照片编号、标签与描述，在正文合适位置为每张照片插入配图标记，格式为 [IMAGE: 照片N: 配图建议: 与照片实际内容一致的具体描述]
- N 必须来自下方照片编号；每张照片至少使用一次；配图描述必须同时结合该照片的标签与描述撰写（标签标明场景/工艺/材料要点，描述说明画面细节），禁止只看其一；严禁编造照片中没有的内容
- 每处配图标记独占一行，放在自然段落之间

主题：{topic}

模仿风格：{style_description}
具体请遵循：
- 语气：{tone}
- 开头方式：{opening_style}
- 段落结构：{structure}
- 论证手法：{argument_pattern}
- 结尾方式：{closing_style}

参考知识（来自知识库，用于提供事实依据，不要直接复制）：
{knowledge_context}

照片信息：
{photo_context}
{photo_instruction}

请直接输出文章正文。"""


async def imitate_article(
    topic: str,
    style_analysis: dict,
    knowledge_context: str = "",
    photo_descriptions: str = "",
    photo_object_names: list[str] | None = None,
    min_words: int | None = None,
    max_words: int | None = None,
) -> dict:
    """基于风格模板生成模仿文章"""
    min_words = min_words or settings.article_min_words
    max_words = max_words or settings.article_max_words
    max_tokens = min(int(max_words * 1.6) + 1024, 8192)
    llm = create_llm(temperature=0.6, max_tokens=max_tokens, top_p=0.9)
    photo_count = len(photo_object_names or [])
    photo_context_str = photo_descriptions if photo_descriptions else "（照片描述将在下文列出）"
    if photo_count > 0:
        photo_names_hint = "、".join(photo_object_names[:3]) if photo_object_names else "相关照片"
        photo_index_text = "\n".join(
            f"{i + 1}. 照片{i + 1}（文件名：{name.rsplit('/', 1)[-1]}）"
            for i, name in enumerate(photo_object_names)
        )
        photo_instruction_str = (
            f"文章配有 {photo_count} 张现场照片（{photo_names_hint} 等），编号如下：\n"
            f"{photo_index_text}\n"
            f"请在正文合适位置为这些照片插入配图标记，每张照片至少使用一次，"
            f"格式为 [IMAGE: 照片N: 配图建议: 与照片实际内容一致的具体描述]，N 必须来自上方编号；"
            f"配图描述必须同时结合该照片的标签与描述（标签标明场景/工艺/材料要点，描述说明画面细节），禁止只看其一；"
            f"描述严禁编造照片中没有的内容；每处标记独占一行。"
        )
    else:
        photo_instruction_str = "（无照片，不需要插入配图标记）"

    # 先生成标题
    title_prompt = f'为主题"{topic}"生成一个模仿{style_analysis.get("tone","专业")}风格的 SEO 优化文章标题（25字以内，不含引号）。只输出标题。'
    try:
        title_raw = await call_llm_with_retry(
            llm, [{"role": "user", "content": title_prompt}], max_retries=2, clean=True
        )
        title = title_raw.strip().strip('"').strip("《》")
    except Exception:
        title = topic

    # 生成正文
    prompt = _IMITATE_PROMPT.format(
        topic=topic,
        tone=style_analysis.get("tone", "专业权威"),
        opening_style=style_analysis.get("opening_style", "痛点提问直击"),
        structure=style_analysis.get("structure", "问题→方案→结果"),
        argument_pattern=style_analysis.get("argument_pattern", "理论分析+案例佐证"),
        closing_style=style_analysis.get("closing_style", "引导咨询"),
        style_description=style_analysis.get("style_description", "专业技术分析风格"),
        knowledge_context=knowledge_context or "（暂无相关知识库内容）",
        photo_context=photo_context_str,
        photo_instruction=photo_instruction_str,
        min_words=min_words,
        max_words=max_words,
    )

    try:
        content = await call_llm_with_retry(
            create_llm(temperature=0.6, max_tokens=max_tokens, top_p=0.9),
            [{"role": "user", "content": prompt}],
            max_retries=2,
            clean=True,
        )
    except Exception as exc:
        logger.error("imitate_generation_failed", error=str(exc))
        content = f"（生成失败：{exc}）"

    # 字数校验：超限截断 → 不足自动扩写修复（一次）
    from app.articles.generator import (
        _count_words,
        _repair_article_words,
        _truncate_content,
    )

    content = _truncate_content(content, max_words)
    if _count_words(content) < min_words:
        content = await _repair_article_words(
            content, min_words, max_words, max_tokens, {"top_p": 0.9}
        )
        content = _truncate_content(content, max_words)

    # 提取配图标记（照片N 精确映射，旧格式回退）
    image_placement = []
    if photo_object_names:
        from app.articles.generator import _extract_image_placements
        image_placement = _extract_image_placements(content, photo_object_names)

    return {
        "title": title,
        "content": content,
        "word_count": _count_words(content),
        "image_placement": image_placement,
    }
