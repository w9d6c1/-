"""文档文本清洗引擎 — 规则清洗层

对 PDF/DOCX/外部工具转换后的 Markdown 文本做确定性清洗：

1. 页标记清除（=== Page N === / [PN] / Page N of M）
2. 占位行清除（独立的"表格""图片"行）
3. 孤儿碎片合并（1-2 字 CJK 碎片并入上行，修复表格单元格断行）
4. CJK 空格规范化（去除中文之间/中文与字母数字之间的多余空格）
5. 空行压缩

语义级重建（复杂表格结构、多字碎片）由 LLM 增强层处理，见
text_cleaner_llm.py。本层所有操作保证内容字符不丢失、可重复执行（幂等）。
"""

import re
from dataclasses import dataclass

_PAGE_MARKER_PATTERNS = (
    re.compile(r"^===\s*Page\s+\d+\s*===\s*$"),
    re.compile(r"^---\s*Page\s+\d+\s*---\s*$"),
    re.compile(r"^\[P\d+\]\s*$"),
    re.compile(r"^Page\s+\d+\s+of\s+\d+\s*$"),
    re.compile(r"^第\s*\d+\s*页\s*$"),
)

# 内联形式（兼容已被压缩为单行的存量 plain_text）
_INLINE_PAGE_MARKER_RE = re.compile(
    r"===\s*Page\s+\d+\s*===|---\s*Page\s+\d+\s*---|\[P\d+\]|Page\s+\d+\s+of\s+\d+"
)

_PLACEHOLDER_WORDS = frozenset({"表格", "图片"})

# 常见扫描件水印/广告噪声行（整行丢弃，如 "福睿金融-外汇黄金平台测评 http://..."）。
# 这类水印以文字层或 OCR 文本形式逐页出现，会污染知识库内容。
_NOISE_LINE_RES = (
    re.compile(r"福睿金融"),
    re.compile(r"外汇黄金平台测评"),
    re.compile(r"forexcny", re.IGNORECASE),
)

_BULLET_MARKS = frozenset({"-", "•", "·", "–"})

# 只有符号没有文字的"标题"（PDF 解析误判，如 "### >"、孤立 "##"）
_SYMBOL_ONLY_HEADING_RE = re.compile(r"^#{1,6}[\s>\-–•·]*$")

# BOM、零宽字符等不可见字符
_INVISIBLE_CHARS_RE = re.compile(r"[\ufeff\u200b\u200c\u200d\u2060\u00ad]")

_MULTI_SPACE_RE = re.compile(r"[^\S\n]{2,}")


@dataclass
class CleanReport:
    original_chars: int = 0
    cleaned_chars: int = 0
    removed_page_markers: int = 0
    removed_placeholders: int = 0
    removed_noise_lines: int = 0
    merged_fragments: int = 0
    collapsed_blank_lines: int = 0
    llm_enhanced: bool = False


@dataclass
class CleanResult:
    text: str
    report: CleanReport


def _is_cjk(ch: str) -> bool:
    return "\u4e00" <= ch <= "\u9fff"


def _is_ascii_alnum(ch: str) -> bool:
    return ch.isascii() and ch.isalnum()


def strip_page_markers(text: str) -> tuple[str, int]:
    """移除页标记（整行优先，兼容内联），返回 (处理后文本, 移除数量)"""
    if not text:
        return "", 0
    kept: list[str] = []
    removed = 0
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped and any(p.match(stripped) for p in _PAGE_MARKER_PATTERNS):
            removed += 1
            continue
        kept.append(line)
    joined = "\n".join(kept)
    joined, inline_count = _INLINE_PAGE_MARKER_RE.subn("", joined)
    return joined, removed + inline_count


def strip_placeholders(text: str) -> tuple[str, int]:
    """移除独立的转换占位行（如"表格"）与无文本的符号标题，保留普通句子"""
    if not text:
        return "", 0
    kept: list[str] = []
    removed = 0
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped in _PLACEHOLDER_WORDS or _SYMBOL_ONLY_HEADING_RE.match(stripped):
            removed += 1
            continue
        kept.append(line)
    return "\n".join(kept), removed


def strip_noise_lines(text: str) -> tuple[str, int]:
    """移除整行水印/广告噪声（逐行命中即丢，保留其余内容）"""
    if not text:
        return "", 0
    kept: list[str] = []
    removed = 0
    for line in text.split("\n"):
        if line.strip() and any(p.search(line) for p in _NOISE_LINE_RES):
            removed += 1
            continue
        kept.append(line)
    return "\n".join(kept), removed


def merge_orphan_fragments(text: str) -> tuple[str, int]:
    """合并 1-2 字的 CJK 孤儿碎片行到上一行。

    PDF 表格列宽截断常把词语拆成碎片行（如"物理隔/离"）。仅当碎片
    全为 CJK、无标点，且上行以 CJK/字母数字结尾（非标点）、不是标题
    或表格行时才合并，保证保守安全。
    """
    if not text:
        return "", 0
    result: list[str] = []
    merged = 0
    for line in text.split("\n"):
        stripped = line.strip()
        if result and stripped and not stripped.startswith("#") and stripped not in _BULLET_MARKS:
            prev = result[-1].rstrip()
            if prev in _BULLET_MARKS:
                result[-1] = prev + " " + stripped
                merged += 1
                continue
        if (
            stripped
            and len(stripped) <= 2
            and all(_is_cjk(ch) for ch in stripped)
            and result
        ):
            prev = result[-1].rstrip()
            if (
                prev
                and not prev.startswith("#")
                and not prev.startswith("|")
                and (_is_cjk(prev[-1]) or _is_ascii_alnum(prev[-1]))
            ):
                result[-1] = prev + stripped
                merged += 1
                continue
        result.append(line)
    return "\n".join(result), merged


def remove_cjk_spaces(text: str) -> str:
    """去除 CJK 相关多余空格。

    移除规则：空格一侧为 CJK，另一侧为 CJK/字母/数字时删除该空格；
    运算符（+ / < 等）与纯英文短语中的空格保留。连续水平空白先压缩为单空格。
    """
    if not text:
        return ""
    text = _MULTI_SPACE_RE.sub(" ", text)
    chars = list(text)
    out: list[str] = []
    last = len(chars) - 1
    for i, ch in enumerate(chars):
        if ch == " " and 0 < i < last:
            left, right = chars[i - 1], chars[i + 1]
            left_near = _is_cjk(left) or _is_ascii_alnum(left)
            right_near = _is_cjk(right) or _is_ascii_alnum(right)
            if (_is_cjk(left) and right_near) or (_is_cjk(right) and left_near):
                continue
        out.append(ch)
    return "".join(out)


def collapse_blank_lines(text: str) -> tuple[str, int]:
    """压缩连续空行为单个空行，并去除首尾空行"""
    if not text:
        return "", 0
    result: list[str] = []
    collapsed = 0
    blank_run = 0
    for line in text.split("\n"):
        if not line.strip():
            blank_run += 1
            if blank_run == 1 and result:
                result.append("")
            elif blank_run > 1:
                collapsed += 1
        else:
            blank_run = 0
            result.append(line)
    while result and not result[-1].strip():
        result.pop()
        collapsed += 1
    return "\n".join(result), collapsed


def clean_document_text(text: str) -> CleanResult:
    """完整规则清洗管道，返回清洗文本与统计报告"""
    original_chars = len(text)
    text = _INVISIBLE_CHARS_RE.sub("", text)
    text, markers = strip_page_markers(text)
    text, placeholders = strip_placeholders(text)
    text, noise = strip_noise_lines(text)
    text, merged = merge_orphan_fragments(text)
    text = remove_cjk_spaces(text)
    text, collapsed = collapse_blank_lines(text)
    report = CleanReport(
        original_chars=original_chars,
        cleaned_chars=len(text),
        removed_page_markers=markers,
        removed_placeholders=placeholders,
        removed_noise_lines=noise,
        merged_fragments=merged,
        collapsed_blank_lines=collapsed,
    )
    return CleanResult(text=text, report=report)
