"""上下文组装节点 — Token 预算 + 截断"""

import copy

from app.agents.llm import clean_response, count_tokens
from app.agents.state import AgentState
from app.retrieval.fusion import FusionResult

MAX_CONTEXT_TOKENS = 3000


def _format_doc(doc: FusionResult, index: int, image_ids: list[int]) -> str:
    source_label = ""
    source_type = doc.metadata.get("source_type", "internal")
    source_name = doc.metadata.get("source_name", "")
    if source_name:
        source_label = f"（来源：{source_name}）"
    elif source_type and source_type != "internal":
        source_label = f"（来源：{source_type}）"
    base = f"[{index}]{source_label} {clean_response(doc.content)}\n"
    if image_ids:
        refs = "、".join(f"[图{i}]" for i in image_ids)
        base += (
            f"【系统提示：本文档附带 {len(image_ids)} 张可引用图片，编号 {refs}。"
            "在回答中写出图片编号即可向用户展示对应图片，无需描述图片内容。】\n"
        )
    return base


def assemble_context(state: AgentState) -> AgentState:
    result = copy.deepcopy(state)
    docs = state.get("retrieved_docs", [])
    if not docs:
        result["context"] = ""
        result["context_doc_indices"] = []
        return result

    images_by_doc_index: dict[int, list[int]] = {}
    for img in state.get("doc_images", []):
        images_by_doc_index.setdefault(img["doc_index"], []).append(img["id"])

    parts: list[str] = []
    token_count = 0
    used_indices: list[int] = []

    for i, doc in enumerate(docs):
        formatted = _format_doc(doc, i + 1, images_by_doc_index.get(i + 1, []))
        t = count_tokens(formatted)
        if token_count + t > MAX_CONTEXT_TOKENS:
            break
        parts.append(formatted)
        token_count += t
        used_indices.append(i)

    result["context"] = "\n---\n".join(parts)
    result["context_doc_indices"] = used_indices
    return result
