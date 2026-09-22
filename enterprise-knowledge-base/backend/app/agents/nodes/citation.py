"""引用组装节点 — 校验 [编号] 标记、构建 citations 列表。

在生成节点之后运行，负责：
1. 解析 final_answer 中的 [数字] 引用标记
2. 校验每个编号是否对应真实进入上下文的文档
3. 从 retrieved_docs 提取标题/来源/链接等元数据
4. 组装 citations 列表写入 state（独立字段，不经文本清洗）
5. 确定性图片兜底：答案未引用任何 [图N] 时，为带配图的被引用文档自动插入标记
"""

import copy
import re

from app.agents.state import AgentState

_CITE_RE = re.compile(r"\[(\d+)\]")
_IMG_MARKER_RE = re.compile(r"\[图(\d+)\]")
_MAX_AUTO_IMAGES = 3


def _line_end(text: str, pos: int) -> int:
    nl = text.find("\n", pos)
    return len(text) if nl == -1 else nl


def insert_missing_image_markers(
    answer: str,
    images_by_doc_index: dict[int, list[dict]],
    cited_numbers: set[int],
) -> str:
    """答案未引用任何图片时，为带配图的被引用文档自动插入图片标记（确定性兜底）。

    每个被引用文档插入其第一张图片，插在该引用编号所在行的行尾；
    全篇最多插入 _MAX_AUTO_IMAGES 张。返回新答案。
    """
    if _IMG_MARKER_RE.search(answer):
        return answer

    text = answer
    inserted = 0
    for n in sorted(cited_numbers):
        if inserted >= _MAX_AUTO_IMAGES:
            break
        imgs = images_by_doc_index.get(n, [])
        if not imgs:
            continue
        marker = f"[图{imgs[0]['id']}]"
        if marker in text:
            continue
        cite_pos = text.find(f"[{n}]")
        if cite_pos == -1:
            continue
        line_end = _line_end(text, cite_pos)
        text = text[:line_end] + f"\n{marker}" + text[line_end:]
        inserted += 1
    return text


def citation_node(state: AgentState) -> AgentState:
    result = copy.deepcopy(state)
    answer = state.get("final_answer", "")
    docs = state.get("retrieved_docs", [])
    used_indices = state.get("context_doc_indices", [])

    if not answer or not docs or not used_indices:
        result["citations"] = []
        return result

    cited_numbers: set[int] = set()
    for m in _CITE_RE.finditer(answer):
        n = int(m.group(1))
        doc_idx = n - 1
        if doc_idx in used_indices:
            cited_numbers.add(n)

    images_by_doc_index: dict[int, list[dict]] = {}
    for img in state.get("doc_images", []):
        images_by_doc_index.setdefault(img["doc_index"], []).append(
            {
                "id": img["id"],
                "url": img["url"],
                "width": img.get("width"),
                "height": img.get("height"),
            }
        )

    citations: list[dict] = []
    for n in sorted(cited_numbers):
        doc_idx = n - 1
        doc = docs[doc_idx]
        md = doc.metadata
        citations.append({
            "index": n,
            "title": md.get("title", "未知文档"),
            "platform": md.get("source_type", "internal"),
            "url": md.get("original_url", ""),
            "source_name": md.get("source_name", ""),
            "is_internal": md.get("source_type", "internal") == "internal",
            "images": images_by_doc_index.get(n, []),
        })

    result["citations"] = citations
    result["final_answer"] = insert_missing_image_markers(answer, images_by_doc_index, cited_numbers)
    return result
