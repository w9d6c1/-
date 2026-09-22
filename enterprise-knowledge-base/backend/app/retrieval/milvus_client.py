"""Milvus Dense 向量检索 — 三 Collection 物理隔离 (MilvusClient API)"""

from dataclasses import dataclass, field

from langchain_core.documents import Document
from pymilvus import CollectionSchema, DataType, FieldSchema, MilvusClient
from pymilvus.milvus_client.index import IndexParams

from app.core.config import settings
from app.core.logging import logger


@dataclass
class MilvusConfig:
    host: str
    port: int
    dimension: int = 1024


@dataclass
class MilvusResult:
    doc_id: int
    chunk_index: int
    content: str
    score: float
    scope: str
    metadata: dict = field(default_factory=dict)


def create_milvus_config() -> MilvusConfig:
    return MilvusConfig(host=settings.milvus_host, port=settings.milvus_port, dimension=1024)


def get_collection_name(scope: str | None) -> str:
    return f"coll_{scope_name}" if (scope_name := scope or "public") else "coll_public"


_client: MilvusClient | None = None
_collection_fields_cache: dict[str, set[str]] = {}


def _get_client() -> MilvusClient:
    global _client
    if _client is None:
        _client = MilvusClient(uri=f"http://{settings.milvus_host}:{settings.milvus_port}", timeout=10)
    return _client


def _collection_fields(client: MilvusClient, coll_name: str) -> set[str]:
    """缓存式获取集合字段名集合（进程内每集合仅 describe 一次）。

    Milvus 2.4 服务端不支持在线加字段（AddCollectionField 未实现），故 source_type
    仅存在于新建集合或经重建迁移后的集合。此处探测字段是否存在，供写入/检索按需处理，
    避免对无 source_type 字段的旧集合请求该字段导致报错。
    """
    cached = _collection_fields_cache.get(coll_name)
    if cached is not None:
        return cached
    try:
        desc = client.describe_collection(coll_name)
        names = {f.get("name") for f in desc.get("fields", [])}
    except Exception:
        logger.warning("milvus_describe_collection_failed", collection=coll_name, exc_info=True)
        names = set()
    _collection_fields_cache[coll_name] = names
    return names


def _has_source_type(client: MilvusClient, coll_name: str) -> bool:
    return "source_type" in _collection_fields(client, coll_name)


def _has_source_name(client: MilvusClient, coll_name: str) -> bool:
    return "source_name" in _collection_fields(client, coll_name)


def _has_original_url(client: MilvusClient, coll_name: str) -> bool:
    return "original_url" in _collection_fields(client, coll_name)


def _ensure_collection(scope: str, config: MilvusConfig | None = None) -> str:
    cfg = config or create_milvus_config()
    coll_name = get_collection_name(scope)
    client = _get_client()

    if client.has_collection(coll_name):
        return coll_name

    fields: list[FieldSchema] = [
        FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=100, is_primary=True),
        FieldSchema(name="vector", dtype=DataType.FLOAT_VECTOR, dim=cfg.dimension),
        FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=65535),
        FieldSchema(name="doc_id", dtype=DataType.INT64),
        FieldSchema(name="chunk_index", dtype=DataType.INT64),
        FieldSchema(name="scope", dtype=DataType.VARCHAR, max_length=20),
        FieldSchema(name="title", dtype=DataType.VARCHAR, max_length=500),
        FieldSchema(name="source_type", dtype=DataType.VARCHAR, max_length=32),
        FieldSchema(name="source_name", dtype=DataType.VARCHAR, max_length=200),
        FieldSchema(name="original_url", dtype=DataType.VARCHAR, max_length=2048),
    ]
    schema = CollectionSchema(fields=fields, enable_dynamic_field=False)
    client.create_collection(
        collection_name=coll_name,
        schema=schema,
    )
    index_params = IndexParams()
    index_params.add_index(field_name="vector", metric_type="IP", index_type="IVF_FLAT", params={"nlist": 128})
    client.create_index(
        collection_name=coll_name,
        index_params=index_params,
    )
    client.load_collection(coll_name)
    _collection_fields_cache[coll_name] = {f.name for f in fields}
    return coll_name


def preload_collections(scopes: list[str] | None = None) -> None:
    scopes = scopes or ["public", "internal", "customer"]
    for scope in scopes:
        try:
            client = _get_client()
            _ensure_collection(scope)
            client.load_collection(get_collection_name(scope))
            stats = client.get_collection_stats(get_collection_name(scope))
            logger.info("milvus_collection_preloaded", scope=scope, stats=stats)
        except Exception:
            logger.warning("milvus_collection_preload_failed", scope=scope, exc_info=True)


async def insert_vectors(
    docs: list[Document],
    embeddings: list[list[float]],
    scope: str,
) -> int:
    if not docs:
        return 0

    coll_name = _ensure_collection(scope)
    client = _get_client()
    has_source = _has_source_type(client, coll_name)
    has_source_name = _has_source_name(client, coll_name)
    has_original_url = _has_original_url(client, coll_name)
    data: list[dict] = []
    for i, doc in enumerate(docs):
        row: dict = {
            "id": f"{doc.metadata.get('doc_id', 0)}_{doc.metadata.get('chunk_index', 0)}",
            "vector": embeddings[i],
            "content": doc.page_content[:65535],
            "doc_id": doc.metadata.get("doc_id", 0),
            "chunk_index": doc.metadata.get("chunk_index", 0),
            "scope": scope,
            "title": doc.metadata.get("title", "")[:500],
        }
        if has_source:
            row["source_type"] = str(doc.metadata.get("source_type", "internal") or "internal")[:32]
        if has_source_name:
            row["source_name"] = str(doc.metadata.get("source_name", "") or "")[:200]
        if has_original_url:
            row["original_url"] = str(doc.metadata.get("original_url", "") or "")[:2048]
        data.append(row)
    result = client.insert(collection_name=coll_name, data=data)
    return result["insert_count"]


async def dense_search(
    query_vector: list[float],
    scope: str,
    top_k: int = 5,
) -> list[MilvusResult]:
    try:
        coll_name = _ensure_collection(scope)
        client = _get_client()
    except Exception:
        return []

    output_fields = ["content", "doc_id", "chunk_index", "scope", "title"]
    if _has_source_type(client, coll_name):
        output_fields.append("source_type")
    if _has_source_name(client, coll_name):
        output_fields.append("source_name")
    if _has_original_url(client, coll_name):
        output_fields.append("original_url")

    try:
        results = client.search(
            collection_name=coll_name,
            data=[query_vector],
            anns_field="vector",
            limit=top_k,
            output_fields=output_fields,
            search_params={"metric_type": "IP", "params": {"nprobe": 16}},
        )
    except Exception:
        logger.warning("milvus_search_failed", scope=scope)
        return []

    output: list[MilvusResult] = []
    for hits in results:
        for hit in hits:
            entity: dict = hit.get("entity", hit)  # type: ignore[arg-type]
            output.append(MilvusResult(
                doc_id=entity.get("doc_id", 0),
                chunk_index=entity.get("chunk_index", 0),
                content=entity.get("content", ""),
                score=hit.get("distance", 0),
                scope=entity.get("scope", scope),
                metadata={
                    "title": entity.get("title", ""),
                    "source_type": entity.get("source_type", "internal") or "internal",
                    "source_name": entity.get("source_name", ""),
                    "original_url": entity.get("original_url", ""),
                },
            ))
    return output


async def delete_doc_from_milvus(doc_id: int, scope: str) -> int:
    try:
        coll_name = _ensure_collection(scope)
        client = _get_client()
    except Exception:
        return 0
    result = client.delete(collection_name=coll_name, filter=f"doc_id == {doc_id}")
    return len(result) if isinstance(result, list) else 0


async def delete_doc_from_all_scopes(doc_id: int) -> int:
    total = 0
    for scope in ("public", "internal", "customer"):
        total += await delete_doc_from_milvus(doc_id, scope)
    return total
