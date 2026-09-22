"""公开文件服务 — 采集文章图片 / 创作文章配图的只读代理。

- article-images/：采集文章图片（公众号/知乎等），内部问答与客服端共用。
- article-photos/：批量创作文章的配图，发布到各平台时供 Chrome 扩展/平台直接拉取。
安全约束：仅允许上述前缀 + 扩展名白名单，路径穿越一律拒绝。
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.core.config import settings
from app.core.minio_client import get_minio_client

router = APIRouter(tags=["public-files"])

_ALLOWED_PREFIXES = ("article-images/", "article-photos/", "photo-library/")
_ALLOWED_EXT_CT = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}
_CACHE_HEADERS = {"Cache-Control": "public, max-age=604800, immutable"}


def _validate_object_name(object_name: str) -> str:
    name = object_name.strip().lstrip("/")
    if "\\" in name or ".." in name or "//" in name:
        raise HTTPException(400, "非法路径")
    if not name.startswith(_ALLOWED_PREFIXES):
        raise HTTPException(403, "禁止访问该资源")
    lower = name.lower()
    if not any(lower.endswith(ext) for ext in _ALLOWED_EXT_CT):
        raise HTTPException(403, "不支持的文件类型")
    return name


def _content_type(object_name: str) -> str:
    lower = object_name.lower()
    for ext, ct in _ALLOWED_EXT_CT.items():
        if lower.endswith(ext):
            return ct
    return "application/octet-stream"


@router.get("/images/{object_name:path}")
async def get_public_image(object_name: str):
    """代理 MinIO 中的采集文章图片/创作配图，供对话界面与平台发布直接展示。"""
    name = _validate_object_name(object_name)
    client = get_minio_client()
    try:
        response = client.get_object(settings.minio_bucket, name)
        data = response.read()
        response.close()
        response.release_conn()
    except Exception:
        raise HTTPException(404, "图片不存在")
    return Response(content=data, media_type=_content_type(name), headers=_CACHE_HEADERS)
