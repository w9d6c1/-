"""文档图片加载 — 为检索结果附带正文图片，供问答带图展示。

仅读取 doc_image 表（采集转存结果），按文档聚合、按 seq 排序。
"""

from typing import TYPE_CHECKING

from sqlalchemy import select

from app.collector.image_extractor import image_url_path
from app.core.database import AsyncSessionLocal
from app.core.logging import logger
from app.models.document import DocImage

if TYPE_CHECKING:
    from app.retrieval.fusion import FusionResult

MAX_IMAGES_PER_DOC = 3


async def load_images_for_docs(doc_ids: list[int]) -> dict[int, list[dict]]:
    """批量加载文档图片，返回 {doc_id: [图片字典]}。

    每篇文档最多返回 MAX_IMAGES_PER_DOC 张（按正文顺序）。
    图片字典含 id/object_name/url/width/height/seq，url 为公开只读服务路径。
    任何异常均被吞掉并返回空映射，绝不阻塞问答主链路。
    """
    unique_ids = sorted({d for d in doc_ids if d})
    if not unique_ids:
        return {}

    try:
        async with AsyncSessionLocal() as db:
            stmt = (
                select(DocImage)
                .where(DocImage.doc_id.in_(unique_ids))
                .order_by(DocImage.doc_id, DocImage.seq)
            )
            rows = (await db.execute(stmt)).scalars().all()
    except Exception:
        logger.warning("doc_images_load_failed", exc_info=True)
        return {}

    result: dict[int, list[dict]] = {}
    for row in rows:
        bucket = result.setdefault(row.doc_id, [])
        if len(bucket) >= MAX_IMAGES_PER_DOC:
            continue
        bucket.append(
            {
                "id": row.id,
                "seq": row.seq,
                "object_name": row.object_name,
                "url": image_url_path(row.object_name),
                "width": row.width,
                "height": row.height,
            }
        )
    return result


async def build_image_registry(docs: list["FusionResult"]) -> list[dict]:
    """为检索结果构建全局图片注册表。

    按检索文档顺序为每篇文档的图片分配全局编号（1 起），
    返回 [{id, doc_index, seq, url, object_name, width, height}]。
    doc_index 为文档在 retrieved_docs 中的 1 基序号，与引用编号一致。
    加载失败返回空列表，不影响主链路。
    """
    if not docs:
        return []
    try:
        images_by_doc = await load_images_for_docs([d.doc_id for d in docs])
    except Exception:
        return []

    registry: list[dict] = []
    global_id = 0
    for idx, doc in enumerate(docs, start=1):
        for img in images_by_doc.get(doc.doc_id, []):
            global_id += 1
            registry.append(
                {
                    "id": global_id,
                    "doc_index": idx,
                    "seq": img["seq"],
                    "url": img["url"],
                    "object_name": img["object_name"],
                    "width": img.get("width"),
                    "height": img.get("height"),
                }
            )
    return registry
