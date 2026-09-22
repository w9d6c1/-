"""文档文本清洗 — LLM 增强层

对规则清洗后的文本做语义级优化：合并多字碎片词、重建丢失的表格结构。
安全护栏：

1. 长度偏差护栏 — 单段 LLM 输出与输入长度偏差超过 LENGTH_DEVIATION_LIMIT
   时判定为幻觉/截断，丢弃该段结果回退原文。
2. 失败回退 — LLM 未配置、调用异常或输出为空时，整体回退规则清洗结果。
"""

import re
from dataclasses import replace

from langchain_core.language_models import BaseChatModel

from app.agents.llm import create_llm
from app.core.config import settings
from app.core.logging import logger
from app.services.text_cleaner import CleanReport, CleanResult, clean_document_text

MAX_SEGMENT_CHARS = 2000
LENGTH_DEVIATION_LIMIT = 0.4

_HEADING_SPLIT_RE = re.compile(r"(?m)^(?=#)")

_CLEAN_PROMPT = """你是文档清洗助手。以下文本由 PDF/Word 转换而来，
存在表格结构丢失、词语被拆行等格式问题。请清洗优化：

1. 合并被错误拆散的碎片词语和句子（例如"内部问/答智能/体"应合并为"内部问答智能体"）
2. 将丢失结构的表格内容尽量重建为 Markdown 表格；无法确定列结构时合并为通顺的句子
3. 严格保留全部事实内容，禁止新增、删除或改写任何信息
4. 保留标题层级（# 标记）和段落结构

只输出清洗后的文本，不要输出任何解释或前后缀。

待清洗文本：
{text}"""


def split_into_segments(text: str, max_chars: int = MAX_SEGMENT_CHARS) -> list[str]:
    """按标题边界分段；单段超长时按行切分"""
    if not text or not text.strip():
        return []
    parts = _HEADING_SPLIT_RE.split(text)
    segments: list[str] = []
    for part in parts:
        part = part.strip("\n")
        if not part.strip():
            continue
        if len(part) <= max_chars:
            segments.append(part)
            continue
        current = ""
        for line in part.split("\n"):
            if current and len(current) + len(line) + 1 > max_chars:
                segments.append(current)
                current = line
            else:
                current = f"{current}\n{line}" if current else line
        if current:
            segments.append(current)
    return segments


async def _enhance_segment(llm: BaseChatModel, segment: str) -> str:
    """单段 LLM 清洗，带长度偏差护栏"""
    response = await llm.ainvoke(_CLEAN_PROMPT.format(text=segment))
    result = (getattr(response, "content", "") or "").strip()
    if not result:
        return segment
    deviation = abs(len(result) - len(segment)) / max(len(segment), 1)
    if deviation > LENGTH_DEVIATION_LIMIT:
        logger.warning(
            "llm_clean_length_guard",
            segment_chars=len(segment),
            output_chars=len(result),
            deviation=round(deviation, 2),
        )
        return segment
    return result


async def llm_enhance_clean(text: str, use_llm: bool = True) -> CleanResult:
    """规则清洗 + 可选 LLM 增强；任何 LLM 异常自动回退规则结果"""
    base = clean_document_text(text)
    if not use_llm or not settings.llm_api_key or not base.text.strip():
        return base
    try:
        llm = create_llm(temperature=0.0, max_tokens=8192)
        segments = split_into_segments(base.text)
        enhanced_segments: list[str] = []
        for seg in segments:
            enhanced_segments.append(await _enhance_segment(llm, seg))
        enhanced_text = "\n\n".join(enhanced_segments)
        if enhanced_text == base.text:
            return base
        report: CleanReport = replace(base.report, llm_enhanced=True)
        return CleanResult(text=enhanced_text, report=report)
    except Exception:
        logger.warning("llm_clean_fallback", exc_info=True)
        return base
