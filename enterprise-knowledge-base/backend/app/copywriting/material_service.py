"""素材导入 — 照片/文字/视频上传 + 链接抓取 → AI 可读的素材描述

- 照片: MinIO 存储 + 豆包多模态读画面 → 文字描述
- 文字: 直接读取内容
- 视频: 仅存作参考（暂不读取画面）
- 链接: 复用 imitate.fetch_article_content 抓取正文
"""

import base64
import re
import uuid
from datetime import datetime

from app.articles.vision import get_vision_provider
from app.core.logging import logger
from app.core.minio_client import upload_file

_BUCKET = "knowledge-docs"
_PREFIX = "copywriting-materials/"

# 允许的扩展名（按类型）
_PHOTO_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif")
_TEXT_EXTS = (".txt", ".md", ".markdown", ".csv")
_VIDEO_EXTS = (".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".m4v")

_PHOTO_PROMPT = """请用中文详细描述这张照片的内容：场景、主体、人物/物品、动作、环境氛围。
输出将用于短视频脚本创作，请客观描述，控制在 150 字以内。不要评价照片质量。"""


class MaterialService:
    """素材导入服务"""

    def __init__(self, db) -> None:
        self.db = db

    async def upload_file(
        self, filename: str, data: bytes, content_type: str, user_id: int
    ) -> dict:
        """上传单个素材文件，返回类型与可读描述。"""
        ext = _ext(filename)
        obj_name = f"{_PREFIX}{user_id}/{datetime.now():%Y%m%d}/{uuid.uuid4().hex[:8]}_{filename}"

        try:
            upload_file(_BUCKET, obj_name, data, content_type)
        except Exception as exc:
            logger.warning("copy_material_upload_failed", filename=filename, error=str(exc))
            return {
                "ok": False, "filename": filename, "type": "unknown",
                "description": f"上传失败：{exc}", "object_name": None,
            }

        if ext in _PHOTO_EXTS:
            description = await self._analyze_photo(data, filename)
            mtype = "photo"
        elif ext in _TEXT_EXTS:
            try:
                text = data.decode("utf-8", errors="ignore").strip()
            except Exception:
                text = ""
            description = text[:2000] if text else "（空文本文件）"
            mtype = "text"
        elif ext in _VIDEO_EXTS:
            description = f"（视频文件 {filename}，仅作参考，暂不读取画面）"
            mtype = "video"
        else:
            description = f"（其他文件 {filename}，暂不支持解析内容）"
            mtype = "other"

        logger.info("copy_material_uploaded", filename=filename, type=mtype, object_name=obj_name)
        return {
            "ok": True, "filename": filename, "type": mtype,
            "description": description, "object_name": obj_name,
        }

    @staticmethod
    async def _analyze_photo(data: bytes, filename: str) -> str:
        """照片 → 视觉模型描述；未配置 key 时降级。"""
        provider = get_vision_provider()
        if provider is None:
            return f"（照片 {filename}，未配置视觉模型，无画面描述）"
        try:
            img_b64 = base64.b64encode(data).decode()
            try:
                desc = await provider.analyze(img_b64, _PHOTO_PROMPT)
            finally:
                del img_b64
            return desc.strip() or f"（照片 {filename}，无描述）"
        except Exception as exc:
            logger.warning("copy_material_photo_analyze_failed", filename=filename, error=str(exc))
            return f"（照片 {filename} 分析失败：{exc}）"

    @staticmethod
    def summarize(entries: list[dict]) -> str:
        """汇总素材描述为提示文本。"""
        if not entries:
            return ""
        parts = []
        for i, e in enumerate(entries, 1):
            if not e.get("ok"):
                continue
            desc = e.get("description", "") or ""
            parts.append(f"素材{i}【{e.get('type')}】{e.get('filename')}：\n{desc}")
        return "\n\n---\n\n".join(parts)


def _ext(filename: str) -> str:
    """返回小写扩展名（含点），无则空。"""
    m = re.search(r"(\.[^.\\/]+)$", filename or "")
    return m.group(1).lower() if m else ""


async def fetch_link_content(url: str) -> str:
    """抓取链接正文（复用文章模块的抓取工具）。"""
    from app.articles.imitate import fetch_article_content

    return await fetch_article_content(url, use_jina_fallback=True)
