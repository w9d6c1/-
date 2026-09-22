"""
Elasticsearch 索引模板初始化脚本
运行方式: python scripts/init_es.py
"""

import sys
import time

from elasticsearch import Elasticsearch

ES_HOST = "http://localhost:9200"

INDEX_TEMPLATES = {
    "coll_public": "公共知识 BM25 索引",
    "coll_customer": "客服知识 BM25 索引",
    "coll_internal": "内部知识 BM25 索引",
}


def create_index(es: Elasticsearch, name: str, description: str) -> None:
    if es.indices.exists(index=name):
        print(f"  索引 '{name}' 已存在，跳过")
        return

    body = {
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "analysis": {
                "analyzer": {
                    "ik_max_word_analyzer": {"type": "ik_max_word"},
                    "ik_smart_analyzer": {"type": "ik_smart"},
                }
            },
        },
        "mappings": {
            "properties": {
                "chunk_id": {"type": "integer"},
                "doc_id": {"type": "integer"},
                "chunk_index": {"type": "integer"},
                "content": {
                    "type": "text",
                    "analyzer": "ik_max_word",
                    "search_analyzer": "ik_smart",
                },
                "scope": {"type": "keyword"},
                "title": {"type": "text", "analyzer": "ik_max_word"},
                "created_at": {"type": "date"},
            }
        },
    }
    es.indices.create(index=name, body=body)
    print(f"  索引 '{name}' ({description}) 创建完成")


def main():
    print("等待 Elasticsearch 连接...")
    es = Elasticsearch(ES_HOST)

    for i in range(30):
        try:
            if es.ping():
                print("ES 连接成功")
                break
        except Exception:
            time.sleep(2)
    else:
        print("错误: 无法连接 Elasticsearch")
        sys.exit(1)

    print("\n创建索引:")
    for name, desc in INDEX_TEMPLATES.items():
        create_index(es, name, desc)

    print(f"\n当前所有索引: {list(es.indices.get_alias().keys())}")
    print("初始化完成")


if __name__ == "__main__":
    main()
