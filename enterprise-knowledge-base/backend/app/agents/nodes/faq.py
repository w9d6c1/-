"""FAQ 精准匹配节点 — score>=0.85 短路返回"""

import asyncio
import copy
import math

import numpy as np

from app.agents.embedding import embed_faq_query as embed_query
from app.agents.embedding import embed_faq_texts as embed_texts
from app.agents.llm import clean_response
from app.agents.state import AgentState
from app.core.logging import logger

FAQ_MATCH_THRESHOLD = 0.85

FAQ_VECTORS: list[dict] = []
_faq_vectors_lock = asyncio.Lock()

# 预计算的归一化向量矩阵，与 FAQ_VECTORS 行对齐，用于 numpy 批量点积。
_faq_matrix: np.ndarray | None = None
_faq_scopes: list[str] = []
# 身份哨兵：矩阵是基于哪个 FAQ_VECTORS 对象构建的。
# 测试会直接 patch FAQ_VECTORS（绕过重建），身份不一致时回退到即时构建，保证正确性。
_faq_matrix_src: list | None = None


def _normalize_rows(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


def _rebuild_matrix_locked() -> None:
    """在持有 _faq_vectors_lock 时调用，重建归一化矩阵与 scope 索引。"""
    global _faq_matrix, _faq_scopes, _faq_matrix_src
    if FAQ_VECTORS:
        raw = np.asarray([e["vector"] for e in FAQ_VECTORS], dtype=np.float32)
        _faq_matrix = _normalize_rows(raw)
        _faq_scopes = [e["scope"] for e in FAQ_VECTORS]
    else:
        _faq_matrix = None
        _faq_scopes = []
    _faq_matrix_src = FAQ_VECTORS


async def _set_faq_vectors(faqs: list[dict], scopes: list[str] | None = None) -> int:
    async with _faq_vectors_lock:
        vectors: list[dict] = []
        faq_entries: list[dict] = []
        for faq in faqs:
            if scopes and faq["scope"] not in scopes:
                continue
            for q_text in faq.get("questions_for_embedding", [faq["question"]]):
                faq_entries.append({
                    "faq_id": faq["id"],
                    "question": q_text,
                    "content": faq["answer"],
                    "scope": faq["scope"],
                })

        if faq_entries:
            texts = [e["question"] for e in faq_entries]
            vecs = await embed_texts(texts)
            for entry, vec in zip(faq_entries, vecs):
                entry["vector"] = vec
                vectors.append(entry)

        global FAQ_VECTORS
        FAQ_VECTORS = vectors
        _rebuild_matrix_locked()
        count = len(vectors)
        logger.info("faq_vectors_loaded", count=count)
        return count


async def _clear_faq_vectors() -> None:
    async with _faq_vectors_lock:
        global FAQ_VECTORS
        FAQ_VECTORS = []
        _rebuild_matrix_locked()


def get_faq_vectors() -> list[dict]:
    return list(FAQ_VECTORS)


async def load_faq_vectors_from_db(db_session, scopes: list[str] | None = None) -> int:
    from app.services.faq_service import load_online_faqs

    faqs = await load_online_faqs(db_session, scopes=scopes)
    return await _set_faq_vectors(faqs, scopes=scopes)


async def refresh_faq_vectors_from_db(db_session, scopes: list[str] | None = None) -> int:
    return await load_faq_vectors_from_db(db_session, scopes=scopes)


async def upsert_faq_vector(faq: dict) -> None:
    """增量刷新单条 FAQ 的向量：移除该 faq_id 旧条目，再嵌入其全部问法。

    faq 需含 id / question / answer / scope / questions_for_embedding。
    """
    faq_id = faq["id"]
    questions = faq.get("questions_for_embedding") or [faq["question"]]
    entries = [
        {
            "faq_id": faq_id,
            "question": q,
            "content": faq["answer"],
            "scope": faq["scope"],
        }
        for q in questions
    ]
    async with _faq_vectors_lock:
        if entries:
            vecs = await embed_texts([e["question"] for e in entries])
            for entry, vec in zip(entries, vecs):
                entry["vector"] = vec
        global FAQ_VECTORS
        # 重新赋值（非原地修改），保证并发查询持有的快照仍然有效。
        FAQ_VECTORS = [e for e in FAQ_VECTORS if e["faq_id"] != faq_id] + entries
        _rebuild_matrix_locked()


async def remove_faq_vector(faq_id: int) -> None:
    """从内存索引移除某条 FAQ 的所有向量条目。"""
    async with _faq_vectors_lock:
        global FAQ_VECTORS
        FAQ_VECTORS = [e for e in FAQ_VECTORS if e["faq_id"] != faq_id]
        _rebuild_matrix_locked()


def _cosine_sim(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _best_faq_match(
    query_vec: list[float],
    entries: list[dict],
    matrix: np.ndarray | None,
    scopes_list: list[str],
    allowed_scopes: set[str],
) -> tuple[float, str | None]:
    """numpy 批量余弦相似度 + scope 掩码，返回 (最高分, 答案)。"""
    if not entries or matrix is None or matrix.shape[0] != len(entries):
        return 0.0, None

    query = np.asarray(query_vec, dtype=np.float32)
    q_norm = float(np.linalg.norm(query))
    if q_norm == 0.0:
        return 0.0, None

    # matrix 行已归一化，点积即余弦相似度。
    scores = matrix @ (query / q_norm)

    mask = np.fromiter(
        (s in allowed_scopes for s in scopes_list), dtype=bool, count=len(scopes_list)
    )
    if not mask.any():
        return 0.0, None
    scores = np.where(mask, scores, -np.inf)

    best_idx = int(np.argmax(scores))
    best_score = float(scores[best_idx])
    if not np.isfinite(best_score):
        return 0.0, None
    return best_score, entries[best_idx]["content"]


async def faq_match_node(state: AgentState) -> AgentState:
    result = copy.deepcopy(state)
    result["faq_hit"] = False
    result["faq_answer"] = None

    query = state.get("rewritten_query") or state.get("original_query", "")
    if not query:
        return result

    allowed_scopes = set(state.get("user_scopes", []))
    if not FAQ_VECTORS:
        return result

    query_vec = await embed_query(query)

    # await 之后原子快照，避免与并发增量刷新竞争。
    entries = FAQ_VECTORS
    if _faq_matrix is not None and _faq_matrix_src is entries:
        matrix = _faq_matrix
        scopes_list = _faq_scopes
    else:
        # FAQ_VECTORS 被直接替换（如测试）或矩阵未同步，就地构建。
        if not entries:
            return result
        matrix = _normalize_rows(
            np.asarray([e["vector"] for e in entries], dtype=np.float32)
        )
        scopes_list = [e["scope"] for e in entries]

    best_score, best_answer = _best_faq_match(
        query_vec, entries, matrix, scopes_list, allowed_scopes
    )

    if best_score >= FAQ_MATCH_THRESHOLD and best_answer is not None:
        result["faq_hit"] = True
        result["faq_answer"] = best_answer
        result["route"] = "faq_answer"
        result["context"] = f"参考FAQ答案：\n{clean_response(best_answer)}"

    return result
