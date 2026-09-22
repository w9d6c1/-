"""Milvus 集合迁移 — 为 coll_* 集合引入 source_type/source_name/original_url 标量字段（重建式）。

背景：Milvus 2.4 服务端不支持在线加字段（AddCollectionField 未实现），故无法对已存在
集合直接 add_field。唯一可行路径为「重建集合（drop + create 含新字段的新 schema）
+ 从 MySQL 重灌向量」。

操作流程（低峰维护窗口）:
    1. python scripts/migrate_milvus_source_type.py            # 预检：查看各集合字段与行数
    2. python scripts/migrate_milvus_source_type.py --rebuild --confirm   # 破坏性：重建集合（清空向量）
    3. python scripts/reindex_all.py                           # 从 MySQL 重灌向量（需 embedding 可用）

运行环境：kb-backend 容器内，工作目录 /app。
"""

import argparse

from app.retrieval.milvus_client import _ensure_collection, _get_client, get_collection_name

SCOPES = ["public", "internal", "customer"]
REQUIRED_FIELDS = ["source_type", "source_name", "original_url"]


def _row_count(client, coll: str) -> int:
    try:
        return int(client.get_collection_stats(coll).get("row_count", 0))
    except Exception:
        return -1


def _get_fields(client, coll: str) -> set[str] | None:
    if not client.has_collection(coll):
        return None
    desc = client.describe_collection(coll)
    return {f.get("name") for f in desc.get("fields", [])}


def check(client) -> None:
    print("集合元数据字段状态：")
    for scope in SCOPES:
        coll = get_collection_name(scope)
        if not client.has_collection(coll):
            print(f"  [absent ] {coll}: 集合不存在")
            continue
        fields = _get_fields(client, coll)
        rows = _row_count(client, coll)
        missing = [f for f in REQUIRED_FIELDS if f not in (fields or set())]
        if missing:
            mark = "INCOMPLETE"
            detail = f"缺少: {', '.join(missing)}"
        else:
            mark = "ok"
            detail = "字段完整"
        print(f"  [{mark:10}] {coll}: {detail} (rows={rows})")


def rebuild(client) -> None:
    print("重建集合（drop + create 含完整元数据字段的新 schema）：")
    for scope in SCOPES:
        coll = get_collection_name(scope)
        rows_before = _row_count(client, coll) if client.has_collection(coll) else 0
        if client.has_collection(coll):
            client.drop_collection(coll)
        _ensure_collection(scope)
        print(f"  [rebuilt] {coll}: 原 rows={rows_before} 已清空，须运行 scripts/reindex_all.py 重灌")
    print("\n重建完成。请立即运行: python scripts/reindex_all.py")


def main() -> None:
    parser = argparse.ArgumentParser(description="Milvus 集合元数据字段迁移（重建式）")
    parser.add_argument("--rebuild", action="store_true", help="重建集合（破坏性，清空向量）")
    parser.add_argument("--confirm", action="store_true", help="与 --rebuild 同用，确认执行破坏性操作")
    args = parser.parse_args()

    client = _get_client()
    if args.rebuild:
        if not args.confirm:
            raise SystemExit(
                "重建为破坏性操作，会清空集合向量！须追加 --confirm，并在低峰期执行；"
                "重建后须运行 scripts/reindex_all.py 从 MySQL 重灌。"
            )
        rebuild(client)
    else:
        check(client)


if __name__ == "__main__":
    main()
