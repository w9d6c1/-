"""从 MySQL 重灌全部在线文档到 ES + Milvus。

用途：Milvus 集合经 scripts/migrate_milvus_source_type.py --rebuild 重建后，向量被清空，
需运行本脚本从 MySQL（source of truth）重新生成向量并写回 ES + Milvus。
重灌时会自动携带 source_type 等来源字段（来自 knowledge_doc）。

依赖：embedding 模型/服务可用（见 config embedding_model / siliconflow_api_key）。

运行（kb-backend 容器内，工作目录 /app）: python scripts/reindex_all.py
"""

import asyncio

from app.core.database import AsyncSessionLocal
from app.core.logging import logger
from app.retrieval.sync import sync_all_online


async def main() -> int:
    async with AsyncSessionLocal() as db:
        total = await sync_all_online(db)
    logger.info("reindex_all_done", total=total)
    print(f"重灌完成，写入 {total} 条 ES+Milvus 记录")
    return total


if __name__ == "__main__":
    asyncio.run(main())
