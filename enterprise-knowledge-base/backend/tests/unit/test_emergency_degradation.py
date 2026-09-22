"""应急与回滚方案 — 故障降级预案测试

要求:
- 大模型故障时切换备用 API
- 向量库故障时降级为 BM25 检索
- 存储故障时的降级策略
"""

import re
from pathlib import Path

import pytest

# ── 容器内跳过：路径解析依赖宿主仓库根目录 ──
from pathlib import Path as _Path
_PROJECT = _Path(__file__).resolve().parent.parent.parent.parent
pytestmark = pytest.mark.skipif(
    not (_PROJECT / "backend" / "app").exists(),
    reason=f"需从宿主仓库根目录运行（{_PROJECT}/backend/app 不存在）",
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
BACKEND_ROOT = PROJECT_ROOT / "backend"
LLM_PY = BACKEND_ROOT / "app" / "agents" / "llm.py"
EMBEDDING_PY = BACKEND_ROOT / "app" / "agents" / "embedding.py"
RERANKER_PY = BACKEND_ROOT / "app" / "retrieval" / "reranker.py"
REWRITE_PY = BACKEND_ROOT / "app" / "agents" / "nodes" / "rewrite.py"
GENERATE_PY = BACKEND_ROOT / "app" / "agents" / "nodes" / "generate.py"
CONFIG_PY = BACKEND_ROOT / "app" / "core" / "config.py"
ES_CLIENT_PY = BACKEND_ROOT / "app" / "retrieval" / "es_client.py"
MILVUS_CLIENT_PY = BACKEND_ROOT / "app" / "retrieval" / "milvus_client.py"
GRAPH_PY = BACKEND_ROOT / "app" / "agents" / "graph.py"


# ============================================================
# DEG-01: LLM 调用有指数退避重试
# ============================================================
def test_llm_retry_with_backoff_exists():
    content = LLM_PY.read_text(encoding="utf-8")
    assert "call_llm_with_retry" in content or "acall_llm_with_retry" in content, (
        "llm.py 中缺少 call_llm_with_retry 函数"
    )
    # 应包含指数退避逻辑
    assert any(kw in content for kw in ("exponential", "backoff", "pow(2", "delay")), (
        "llm.py 的重试逻辑中缺少指数退避"
    )


# ============================================================
# DEG-02: 嵌入 API 失败时降级到本地 BGE 模型
# ============================================================
def test_embedding_fallback_to_local_exists():
    content = EMBEDDING_PY.read_text(encoding="utf-8")

    has_siliconflow = "siliconflow" in content.lower() or "_via_siliconflow" in content
    has_local = "local" in content.lower() or "_via_local" in content or "sentence_transformers" in content.lower()

    assert has_siliconflow, "embedding.py 中未引用 SiliconFlow API"
    assert has_local, "embedding.py 中缺少本地模型兜底逻辑（BGE）"

    # 验证降级路径：异常时回退到本地
    has_fallback = "except" in content and ("local" in content.lower() or "sentence_transformer" in content.lower())
    assert has_fallback, "embedding.py 中 API 异常时未降级到本地模型"


# ============================================================
# DEG-03: 重排序失败时降级到 RRF fused_score
# ============================================================
def test_reranker_fallback_to_fused_score_exists():
    content = RERANKER_PY.read_text(encoding="utf-8")
    assert "fused_score" in content, "reranker.py 中缺少 fused_score 降级逻辑"
    assert "except" in content, "reranker.py 中缺少异常捕获"


# ============================================================
# DEG-04: 查询改写失败时降级到 normalize_query
# ============================================================
def test_rewrite_fallback_to_normalize_exists():
    content = REWRITE_PY.read_text(encoding="utf-8")
    assert "normalize_query" in content, "rewrite.py 中缺少 normalize_query 降级函数"
    assert "except" in content, "rewrite.py 中 LLM 调用异常时未捕获"


# ============================================================
# DEG-05: 备用 LLM provider 配置存在
# ============================================================
def test_alternative_llm_provider_config_exists():
    content = CONFIG_PY.read_text(encoding="utf-8")

    # 当前仅有一个 LLM provider
    # 测试驱动添加 backup/additional provider 配置
    has_backup = any(kw in content for kw in (
        "backup_llm", "llm_backup", "fallback_llm", "alternative_llm",
        "llm_provider_backup", "llm_backup_api_key", "备用"
    ))
    assert has_backup, (
        "config.py 中缺少备用 LLM provider 配置字段。"
        "请添加 LLM_BACKUP_PROVIDER / LLM_BACKUP_BASE_URL / LLM_BACKUP_API_KEY，"
        "当主模型不可用时快速切换。"
    )


# ============================================================
# DEG-06: ES BM25 检索独立于 Milvus
# ============================================================
def test_bm25_search_independent_of_milvus():
    """验证 ES 客户端不依赖 Milvus，即可 BM25 独立检索"""
    es_content = ES_CLIENT_PY.read_text(encoding="utf-8")
    assert "import" in es_content, f"{ES_CLIENT_PY.name} 不完整"
    assert "elasticsearch" in es_content.lower(), f"{ES_CLIENT_PY.name} 未引用 ES SDK"

    # ES 文件不应 import milvus
    has_milvus_import = "milvus" in es_content.lower()
    assert not has_milvus_import, (
        "es_client.py 不应依赖 milvus 模块。"
        "BM25 检索应在 Milvus 宕机时独立可用。"
    )

    # Milvus 客户端在搜索失败时不应崩溃
    milvus_content = MILVUS_CLIENT_PY.read_text(encoding="utf-8")
    assert "except" in milvus_content, (
        "milvus_client.py 中搜索方法无异常捕获。"
        "Milvus 宕机时应返回空列表，不抛异常。"
    )


# ============================================================
# DEG-07: LLM 生成失败时返回友好降级文案
# ============================================================
def test_generate_node_returns_graceful_error():
    content = GENERATE_PY.read_text(encoding="utf-8")
    assert "except" in content, "generate.py 中 LLM 调用无异常捕获"
    has_graceful = any(kw in content for kw in ("抱歉", "请稍后", "请稍后再试", "稍后重试", "error"))
    assert has_graceful, (
        "generate.py 中 LLM 异常时未返回用户友好的降级文案"
    )


# ============================================================
# DEG-08: PG 连接失败时 Checkpointer 优雅降级
# ============================================================
def test_checkpointer_graceful_fallback_no_crash():
    content = GRAPH_PY.read_text(encoding="utf-8")
    assert "init_checkpointer" in content, "graph.py 中缺少 init_checkpointer 函数"

    # 该函数应在 PG 失败时返回 None 而不是抛出异常
    has_return_none = "return None" in content or "None" in content
    has_try = "try" in content.lower()
    assert has_return_none and has_try, (
        "init_checkpointer() 应 try/except 包裹，PG 连接失败时返回 None"
    )


# ============================================================
# DEG-09: 检索降级路径完整（Dense → BM25 → 空结果）
# ============================================================
def test_retrieval_degradation_path_complete():
    """验证检索模块在各级故障时都有降级路径"""
    fusion_content = (BACKEND_ROOT / "app" / "retrieval" / "fusion.py").read_text(encoding="utf-8")
    assert "dense_results" in fusion_content or "dense_search" in fusion_content, (
        "fusion.py 中缺少 dense 检索结果处理"
    )
    assert "bm25_results" in fusion_content or "es_search" in fusion_content or "bm25" in fusion_content.lower(), (
        "fusion.py 中缺少 BM25 检索结果处理"
    )
