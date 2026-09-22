"""HTML 清洗 — 提取正文纯文本（stdlib HTMLParser，无第三方依赖）。"""

import re
from html.parser import HTMLParser

from app.collector.image_extractor import IMG_PLACEHOLDER_RE, resolve_img_src

_SKIP_TAGS = {
    "script", "style", "noscript", "nav", "header", "footer", "aside",
    "iframe", "svg", "form", "button", "input", "select", "textarea",
}
_BLOCK_TAGS = {
    "p", "div", "br", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6",
    "tr", "table", "section", "article", "blockquote", "pre", "hr", "dd", "dt", "figure",
}
_WS_RE = re.compile(r"[^\S\n]+")


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.chunks: list[str] = []
        self.title_parts: list[str] = []
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if tag == "title":
            self._in_title = True
            return
        if tag in _BLOCK_TAGS:
            self.chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            if self._skip_depth > 0:
                self._skip_depth -= 1
            return
        if tag == "title":
            self._in_title = False
            return
        if tag in _BLOCK_TAGS:
            self.chunks.append("\n")

    def handle_startendtag(self, tag: str, attrs: list) -> None:
        if tag in _BLOCK_TAGS:
            self.chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth > 0:
            return
        if self._in_title:
            self.title_parts.append(data)
            return
        if data.strip():
            self.chunks.append(data)


class _TextWithImagesExtractor(_TextExtractor):
    """在纯文本提取基础上，为可解析出有效地址的 <img> 顺序插入 [[IMG:n]] 占位符。

    占位符编号规则必须与 image_extractor.parse_images 完全一致：
    仅统计 resolve_img_src 能解析出 http(s) 地址的 <img>，按出现顺序编号。
    """

    def __init__(self) -> None:
        super().__init__()
        self.image_count = 0

    def _handle_img(self, attrs: list) -> None:
        if self._skip_depth > 0:
            return
        if resolve_img_src(attrs):
            self.image_count += 1
            self.chunks.append(f"\n[[IMG:{self.image_count}]]\n")

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "img":
            self._handle_img(attrs)
            return
        super().handle_starttag(tag, attrs)

    def handle_startendtag(self, tag: str, attrs: list) -> None:
        if tag == "img":
            self._handle_img(attrs)
            return
        super().handle_startendtag(tag, attrs)


def _run_parser(html: str) -> _TextExtractor:
    extractor = _TextExtractor()
    extractor.feed(html)
    extractor.close()
    return extractor


def _normalize(text: str) -> str:
    lines = [_WS_RE.sub(" ", line).strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line).strip()


def clean_html(html: str) -> str:
    """提取 HTML 正文纯文本：去脚本/样式/导航，块级换行，压缩空白。"""
    if not html or not html.strip():
        return ""
    try:
        extractor = _run_parser(html)
        text = "".join(extractor.chunks)
    except Exception:
        text = re.sub(r"<[^>]+>", " ", html)
    return _normalize(text)


def clean_html_with_images(html: str) -> tuple[str, int]:
    """提取正文纯文本并保留图片位置占位符。

    返回 (含 [[IMG:n]] 占位符的文本, 图片数量)。解析失败时回退为无占位符纯文本。
    """
    if not html or not html.strip():
        return "", 0
    try:
        extractor = _TextWithImagesExtractor()
        extractor.feed(html)
        extractor.close()
        text = "".join(extractor.chunks)
        return _normalize(text), extractor.image_count
    except Exception:
        return clean_html(html), 0


def strip_image_placeholders(text: str) -> str:
    """剥离 [[IMG:n]] 占位符并重新归一化空白，得到与 clean_html 一致的纯文本。"""
    if not text or "[[IMG:" not in text:
        return text
    return _normalize(IMG_PLACEHOLDER_RE.sub("", text))


def extract_title(html: str) -> str:
    """提取 <title> 标签内容（若有），否则返回空串。"""
    if not html:
        return ""
    try:
        extractor = _run_parser(html)
    except Exception:
        return ""
    return re.sub(r"\s+", " ", "".join(extractor.title_parts)).strip()
