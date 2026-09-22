"""文章生成引擎 — 三步流水线：检索 → 规划角度 → 逐篇生成

复用:
- app.agents.llm.create_llm() / call_llm_with_retry()
- app.retrieval.fusion.hybrid_retrieve()

内存策略：逐篇生成 → 即时写 DB → del 释放，任何时候内存中只保留 1 篇文章。
"""

import asyncio
import json
import re

from app.agents.llm import call_llm_with_retry, clean_response, create_llm
from app.articles.template_service import ACCOUNT_ANGLE_HINTS, ACCOUNT_TYPES
from app.core.config import settings
from app.core.logging import logger
from app.retrieval.fusion import FusionResult, hybrid_retrieve

# ============================================================
# 默认 5 个角度 + 检索查询关键词
# ============================================================

DEFAULT_ANGLES: list[dict] = [
    {
        "key": "technical_detail",
        "label": "技术原理解析",
        "retrieval_query": "电渗透防水技术原理 工作原理 技术参数 系统组成",
        "temperature": 0.4,
        "top_p": 0.85,
    },
    {
        "key": "case_study",
        "label": "案例实践分享",
        "retrieval_query": "电渗透防水工程案例 施工案例 地下室防水 应用效果",
        "temperature": 0.5,
        "top_p": 0.9,
    },
    {
        "key": "benefit_analysis",
        "label": "优势效益分析",
        "retrieval_query": "电渗透防水优势 防水效果对比 节能环保 经济效益",
        "temperature": 0.4,
        "top_p": 0.85,
    },
    {
        "key": "comparison",
        "label": "方案对比分析",
        "retrieval_query": "电渗透与传统防水对比 防水方案比较 技术选型",
        "temperature": 0.4,
        "top_p": 0.85,
    },
    {
        "key": "maintenance_guide",
        "label": "选购施工指南",
        "retrieval_query": "电渗透防水维护保养 常见问题 选购注意事项",
        "temperature": 0.4,
        "top_p": 0.85,
    },
]


# ============================================================
# Step 1: 知识检索
# ============================================================

async def retrieve_knowledge(
    angles: list[dict],
    scope: str = "public",
    top_k: int = 8,
) -> dict[str, list[FusionResult]]:
    """对每个角度执行 hybrid_retrieve，返回 angle_key → 检索结果 的映射。"""
    results: dict[str, list[FusionResult]] = {}
    for angle in angles:
        query = angle.get("retrieval_query", angle["label"])
        try:
            retrieved = await hybrid_retrieve(query, scope=scope, top_k=top_k)
            results[angle["key"]] = retrieved
            logger.info(
                "article_retrieve_done",
                angle=angle["key"],
                count=len(retrieved),
            )
        except Exception as exc:
            logger.warning("article_retrieve_failed", angle=angle["key"], error=str(exc))
            results[angle["key"]] = []
    return results


# ============================================================
# Step 2: 规划角度（一次 LLM 调用）
# ============================================================

_ANGLE_PLAN_PROMPT = """你是 GEO 内容策略专家，专精于建筑防潮防水领域。

用户要撰写一批关于以下主题的文章：
【主题】{topic}

{account_type_section}

参考知识摘要：
{knowledge_summary}

图片信息（含标签与描述，标签可能存在为空）：
{photo_descriptions}

请为上述主题规划 {count} 个**互不重复**的文章角度，确保覆盖目标读者需求。
每个角度必须包含：
- key: 英文标识（如 technical_case）
- label: 中文角度名称（4-8字）
- retrieval_query: 用于知识库检索的搜索词（10-30字）
- tone: 文章语气（professional/case_story/persuasive/comparative/guide）
- target_audience: 目标读者（如"业主"、"施工方"、"设计师"）

直接返回 JSON 数组，不要有任何额外文字。"""


async def plan_angles(
    topic: str,
    photo_descriptions: str = "",
    knowledge_summary: str = "",
    count: int = 5,
    account_type: str | None = None,
) -> list[dict]:
    """调用 LLM 规划差异化角度；失败时退回默认角度。

    account_type: 目标账号类型（user/designer/dealer），用于约束角度贴合该人群。
    """
    account_section = ""
    if account_type and account_type in ACCOUNT_ANGLE_HINTS:
        account_section = (
            f"本次文章的目标读者人群：{ACCOUNT_TYPES.get(account_type, account_type)}。\n"
            f"角度必须从该人群视角出发：{ACCOUNT_ANGLE_HINTS[account_type]}"
        )
    else:
        account_section = "（未指定人群，角度自由发挥，覆盖不同读者需求）"

    llm = create_llm(temperature=0.5, max_tokens=2048, top_p=0.9)
    prompt = _ANGLE_PLAN_PROMPT.format(
        topic=topic,
        account_type_section=account_section,
        knowledge_summary=knowledge_summary or "（暂无相关知识库内容）",
        photo_descriptions=photo_descriptions or "（无现场照片）",
        count=count,
    )
    messages = [{"role": "user", "content": prompt}]

    try:
        raw = await call_llm_with_retry(llm, messages, max_retries=2)
        # 提取 JSON 数组
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if match:
            angles = json.loads(match.group(0))
            if isinstance(angles, list) and len(angles) >= count:
                logger.info("article_angles_planned", count=len(angles[:count]))
                return angles[:count]
    except Exception as exc:
        logger.warning("article_angle_plan_failed", error=str(exc))

    # 退回默认角度
    logger.info("article_angles_fallback", count=min(count, len(DEFAULT_ANGLES)))
    return DEFAULT_ANGLES[:count]


# ============================================================
# Step 3: 逐篇生成文章
# ============================================================

_ARTICLE_PROMPT = """你是专业文章撰写助手，专精于建筑防潮防水行业。严格遵守以下硬性规则，违规会判定任务失败：

硬性规则：
1. 全文只输出纯净正文，禁止输出任何Markdown符号，包括#、*、-、>、`、分割线、加粗标记等一切格式符号；
2. 禁止输出任何内心思考、推理过程、分析草稿、步骤拆解、内心独白，不能出现"思考、分析、首先、第一步、接下来"这类推理类文字；
3. 不要分段标题、不要分点罗列，全文流畅连贯成完整段落；
4. 只输出最终成品文章，不得输出前置说明、后置总结注释；
5. 如果需要分层表达，只用自然文字衔接，严禁使用任何符号区分层级；
6. 输出内容不能带任何注释、标记、占位符。

注意：[IMAGE: 照片N: 配图建议: xxx] 是系统配图占位符，必须按需插入，不受规则1限制；N 必须是下方照片列表中的编号。

写作任务：
- 主题：{topic}
- 角度：{angle_label}（{angle_key}）
- 语气：{tone}
- 目标读者：{target_audience}
- 目标字数：正文（不含配图标记）必须达到 {min_words}-{max_words} 字。字数不足或超标都会被判定任务失败，需要重新撰写。

参考知识（来自知识库，用于提供事实依据，不要直接复制）：
{retrieved_context}

现场照片信息（每条含：标签 + 描述，标签可能存在为空）：
{photo_descriptions}
{photo_instruction}
{template_section}

请直接输出文章正文。"""


async def generate_single_article(
    topic: str,
    angle: dict,
    retrieved_context: list[FusionResult],
    photo_descriptions: str = "",
    photo_object_names: list[str] | None = None,
    template_instructions: str = "",
    min_words: int | None = None,
    max_words: int | None = None,
    account_type: str | None = None,
) -> dict:
    """生成单篇文章，返回 {title, content, word_count, angle_key, image_placement}。"""
    min_words = min_words or settings.article_min_words
    max_words = max_words or settings.article_max_words

    # 知识上下文（取 top-3 片段以控制 prompt 长度）
    context_parts = [clean_response(r.content) for r in retrieved_context[:3]]
    context_text = "\n\n---\n\n".join(context_parts) if context_parts else "（暂无相关知识库内容）"

    # 输出 token 上限按目标字数动态放大（中文约 1 token≈1 字，留足余量，防截断）
    max_tokens = min(int(max_words * 1.6) + 1024, 8192)
    llm = create_llm(
        temperature=angle.get("temperature", settings.article_temperature),
        max_tokens=max_tokens,
        top_p=angle.get("top_p", settings.article_top_p),
    )

    # 先生成标题
    title_prompt = f'为主题"{topic}"、角度"{angle["label"]}"生成一个 SEO 优化的文章标题（20字以内，不含引号）。只输出标题，不要其他内容。'
    try:
        title_raw = await call_llm_with_retry(
            llm, [{"role": "user", "content": title_prompt}], max_retries=2, clean=True
        )
        title = title_raw.strip().strip('"').strip("《》")
    except Exception:
        title = f"{topic}——{angle['label']}"

    # 生成正文
    photo_desc_text = photo_descriptions or "（无现场照片）"
    photo_count = len(photo_object_names) if photo_object_names else 0

    if photo_count > 0:
        photo_index_text = "\n".join(
            f"{i + 1}. 照片{i + 1}（文件名：{name.rsplit('/', 1)[-1]}）"
            for i, name in enumerate(photo_object_names)
        )
        photo_instruction = (
            f"文章中有 {photo_count} 张现场照片需要配合展示，编号如下：\n"
            f"{photo_index_text}\n"
            f"请在正文合适位置为每张照片插入配图标记，格式为 [IMAGE: 照片N: 配图建议: 与照片实际内容一致的具体描述]。\n"
            f"N 必须来自上方照片编号；配图描述必须同时结合该照片的标签与描述撰写（标签标明场景/工艺/材料/设备要点，描述说明画面细节），两者都要作为依据，禁止只看其一；禁止凭空编造照片中没有的场景、设备或工艺；"
            f"每张照片至少使用一次，每处标记独占一行。\n"
            f"示例：[IMAGE: 照片1: 配图建议: 电渗透电极安装细节]"
        )
    else:
        photo_instruction = "（无照片）"

    prompt = _ARTICLE_PROMPT.format(
        topic=topic,
        angle_label=angle["label"],
        angle_key=angle["key"],
        tone=angle.get("tone", "专业"),
        target_audience=angle.get("target_audience", "业主"),
        min_words=min_words,
        max_words=max_words,
        retrieved_context=context_text,
        photo_descriptions=photo_desc_text,
        photo_instruction=photo_instruction,
        template_section=template_instructions or "",
    )

    content = await call_llm_with_retry(
        create_llm(
            temperature=angle.get("temperature", settings.article_temperature),
            max_tokens=max_tokens,
            top_p=angle.get("top_p", settings.article_top_p),
        ),
        [{"role": "user", "content": prompt}],
        max_retries=2,
        clean=True,
    )

    # 字数校验：超限截断 → 不足自动扩写修复（一次）
    content = _truncate_content(content, max_words)
    if _count_words(content) < min_words:
        content = await _repair_article_words(
            content, min_words, max_words, max_tokens, angle
        )
        content = _truncate_content(content, max_words)

    # 提取图片配图标记（照片N 精确映射，旧格式回退顺序）
    image_placement = _extract_image_placements(content, photo_object_names or [])

    return {
        "title": title,
        "content": content,
        "word_count": _count_words(content),
        "angle": angle["key"],
        "account_type": account_type,
        "image_placement": image_placement,
    }


# ============================================================
# 后处理工具
# ============================================================

_IMAGE_MARKER_STRIP_RE = re.compile(r"\[IMAGE:[^\]]*\]", re.IGNORECASE)


def _count_words(content: str) -> int:
    """统计正文字数：剔除配图标记与所有空白（含换行）后计字符数。"""
    if not content:
        return 0
    stripped = _IMAGE_MARKER_STRIP_RE.sub("", content)
    return len("".join(stripped.split()))


def _truncate_content(content: str, max_chars: int) -> str:
    """字数超限时在最后一个完整句处截断到 max_chars 内，并丢弃被截断的残缺配图标记。"""
    if len(content) <= max_chars:
        return content

    keep = max_chars
    for punct in ("。\n", "。", "\n\n", "；"):
        idx = content.rfind(punct, 0, keep)
        if idx > keep * 0.6:
            return _drop_truncated_markers(content[: min(idx + len(punct), keep)])

    return _drop_truncated_markers(content[:keep])


def _drop_truncated_markers(text: str) -> str:
    """移除结尾处被截断、未闭合的 [IMAGE: ... 标记。"""
    cleaned = re.sub(r"\[IMAGE:[^\]]*$", "", text, flags=re.IGNORECASE)
    return cleaned.strip()


_REPAIR_WORDS_PROMPT = """你正在扩写一篇现有文章，使其达到目标字数。

当前正文（不含配图标记）为 {current_words} 字，目标为 {min_words}-{max_words} 字。

要求：
1. 保留原有结构与 [IMAGE: 照片N: 配图建议: xxx] 配图标记的位置与内容，不得增删配图标记；
2. 在现有内容基础上自然扩充（补充专业细节、真实案例、数据、工艺说明等），不要重复已有句子，不要改变主题；
3. 最终正文（不含配图标记）必须达到 {min_words} 字以上；
4. 只输出扩写后的完整文章正文，不要任何额外文字，不要使用 Markdown 符号。

当前正文：
{content}"""


async def _repair_article_words(
    content: str,
    min_words: int,
    max_words: int,
    max_tokens: int,
    angle: dict,
) -> str:
    """字数不足时调用 LLM 扩写修复；失败则原样返回。"""
    try:
        repair_prompt = _REPAIR_WORDS_PROMPT.format(
            current_words=_count_words(content),
            min_words=min_words,
            max_words=max_words,
            content=content,
        )
        repaired = await call_llm_with_retry(
            create_llm(
                temperature=0.5,
                max_tokens=max_tokens,
                top_p=angle.get("top_p", settings.article_top_p),
            ),
            [{"role": "user", "content": repair_prompt}],
            max_retries=1,
            clean=True,
        )
        if repaired and _count_words(repaired) > _count_words(content):
            return repaired
    except Exception as exc:
        logger.warning("article_words_repair_failed", error=str(exc))
    return content


_IMAGE_MARKER_RE = re.compile(
    r"\[IMAGE:\s*(?:照片\s*(\d+)\s*[:：])?\s*配图建议[:：]\s*(.+?)\]",
    re.IGNORECASE,
)


def _extract_image_placements(content: str, photo_names: list[str]) -> list[dict]:
    """从正文提取配图标记，返回结构化 placement 列表。

    新格式 [IMAGE: 照片N: 配图建议: xxx]：N 精确映射到对应照片；
    旧格式 [IMAGE: 配图建议: xxx]：按出现顺序回退分配（兼容）。
    """
    matches = _IMAGE_MARKER_RE.findall(content)
    placements: list[dict] = []

    fallback_idx = 0
    for i, (num, caption) in enumerate(matches):
        caption = caption.strip()
        if not caption:
            continue

        obj_name = None
        if num:
            n = int(num)
            if 1 <= n <= len(photo_names):
                obj_name = photo_names[n - 1]
        else:
            if photo_names:
                obj_name = photo_names[fallback_idx % len(photo_names)]
                fallback_idx += 1

        placements.append({
            "object_name": obj_name,
            "caption": caption,
            "position": f"marker_{i + 1}",
        })

    return placements


# ============================================================
# 主流水线（async generator，供 SSE 消费）
# ============================================================

async def generate_batch(
    topic: str,
    photo_descriptions: str = "",
    article_count: int = 5,
    knowledge_scope: str = "public",
    skip_count: int = 0,
    angle_keys: list[str] | None = None,
    photo_object_names: list[str] | None = None,
    template_instructions: str = "",
    min_words: int | None = None,
    max_words: int | None = None,
    account_type: str | None = None,
) -> list[dict]:
    """完整三步流水线：检索 → 规划 → 逐篇生成。返回文章列表。

    skip_count: 断点续传 — 跳过前 N 篇已生成的文章，从 N+1 开始继续。
    angle_keys: 指定角度 keys，None=使用全部默认角度。
    photo_object_names: 照片 object names，用于提取配图标记。
    account_type: 目标账号类型（user/designer/dealer），用于约束角度人群。"""
    articles: list[dict] = []

    # 筛选角度
    if angle_keys:
        angles = [a for a in DEFAULT_ANGLES if a["key"] in angle_keys]
        if not angles:
            angles = DEFAULT_ANGLES[:article_count]
    else:
        angles = DEFAULT_ANGLES[:article_count]
    retrieved = await retrieve_knowledge(angles, scope=knowledge_scope)

    # 汇总知识摘要供角度规划使用
    summary_parts = []
    for angle in angles:
        chunks = retrieved.get(angle["key"], [])
        if chunks:
            summary_parts.append(f"{angle['label']}: {clean_response(chunks[0].content[:200])}...")
    knowledge_summary = "\n".join(summary_parts)

    # Step 2: 规划角度（仅当用户未指定角度时调用 LLM）
    if not angle_keys:
        try:
            angles = await plan_angles(
                topic=topic,
                photo_descriptions=photo_descriptions,
                knowledge_summary=knowledge_summary,
                count=article_count,
                account_type=account_type,
            )
        except Exception:
            angles = DEFAULT_ANGLES[:article_count]
        # 规划后的角度可能带新的 retrieval_query，需为最终角度补检索，
        # 否则逐篇生成时取不到知识上下文。
        retrieved = await retrieve_knowledge(angles, scope=knowledge_scope)

    # Step 3: 逐篇生成（支持断点续传）
    for i, angle in enumerate(angles):
        if i < skip_count:
            logger.info("article_skip", index=i + 1, angle=angle["key"], reason="already_generated")
            continue

        logger.info("article_generating", index=i + 1, total=len(angles), angle=angle["key"])
        try:
            ctx = retrieved.get(angle["key"], [])
            article = await generate_single_article(
                topic=topic,
                angle=angle,
                retrieved_context=ctx,
                photo_descriptions=photo_descriptions,
                photo_object_names=photo_object_names or [],
                template_instructions=template_instructions,
                min_words=min_words,
                max_words=max_words,
                account_type=account_type,
            )
            articles.append(article)
        except Exception as exc:
            logger.error("article_generate_failed", angle=angle["key"], error=str(exc))
            articles.append({
                "title": f"{topic}——{angle['label']}",
                "content": f"（生成失败：{exc}）",
                "word_count": 0,
                "angle": angle["key"],
                "account_type": account_type,
                "image_placement": [],
            })

        # 间隔，防 LLM 限流 + 给 GC 喘息
        if i < len(angles) - 1:
            await asyncio.sleep(settings.article_generate_interval)

    logger.info("article_pipeline_done", topic=topic, generated=len(articles))
    return articles


# ============================================================
# 质量评估
# ============================================================

_EVALUATE_SIMILARITY_PROMPT = """判断以下两篇文章的标题是否存在内容雷同（表达不同但核心主题相同也算雷同）。
标题 A: {title_a}
标题 B: {title_b}
只回答 "yes"（雷同）或 "no"（不雷同），不要其他内容。"""


async def evaluate_articles(
    articles: list[dict],
    min_words: int | None = None,
    max_words: int | None = None,
) -> dict:
    """质量评估 — 验证字数、内容完整度、标题差异化。

    返回:
        {"passed": bool, "issues": list[str], "details": list[dict]}
    """
    issues: list[str] = []
    details: list[dict] = []

    min_words = min_words or settings.article_min_words
    max_words = max_words or settings.article_max_words

    # 1. 字数检查
    for i, art in enumerate(articles):
        wc = art.get("word_count", 0)
        detail = {
            "index": i + 1,
            "title": art.get("title", ""),
            "angle": art.get("angle", ""),
            "word_count": wc,
            "word_count_ok": min_words <= wc <= max_words,
            "content_empty": len(art.get("content", "").strip()) < 10,
        }
        if wc < min_words:
            issues.append(f"第 {i + 1} 篇「{art.get('title', '')}」字数不足 ({wc}/{min_words})")
        elif wc > max_words:
            issues.append(f"第 {i + 1} 篇「{art.get('title', '')}」字数超标 ({wc}/{max_words})")
        if detail["content_empty"]:
            issues.append(f"第 {i + 1} 篇「{art.get('title', '')}」内容为空")
        details.append(detail)

    # 2. 标题差异化检查 — 用 LLM 比对每对标题
    title_check_results: list[dict] = []
    if len(articles) >= 2:
        llm = create_llm(temperature=0.2, max_tokens=10, top_p=0.85)
        for i in range(len(articles)):
            for j in range(i + 1, len(articles)):
                title_a = articles[i].get("title", "")
                title_b = articles[j].get("title", "")
                if not title_a or not title_b:
                    continue
                try:
                    raw = await call_llm_with_retry(
                        llm,
                        [{"role": "user", "content": _EVALUATE_SIMILARITY_PROMPT.format(
                            title_a=title_a, title_b=title_b
                        )}],
                        max_retries=1,
                    )
                    is_dup = raw.strip().lower().startswith("yes")
                    title_check_results.append({
                        "pair": f"{i + 1}↔{j + 1}",
                        "title_a": title_a,
                        "title_b": title_b,
                        "duplicate": is_dup,
                    })
                    if is_dup:
                        issues.append(f"第 {i + 1} 篇和第 {j + 1} 篇标题雷同：「{title_a}」≈「{title_b}」")
                except Exception as exc:
                    logger.warning("article_title_eval_failed", pair=f"{i + 1}↔{j + 1}", error=str(exc))

    # 3. 生成评估报告
    passed = len(issues) == 0
    logger.info(
        "article_evaluate_done",
        passed=passed,
        issue_count=len(issues),
        article_count=len(articles),
    )

    return {
        "passed": passed,
        "issues": issues,
        "details": details,
        "title_checks": title_check_results,
    }
