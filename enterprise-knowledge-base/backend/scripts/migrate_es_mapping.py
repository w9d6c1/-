"""Elasticsearch 在线 mapping 迁移 — 为 idx_bm25_* 索引补充 source_type 字段。

非破坏性：put_mapping 仅新增字段，存量文档该字段视为缺失，检索侧回退为 internal。

运行（kb-backend 容器内，工作目录 /app）:
    python scripts/migrate_es_mapping.py            # 执行迁移
    python scripts/migrate_es_mapping.py --dry-run  # 仅预检
"""

import argparse

from elasticsearch import Elasticsearch

from app.core.config import settings

SCOPES = ["public", "internal", "customer"]
FIELD = "source_type"


def _index_name(scope: str) -> str:
    return f"idx_bm25_{scope}"


def main() -> None:
    parser = argparse.ArgumentParser(description="ES source_type mapping 在线迁移")
    parser.add_argument("--dry-run", action="store_true", help="仅预检，不执行变更")
    args = parser.parse_args()

    es = Elasticsearch(settings.es_url, request_timeout=30)
    if not es.ping():
        raise SystemExit("错误: 无法连接 Elasticsearch")

    for scope in SCOPES:
        index = _index_name(scope)
        if not es.indices.exists(index=index):
            print(f"[skip] {index}: 索引不存在")
            continue
        mapping = es.indices.get_mapping(index=index)
        props = mapping[index]["mappings"].get("properties", {})
        if FIELD in props:
            print(f"[ok]   {index}: {FIELD} 已存在")
            continue
        if args.dry_run:
            print(f"[plan] {index}: 将新增 {FIELD}")
            continue
        es.indices.put_mapping(index=index, properties={FIELD: {"type": "keyword"}})
        print(f"[done] {index}: 已新增 {FIELD}")

    print("\n完成")


if __name__ == "__main__":
    main()
