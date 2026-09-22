"""ES BM25 检索 — 三索引物理隔离"""

from dataclasses import dataclass, field

from elasticsearch import AsyncElasticsearch
from langchain_core.documents import Document

from app.core.config import settings


@dataclass
class ESConfig:
    host: str
    port: int

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"


@dataclass
class ESResult:
    doc_id: int
    chunk_index: int
    content: str
    score: float
    scope: str
    metadata: dict = field(default_factory=dict)


def create_es_config() -> ESConfig:
    return ESConfig(host=settings.es_host, port=settings.es_port)


_es_client: AsyncElasticsearch | None = None


def get_es_client(config: ESConfig | None = None) -> AsyncElasticsearch:
    global _es_client
    if _es_client is None:
        cfg = config or create_es_config()
        _es_client = AsyncElasticsearch(cfg.url, request_timeout=30, max_retries=3, retry_on_timeout=True)
    return _es_client


def get_index_name(scope: str | None) -> str:
    scope_name = scope or "public"
    return f"idx_bm25_{scope_name}"


async def create_bm25_index(scope: str) -> None:
    es = get_es_client()
    index_name = get_index_name(scope)
    exists = await es.indices.exists(index=index_name)
    if not exists:
        await es.indices.create(
            index=index_name,
            body={
                "mappings": {
                    "properties": {
                        "content": {"type": "text", "analyzer": "standard"},
                        "doc_id": {"type": "integer"},
                        "chunk_index": {"type": "integer"},
                        "scope": {"type": "keyword"},
                        "title": {"type": "text"},
                        "department": {"type": "keyword"},
                        "source_type": {"type": "keyword"},
                    }
                }
            },
        )


async def ensure_source_type_mapping(scope: str) -> bool:
    """为已存在索引在线补充 source_type 字段映射。

    ES 的 put_mapping 仅新增字段、非破坏性，存量文档该字段视为缺失，
    检索侧统一回退为 internal。索引不存在时返回 False。
    """
    es = get_es_client()
    index_name = get_index_name(scope)
    if not await es.indices.exists(index=index_name):
        return False
    await es.indices.put_mapping(
        index=index_name,
        properties={"source_type": {"type": "keyword"}},
    )
    return True


async def index_documents(docs: list[Document]) -> int:
    es = get_es_client()
    actions: list[dict] = []
    for doc in docs:
        doc_id = doc.metadata.get("doc_id", 0)
        chunk_idx = doc.metadata.get("chunk_index", 0)
        scope = doc.metadata.get("scope", "public")
        index_name = get_index_name(scope)
        actions.append({"index": {"_index": index_name, "_id": f"{doc_id}_{chunk_idx}"}})
        actions.append({
            "content": doc.page_content,
            "doc_id": doc_id,
            "chunk_index": chunk_idx,
            "scope": scope,
            "title": doc.metadata.get("title", ""),
            "department": doc.metadata.get("department", ""),
            "source_type": doc.metadata.get("source_type", "internal"),
            "source_name": doc.metadata.get("source_name", ""),
            "original_url": doc.metadata.get("original_url", ""),
        })
    if not actions:
        return 0
    result = await es.bulk(operations=actions, refresh=True)
    return sum(1 for item in result.get("items", []) if item.get("index", {}).get("result") == "created")


async def bm25_search(
    query: str,
    scope: str,
    top_k: int = 5,
) -> list[ESResult]:
    es = get_es_client()
    index_name = get_index_name(scope)
    body = {
        "query": {
            "match": {
                "content": {"query": query, "operator": "or"},
            }
        },
        "size": top_k,
    }
    result = await es.search(index=index_name, body=body)
    hits = result["hits"]["hits"]
    results: list[ESResult] = []
    for hit in hits:
        src = hit["_source"]
        results.append(ESResult(
            doc_id=src["doc_id"],
            chunk_index=src["chunk_index"],
            content=src["content"],
            score=hit["_score"],
            scope=src.get("scope", scope),
            metadata={
                "title": src.get("title", ""),
                "department": src.get("department", ""),
                "source_type": src.get("source_type", "internal"),
                "source_name": src.get("source_name", ""),
                "original_url": src.get("original_url", ""),
            },
        ))
    return results


async def delete_doc_from_es(doc_id: int, scope: str) -> int:
    es = get_es_client()
    index_name = get_index_name(scope)
    result = await es.delete_by_query(
        index=index_name,
        body={"query": {"term": {"doc_id": doc_id}}},
        refresh=True,
    )
    return result.get("deleted", 0)


async def delete_doc_from_all_scopes(doc_id: int) -> int:
    total = 0
    for scope in ("public", "internal", "customer"):
        total += await delete_doc_from_es(doc_id, scope)
    return total
