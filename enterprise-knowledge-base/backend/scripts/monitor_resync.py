"""向量补同步监控 — 检测「有切片但向量缺失/不全」的文档并自动重新同步。

背景：批量 OCR 导入时，embedding 接口（SiliconFlow）抖动会导致个别书
MySQL 有切片、但 ES/Milvus 无向量（或数量不足）。导入脚本按标题去重，
重跑会跳过这些书，故需本监控周期扫描并补齐。

运行（kb-backend 或独立容器内，工作目录 /app）:
    python scripts/monitor_resync.py                          # 单次
    python scripts/monitor_resync.py --loop --interval 900    # 常驻，每 15 分钟一次

判定：对每个 online+approved 且已过 grace 期的文档，比较 doc_chunk 行数与
idx_bm25_{scope} / coll_{scope} 中该 doc_id 的向量数；不一致则先清除残留再
重新 sync_document。
"""

import argparse
import asyncio
from datetime import UTC, datetime, timedelta

import httpx
from pymilvus import MilvusClient
from sqlalchemy import func, select

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.document import DocChunk, KnowledgeDoc
from app.retrieval.sync import sync_document


def _es_count(doc_id: int, scope: str) -> int:
    idx = f"idx_bm25_{scope}"
    try:
        r = httpx.post(
            f"http://{settings.es_host}:{settings.es_port}/{idx}/_count",
            json={"query": {"term": {"doc_id": doc_id}}},
            timeout=15,
        )
        return int(r.json().get("count", 0))
    except Exception:
        return -1


def _mv_count(client: MilvusClient, doc_id: int, scope: str) -> int:
    try:
        rows = client.query(
            collection_name=f"coll_{scope}",
            filter=f"doc_id == {doc_id}",
            output_fields=["doc_id"],
            limit=16384,
        )
        return len(rows)
    except Exception:
        return -1


def _es_delete(doc_id: int, scope: str) -> None:
    idx = f"idx_bm25_{scope}"
    try:
        httpx.post(
            f"http://{settings.es_host}:{settings.es_port}/{idx}/_delete_by_query",
            json={"query": {"term": {"doc_id": doc_id}}},
            timeout=30,
        )
    except Exception:
        pass


def _mv_delete(client: MilvusClient, doc_id: int, scope: str) -> None:
    try:
        client.delete(collection_name=f"coll_{scope}", filter=f"doc_id == {doc_id}")
    except Exception:
        pass


async def run_once(grace_minutes: int = 30) -> int:
    async with AsyncSessionLocal() as db:
        stmt = select(KnowledgeDoc).where(
            KnowledgeDoc.status == "online",
            KnowledgeDoc.review_status == "approved",
        )
        docs = list((await db.execute(stmt)).scalars())

    client = MilvusClient(uri=f"http://{settings.milvus_host}:{settings.milvus_port}")
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(minutes=grace_minutes)

    fixed = 0
    touched: set[str] = set()
    for doc in docs:
        if doc.created_at and doc.created_at > cutoff:
            continue
        async with AsyncSessionLocal() as db:
            n = (
                await db.execute(
                    select(func.count()).select_from(DocChunk).where(DocChunk.doc_id == doc.id)
                )
            ).scalar() or 0
        if n == 0:
            continue

        scope = doc.scope or "public"
        es = _es_count(doc.id, scope)
        mv = _mv_count(client, doc.id, scope)
        if es == n and mv == n:
            continue

        print(f"[resync] doc {doc.id} '{doc.title}' chunks={n} es={es} mv={mv} -> 补同步", flush=True)
        _es_delete(doc.id, scope)
        _mv_delete(client, doc.id, scope)
        touched.add(scope)
        async with AsyncSessionLocal() as db:
            try:
                total = await sync_document(db, doc.id)
                if total == 0:
                    print(f"[resync] doc {doc.id} 同步返回 0（分类禁用/未审核？）", flush=True)
                else:
                    print(f"[resync] doc {doc.id} -> 已写入 {total}", flush=True)
                    fixed += 1
            except Exception as exc:  # noqa: BLE001
                print(f"[resync] doc {doc.id} 失败: {exc}", flush=True)

    for scope in touched:
        try:
            client.flush(f"coll_{scope}")
        except Exception:
            pass

    print(f"[resync] 本轮完成，修复 {fixed} 篇", flush=True)
    return fixed


async def main_loop(loop: bool, interval: int, grace_minutes: int) -> None:
    """单事件循环内循环执行：避免跨 asyncio.run 复用连接池/客户端导致
    'Future attached to a different loop'。"""
    while True:
        try:
            await run_once(grace_minutes)
        except Exception as exc:  # noqa: BLE001
            print(f"[resync] 运行异常: {exc}", flush=True)
        if not loop:
            break
        await asyncio.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser(description="向量补同步监控")
    parser.add_argument("--loop", action="store_true", help="常驻循环")
    parser.add_argument("--interval", type=int, default=900, help="循环间隔秒数，默认 900")
    parser.add_argument("--grace-minutes", type=int, default=30, help="文档创建后多少分钟内不处理")
    args = parser.parse_args()

    asyncio.run(main_loop(args.loop, args.interval, args.grace_minutes))


if __name__ == "__main__":
    main()
