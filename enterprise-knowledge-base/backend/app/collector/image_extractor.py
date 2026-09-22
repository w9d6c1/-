"""文章正文图片提取 — <img> 解析 → 防盗链下载 → 内容去重 → MinIO 转存。

与 cleaner.clean_html_with_images 共用 resolve_img_src / parse_images，
保证占位符编号与图片列表顺序严格一致。
"""

import hashlib
import io
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx

from app.core.config import settings
from app.core.logging import logger
from app.core.minio_client import ensure_bucket, get_minio_client

MAX_IMAGES_PER_ARTICLE = 20
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MIN_IMAGE_BYTES = 512

IMG_PREFIX = "article-images"

_CONTENT_TYPE_EXT = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/gif": "gif",
    "image/webp": "webp",
    "image/bmp": "bmp",
}

_URL_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}

_REFERER_BY_HOST = {
    "mmbiz.qpic.cn": "https://mp.weixin.qq.com/",
    "mmbiz.qlogo.cn": "https://mp.weixin.qq.com/",
    "pic1.zhimg.com": "https://www.zhihu.com/",
    "pic2.zhimg.com": "https://www.zhihu.com/",
    "pic3.zhimg.com": "https://www.zhihu.com/",
    "pic4.zhimg.com": "https://www.zhihu.com/",
    "picx.zhimg.com": "https://www.zhihu.com/",
}

# 图片占位符（cleaner 插入、ingestion 关联切片后剥离）
IMG_PLACEHOLDER_RE = re.compile(r"\[\[IMG:(\d+)\]\]")


@dataclass
class ParsedImage:
    """HTML 中解析出的单张图片（下载前）。"""

    url: str
    width: int | None = None
    height: int | None = None


@dataclass
class ExtractedImage:
    """下载并转存成功的图片。"""

    seq: int
    object_name: str
    original_url: str
    content_hash: str
    width: int | None = None
    height: int | None = None


def resolve_img_src(attrs: list | dict) -> str | None:
    """按平台优先级解析 <img> 的真实图片地址；无效返回 None。

    微信正文图片在 data-src，知乎在 data-actualsrc/data-original，
    常规页面在 src。data: URI 与空值一律跳过。
    """
    if isinstance(attrs, dict):
        get = attrs.get
    else:
        mapping = dict(attrs)
        get = mapping.get
    for key in ("data-src", "data-actualsrc", "data-original", "src"):
        url = (get(key) or "").strip()
        if url and url.startswith("http"):
            return url
    return None


def _parse_int(value: str | None) -> int | None:
    if not value:
        return None
    m = re.match(r"^\s*(\d+)", str(value))
    return int(m.group(1)) if m else None


class _ImgParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.images: list[ParsedImage] = []

    def _handle_img(self, attrs: list) -> None:
        url = resolve_img_src(attrs)
        if not url:
            return
        mapping = dict(attrs)
        width = _parse_int(mapping.get("width")) or _parse_int(mapping.get("data-w"))
        height = _parse_int(mapping.get("height"))
        self.images.append(ParsedImage(url=url, width=width, height=height))

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "img":
            self._handle_img(attrs)

    def handle_startendtag(self, tag: str, attrs: list) -> None:
        if tag == "img":
            self._handle_img(attrs)


def parse_images(html: str) -> list[ParsedImage]:
    """按正文出现顺序解析全部有效图片；解析失败返回空列表。"""
    if not html or "<img" not in html.lower():
        return []
    try:
        parser = _ImgParser()
        parser.feed(html)
        parser.close()
    except Exception:
        logger.warning("image_parse_failed", exc_info=True)
        return []
    return parser.images[:MAX_IMAGES_PER_ARTICLE]


def _referer_for(url: str, article_url: str) -> str | None:
    host = urlparse(url).hostname or ""
    if host in _REFERER_BY_HOST:
        return _REFERER_BY_HOST[host]
    return article_url or None


def _guess_ext(url: str, content_type: str) -> str:
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct in _CONTENT_TYPE_EXT:
        return _CONTENT_TYPE_EXT[ct]
    path = urlparse(url).path.lower()
    for ext in _URL_EXT:
        if path.endswith(ext):
            return "jpg" if ext == ".jpeg" else ext.lstrip(".")
    return "jpg"


def _safe_external_id(external_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", external_id or "")[:64].strip("_")
    return safe or "unknown"


def build_object_name(platform: str, external_id: str, content_hash: str, ext: str) -> str:
    return f"{IMG_PREFIX}/{platform}/{_safe_external_id(external_id)}/{content_hash}.{ext}"


def image_url_path(object_name: str) -> str:
    """图片对外服务路径（公开只读端点）。"""
    return f"/api/public/images/{object_name}"


async def _download(client: httpx.AsyncClient, url: str, referer: str | None) -> bytes | None:
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    if referer:
        headers["Referer"] = referer
    try:
        resp = await client.get(url, headers=headers, follow_redirects=True)
        resp.raise_for_status()
        data = resp.content
    except Exception:
        logger.debug("image_download_failed", url=url, exc_info=True)
        return None
    if len(data) < MIN_IMAGE_BYTES or len(data) > MAX_IMAGE_BYTES:
        return None
    return data


async def extract_and_store_images(
    html: str,
    platform: str,
    external_id: str,
    article_url: str = "",
) -> list[ExtractedImage]:
    """解析、下载并转存文章图片；单张失败不影响其余，整体失败返回空列表。"""
    parsed = parse_images(html)
    if not parsed:
        return []

    results: list[ExtractedImage] = []
    seen_urls: set[str] = set()
    client = httpx.AsyncClient(timeout=settings.collector_request_timeout)
    try:
        for idx, img in enumerate(parsed, start=1):
            if img.url in seen_urls:
                continue
            seen_urls.add(img.url)

            data = await _download(client, img.url, _referer_for(img.url, article_url))
            if data is None:
                logger.info("image_skipped", seq=idx, url=img.url[:200])
                continue

            c_hash = hashlib.sha256(data).hexdigest()
            ext = _guess_ext(img.url, "")
            object_name = build_object_name(platform, external_id, c_hash, ext)

            try:
                minio = get_minio_client()
                bucket = settings.minio_bucket
                ensure_bucket(bucket)
                try:
                    minio.stat_object(bucket, object_name)
                except Exception:
                    minio.put_object(
                        bucket_name=bucket,
                        object_name=object_name,
                        data=io.BytesIO(data),
                        length=len(data),
                        content_type=f"image/{'jpeg' if ext == 'jpg' else ext}",
                    )
            except Exception:
                logger.warning("image_upload_failed", object_name=object_name, exc_info=True)
                continue

            results.append(
                ExtractedImage(
                    seq=idx,
                    object_name=object_name,
                    original_url=img.url,
                    content_hash=c_hash,
                    width=img.width,
                    height=img.height,
                )
            )
    finally:
        await client.aclose()

    logger.info(
        "images_extracted",
        platform=platform,
        external_id=(external_id or "")[:100],
        parsed=len(parsed),
        stored=len(results),
    )
    return results
