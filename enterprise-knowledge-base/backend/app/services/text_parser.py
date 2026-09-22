"""文本解析服务 — 支持 Markdown/TXT/PDF/Word 解析

PDF 解析基于 PyMuPDF 字号检测自动识别标题层级，
输出 Markdown 风格的 `#` 标题前缀供 semantic chunker 使用。
"""

import io
import re
from dataclasses import dataclass, field


@dataclass
class PageHeading:
    level: int
    title: str
    page: int


@dataclass
class TextParseResult:
    plain_text: str
    word_count: int  # 字符数 (保持与旧字段语义兼容)
    headings: list[PageHeading] = field(default_factory=list)
    page_count: int = 0


def parse_text(content: str, file_type: str) -> TextParseResult:
    if file_type == "md":
        plain_text = re.sub(r"\*\*(.+?)\*\*", r"\1", content)
        plain_text = re.sub(r"\*(.+?)\*", r"\1", plain_text)
        plain_text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", plain_text)
        plain_text = re.sub(r"`{1,3}.*?`{1,3}", "", plain_text)
    else:
        plain_text = content

    plain_text = re.sub(r"\s+", " ", plain_text).strip()
    return TextParseResult(plain_text=plain_text, word_count=len(plain_text))


def _extract_page_text(page) -> tuple[str, list[float]]:
    """单页内嵌文字层提取：返回 (页文本, 字号集合)。"""
    blocks = page.get_text("dict")["blocks"]
    page_lines: list[str] = []
    font_sizes: list[float] = []
    for block in blocks:
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            line_text_parts: list[str] = []
            for span in line.get("spans", []):
                size = span.get("size", 10)
                text = span.get("text", "").strip()
                if text:
                    line_text_parts.append(text)
                    font_sizes.append(size)
            if line_text_parts:
                page_lines.append("".join(line_text_parts))
    return "\n".join(page_lines), font_sizes


def _ocr_page(page, dpi: int = 200) -> str:
    """将 PDF 页栅格化后 OCR。避免顶层导入 numpy/rapidocr，仅 OCR 页才加载。"""
    import fitz

    import numpy as np

    from app.services.ocr import ocr_image

    zoom = max(1.0, dpi / 72.0)
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    if img.shape[2] == 4:
        img = img[:, :, :3]
    text = ocr_image(img)
    return text.strip()


def parse_pdf_bytes(file_bytes: bytes, enable_ocr: bool | None = None) -> TextParseResult:
    """PDF 结构化解析 — 基于字号检测标题，页级文本提取。

    当 enable_ocr=True（或 settings.pdf_ocr_enabled）时，内嵌文字量低于阈值
    （settings.ocr_min_chars_per_page）的页自动栅格化 OCR 兜底，适用于扫描版。
    OCR 页无字号信息，不参与标题层级检测。
    """
    if enable_ocr is None:
        try:
            from app.core.config import settings

            enable_ocr = settings.pdf_ocr_enabled
        except Exception:
            enable_ocr = False
    if enable_ocr:
        try:
            from app.core.config import settings

            ocr_min_chars = settings.ocr_min_chars_per_page
            ocr_dpi = settings.ocr_dpi
        except Exception:
            ocr_min_chars, ocr_dpi = 30, 200

    import fitz

    page_texts: list[str] = []
    all_headings: list[PageHeading] = []
    font_sizes: list[float] = []
    ocr_page_count = 0

    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        for page_num, page in enumerate(doc, start=1):
            page_text, page_font_sizes = _extract_page_text(page)
            if enable_ocr and len(page_text.strip()) < ocr_min_chars:
                ocr_text = _ocr_page(page, dpi=ocr_dpi)
                if ocr_text:
                    page_text = ocr_text
                    ocr_page_count += 1
            font_sizes.extend(page_font_sizes)
            page_texts.append(page_text)

        doc.close()

        heading_sizes = _detect_heading_sizes(font_sizes)
        full_text = "\n".join(page_texts)

        if heading_sizes and ocr_page_count == 0:
            heading_doc = fitz.open(stream=file_bytes, filetype="pdf")
            for page_num, page in enumerate(heading_doc, start=1):
                blocks = page.get_text("dict")["blocks"]
                for block in blocks:
                    if block.get("type") != 0:
                        continue
                    for line in block.get("lines", []):
                        sizes_in_line = {
                            s.get("size", 10) for s in line.get("spans", [])
                        }
                        for lvl, size_threshold in heading_sizes.items():
                            if any(s >= size_threshold for s in sizes_in_line):
                                title = "".join(
                                    s.get("text", "") for s in line.get("spans", [])
                                ).strip()
                                if title and len(title) < 200:
                                    all_headings.append(
                                        PageHeading(level=lvl, title=title, page=page_num)
                                    )
                                break
            heading_doc.close()

        plain_text = _apply_headings_to_text(full_text, all_headings)

    except Exception:
        plain_text = "[PDF parsing unavailable]"
        all_headings = []

    return TextParseResult(
        plain_text=plain_text,
        word_count=len(plain_text),
        headings=all_headings,
        page_count=len(page_texts) if "page_texts" in dir() else 0,
    )


def parse_docx_bytes(file_bytes: bytes) -> TextParseResult:
    """DOCX 解析 — 段落级提取，保留样式信息"""
    try:
        import docx as docx_lib

        document = docx_lib.Document(io.BytesIO(file_bytes))
        all_headings: list[PageHeading] = []
        text_parts: list[str] = []
        page_num = 1

        for para in document.paragraphs:
            text = para.text.strip()
            if not text:
                continue

            if para.style.name and para.style.name.startswith("Heading"):
                level_str = para.style.name.replace("Heading", "").strip()
                try:
                    level = int(level_str)
                except ValueError:
                    level = 1
                all_headings.append(PageHeading(level=min(level, 3), title=text, page=page_num))
                prefix = "#" * level
                text_parts.append(f"{prefix} {text}")
            else:
                text_parts.append(text)

        plain_text = "\n".join(text_parts)
    except Exception:
        plain_text = "[DOCX parsing unavailable]"
        all_headings = []

    return TextParseResult(
        plain_text=plain_text,
        word_count=len(plain_text),
        headings=all_headings,
        page_count=page_num,
    )


def _detect_heading_sizes(font_sizes: list[float]) -> dict[int, float]:
    """根据字号分布自动识别标题层级阈值"""
    if not font_sizes:
        return {}

    from collections import Counter

    counter = Counter(round(s, 1) for s in font_sizes)
    sorted_sizes = sorted(counter.keys(), reverse=True)

    body_size = max(counter, key=counter.get) if counter else 10
    large_sizes = [s for s in sorted_sizes if s > body_size + 1]

    result: dict[int, float] = {}
    if not large_sizes:
        return result

    if len(large_sizes) >= 1:
        result[1] = large_sizes[0]
    if len(large_sizes) >= 2:
        result[2] = large_sizes[1]
    if len(large_sizes) >= 3:
        result[3] = large_sizes[2]

    return result


def _apply_headings_to_text(text: str, headings: list[PageHeading]) -> str:
    """将检测到的标题以 Markdown 前缀形式插入文本"""
    if not headings:
        return text

    lines = text.split("\n")
    heading_set = {(h.title, h.page) for h in headings}

    result: list[str] = []
    current_page = 0
    for line in lines:
        stripped = line.strip()
        for h in headings:
            if h.page != current_page:
                result.append(f"[P{h.page}]")
                current_page = h.page
            if stripped == h.title:
                prefix = "#" * h.level
                line = f"{prefix} {stripped}"
                break

        result.append(line)

    return "\n".join(result)
