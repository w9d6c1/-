"""采集入库服务 — 清洗后的文章写入知识库，含跨平台去重合并与多来源链接管理。

去重策略（三级）：
1. 同平台 external_id 已存在 → 跳过（增量同步幂等）。
2. content_hash 精确命中已有 public 文档 → 合并（追加来源链接，不重建文档）。
3. SimHash 近似 + 标题相似命中 → 合并。
4. 均未命中 → 新建文档（scope=public，status=online）+ 切片 + 同步 + 主来源链接。
"""

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.collector.dedup import (
    content_fingerprint,
    content_hash,
    hamming_distance,
    title_similarity,
)
from app.collector.image_extractor import IMG_PLACEHOLDER_RE, ExtractedImage
from app.collector.models import PLATFORM_DISPLAY_NAMES, RawArticle
from app.core.logging import logger
from app.models.collector import DocSourceLink
from app.models.document import DocChunk, DocImage, KnowledgeDoc
from app.services.chunking import chunk_content

ACTION_CREATED = "created"
ACTION_MERGED = "merged"
ACTION_SKIPPED = "skipped"

_TITLE_MAX = 500
_RAW_TEXT_MAX_BYTES = 60000  # MySQL TEXT 上限 65535 字节，留余量


def _truncate_utf8(text: str | None, max_bytes: int = _RAW_TEXT_MAX_BYTES) -> str | None:
    """按 UTF-8 字节数截断，避免超出 MySQL TEXT 列限制。"""
    if not text:
        return text
    data = text.encode("utf-8")
    if len(data) <= max_bytes:
        return text
    return data[:max_bytes].decode("utf-8", errors="ignore")


def _strip_chunk_markers(text: str) -> str:
    """剥离切片中的 [[IMG:n]] 占位符并压缩多余空行。"""
    if "[[IMG:" not in text:
        return text
    text = IMG_PLACEHOLDER_RE.sub("", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


@dataclass
class IngestOutcome:
    action: str
    doc_id: int | None = None
    reason: str = ""


class SourceContentService:
    def __init__(
        self,
        db: AsyncSession,
        *,
        hamming_threshold: int = 3,
        title_threshold: float = 0.85,
        near_dup_scan_limit: int = 1000,
    ) -> None:
        self.db = db
        self.hamming_threshold = hamming_threshold
        self.title_threshold = title_threshold
        self.near_dup_scan_limit = near_dup_scan_limit
        self._chunk_count = 0

    async def ingest(
        self,
        article: RawArticle,
        plain_text: str,
        *,
        category_id: int,
        chunk_size: int = 512,
        chunk_overlap: int = 80,
        image_text: str | None = None,
        images: list[ExtractedImage] | None = None,
        raw_html: str | None = None,
    ) -> IngestOutcome:
        if not plain_text or not plain_text.strip():
            return IngestOutcome(ACTION_SKIPPED, reason="empty_content")

        if article.external_id:
            existing = await self._find_link(article.platform, article.external_id)
            if existing is not None:
                return IngestOutcome(ACTION_SKIPPED, doc_id=existing.doc_id, reason="external_id_exists")

        c_hash = content_hash(plain_text)
        c_simhash = content_fingerprint(plain_text)

        exact_doc = await self._find_by_content_hash(c_hash)
        if exact_doc is not None:
            await self._add_source_link(exact_doc.id, article, is_primary=False)
            logger.info("collector_merge_exact", doc_id=exact_doc.id, platform=article.platform)
            return IngestOutcome(ACTION_MERGED, doc_id=exact_doc.id, reason="exact_content_hash")

        near_doc = await self._find_near_duplicate(article.title, c_simhash)
        if near_doc is not None:
            await self._add_source_link(near_doc.id, article, is_primary=False)
            logger.info("collector_merge_near", doc_id=near_doc.id, platform=article.platform)
            return IngestOutcome(ACTION_MERGED, doc_id=near_doc.id, reason="near_duplicate")

        doc = await self._create_document(
            article,
            plain_text,
            c_hash,
            c_simhash,
            category_id,
            chunk_size,
            chunk_overlap,
            image_text=image_text,
            images=images,
            raw_html=raw_html,
        )
        await self._add_source_link(doc.id, article, is_primary=True)
        logger.info("collector_created", doc_id=doc.id, platform=article.platform)
        return IngestOutcome(ACTION_CREATED, doc_id=doc.id, reason="new_document")

    async def has_source_link(self, platform: str, external_id: str) -> bool:
        """external_id 是否已入库（用于采集侧提前跳过，避免无效图片下载）。"""
        if not external_id:
            return False
        return await self._find_link(platform, external_id) is not None

    async def _find_link(self, platform: str, external_id: str) -> DocSourceLink | None:
        stmt = (
            select(DocSourceLink)
            .where(DocSourceLink.platform == platform, DocSourceLink.external_id == external_id)
            .limit(1)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def _find_by_content_hash(self, c_hash: str) -> KnowledgeDoc | None:
        stmt = (
            select(KnowledgeDoc)
            .where(KnowledgeDoc.content_hash == c_hash, KnowledgeDoc.scope == "public")
            .limit(1)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def _find_near_duplicate(self, title: str, c_simhash: int) -> KnowledgeDoc | None:
        stmt = (
            select(KnowledgeDoc)
            .where(KnowledgeDoc.scope == "public", KnowledgeDoc.content_simhash.isnot(None))
            .order_by(KnowledgeDoc.id.desc())
            .limit(self.near_dup_scan_limit)
        )
        candidates = (await self.db.execute(stmt)).scalars().all()
        for doc in candidates:
            if doc.content_simhash is None:
                continue
            distance = hamming_distance(c_simhash, doc.content_simhash)
            if distance <= self.hamming_threshold:
                return doc
            if (
                title_similarity(title, doc.title) >= self.title_threshold
                and distance <= self.hamming_threshold * 2
            ):
                return doc
        return None

    async def _create_document(
        self,
        article: RawArticle,
        plain_text: str,
        c_hash: str,
        c_simhash: int,
        category_id: int,
        chunk_size: int,
        chunk_overlap: int,
        *,
        image_text: str | None = None,
        images: list[ExtractedImage] | None = None,
        raw_html: str | None = None,
    ) -> KnowledgeDoc:
        source_name = article.source_name or PLATFORM_DISPLAY_NAMES.get(article.platform, article.platform)
        doc = KnowledgeDoc(
            category_id=category_id,
            title=(article.title or "未命名")[:_TITLE_MAX],
            scope="public",
            source_type=article.platform,
            source_name=source_name,
            original_url=article.original_url or None,
            publish_time=article.publish_time,
            plain_text=plain_text,
            word_count=len(plain_text),
            file_type="txt",
            file_path="",
            chunk_strategy="recursive",
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            status="online",
            review_status="approved",
            content_hash=c_hash,
            content_simhash=c_simhash,
            raw_text=_truncate_utf8(raw_html),
        )
        self.db.add(doc)
        await self.db.flush()

        chunk_image_map = self._build_chunks(doc.id, image_text or plain_text, chunk_size, chunk_overlap)
        doc.chunk_count = self._chunk_count
        for img in images or []:
            self.db.add(
                DocImage(
                    doc_id=doc.id,
                    chunk_index=chunk_image_map.get(img.seq),
                    seq=img.seq,
                    object_name=img.object_name,
                    original_url=(img.original_url or "")[:1024] or None,
                    content_hash=img.content_hash,
                    width=img.width,
                    height=img.height,
                )
            )
        await self.db.commit()
        await self.db.refresh(doc)

        from app.retrieval.sync import sync_document

        await sync_document(self.db, doc.id)
        return doc

    def _build_chunks(
        self, doc_id: int, text: str, chunk_size: int, chunk_overlap: int
    ) -> dict[int, int]:
        """切片并建立图片占位符 → 切片序号映射；剥离占位符后写入 DocChunk。

        纯图片占位符切片（剥离后为空）被跳过，切片序号按实际入库顺序重编。
        返回 {图片seq: chunk_index}。
        """
        chunk_image_map: dict[int, int] = {}
        stored_index = 0
        for raw_chunk in chunk_content(text, "recursive", chunk_size, chunk_overlap):
            seqs = [int(s) for s in IMG_PLACEHOLDER_RE.findall(raw_chunk)]
            clean = _strip_chunk_markers(raw_chunk)
            for seq in seqs:
                chunk_image_map.setdefault(seq, stored_index)
            if not clean:
                continue
            self.db.add(DocChunk(doc_id=doc_id, chunk_index=stored_index, content=clean, scope="public"))
            stored_index += 1
        self._chunk_count = stored_index
        return chunk_image_map

    async def _add_source_link(self, doc_id: int, article: RawArticle, *, is_primary: bool) -> None:
        source_name = article.source_name or PLATFORM_DISPLAY_NAMES.get(article.platform, article.platform)
        link = DocSourceLink(
            doc_id=doc_id,
            platform=article.platform,
            external_id=article.external_id or "",
            original_url=article.original_url or None,
            source_name=source_name,
            publish_time=article.publish_time,
            is_primary=is_primary,
        )
        self.db.add(link)
        await self.db.commit()
