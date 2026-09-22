"""
Milvus 三 Collection 初始化脚本
运行方式: python scripts/init_milvus.py
"""

import sys
import time

from pymilvus import (
    Collection,
    CollectionSchema,
    DataType,
    FieldSchema,
    connections,
    utility,
)

MILVUS_HOST = "localhost"
MILVUS_PORT = 19530
EMBEDDING_DIM = 1024  # bge-large-zh 输出维度

COLLECTIONS = {
    "coll_public": "公共知识",
    "coll_customer": "客服知识",
    "coll_internal": "内部知识",
}


def create_collection(name: str, description: str) -> Collection:
    if utility.has_collection(name):
        print(f"  Collection '{name}' 已存在，跳过")
        return Collection(name)

    fields = [
        FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=100, is_primary=True),
        FieldSchema(name="doc_id", dtype=DataType.INT64),
        FieldSchema(name="chunk_index", dtype=DataType.INT32),
        FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=65535),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=EMBEDDING_DIM),
    ]
    schema = CollectionSchema(fields=fields, description=description)
    col = Collection(name=name, schema=schema)

    index_params = {
        "metric_type": "COSINE",
        "index_type": "HNSW",
        "params": {"M": 16, "efConstruction": 200},
    }
    col.create_index(field_name="embedding", index_params=index_params)
    col.load()
    print(f"  Collection '{name}' 创建完成 (dim={EMBEDDING_DIM}, index=HNSW)")
    return col


def main():
    print("等待 Milvus 连接...")
    for i in range(30):
        try:
            connections.connect(host=MILVUS_HOST, port=MILVUS_PORT)
            print("Milvus 连接成功")
            break
        except Exception:
            time.sleep(2)
    else:
        print("错误: 无法连接 Milvus")
        sys.exit(1)

    print("\n创建 Collection:")
    for name, desc in COLLECTIONS.items():
        create_collection(name, desc)

    print(f"\n当前所有 Collection: {utility.list_collections()}")
    print("初始化完成")


if __name__ == "__main__":
    main()
