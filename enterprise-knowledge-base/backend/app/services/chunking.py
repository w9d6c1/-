"""文档分块策略 — LangChain RecursiveCharacterTextSplitter + BGE tokenizer

chunk_size / chunk_overlap 以 tokens 为单位（非字符），默认 512/80，
确保每个 chunk 完整被 BGE embedding 模型处理（max_length=512）。
"""

_TOKENIZER = None
_SPLITTERS: dict[tuple[int, int], "RecursiveCharacterTextSplitter"] = {}


def _get_tokenizer():
    global _TOKENIZER
    if _TOKENIZER is None:
        import os

        from transformers import AutoTokenizer

        model_path = os.environ.get(
            "TOKENIZER_PATH",
            "/app/models/BAAI/bge-large-zh-v1.5",
        )
        _TOKENIZER = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
    return _TOKENIZER


def _get_splitter(chunk_size: int, chunk_overlap: int) -> "RecursiveCharacterTextSplitter":
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    key = (chunk_size, chunk_overlap)
    if key not in _SPLITTERS:
        separators = ["\n\n", "\n", "。", ".", "？", "?", "！", "!", "；", ";", "，", ",", " ", ""]
        try:
            tokenizer = _get_tokenizer()
            splitter = RecursiveCharacterTextSplitter.from_huggingface_tokenizer(
                tokenizer,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                separators=separators,
                keep_separator=True,
                strip_whitespace=True,
            )
        except Exception:
            # BGE tokenizer 不可用（/app/models 未挂载）时回退字符级切分，中文近似 1 字 ≈ 1 token
            from app.core.logging import logger

            logger.warning("chunk_tokenizer_unavailable_fallback_to_chars")
            splitter = RecursiveCharacterTextSplitter(
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                separators=separators,
                keep_separator=True,
                strip_whitespace=True,
            )
        _SPLITTERS[key] = splitter
    return _SPLITTERS[key]


def chunk_fixed(content: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """固定 token 级切分（无语义边界）"""
    splitter = _get_splitter(chunk_size, chunk_overlap)
    original = splitter._separators
    try:
        splitter._separators = [""]
        splitter._is_separator_regex = False
        return splitter.split_text(content)
    finally:
        splitter._separators = original


def chunk_recursive(content: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """递归语义切分 — 按分隔符优先级拆分，合并短块"""
    splitter = _get_splitter(chunk_size, chunk_overlap)
    chunks = splitter.split_text(content)
    return _remove_short_tail(chunks, chunk_overlap)


def chunk_semantic(content: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """Markdown 标题切分 + 递归切分 — 保留章节结构"""
    import re

    from langchain_text_splitters import MarkdownHeaderTextSplitter

    headers_to_split_on = [
        ("#", "H1"),
        ("##", "H2"),
        ("###", "H3"),
    ]
    markdown_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=headers_to_split_on, strip_headers=False
    )
    md_docs = markdown_splitter.split_text(content)

    if len(md_docs) <= 1:
        return chunk_recursive(content, chunk_size, chunk_overlap)

    recursive_splitter = _get_splitter(chunk_size, chunk_overlap)
    chunks: list[str] = []
    for doc in md_docs:
        section_chunks = recursive_splitter.split_text(doc.page_content)
        chunks.extend(section_chunks)
    return _remove_short_tail(chunks, chunk_overlap)


def _remove_short_tail(chunks: list[str], overlap: int) -> list[str]:
    if len(chunks) >= 2 and len(chunks[-1]) < max(1, overlap // 2):
        return chunks[:-1]
    return chunks


def chunk_content(content: str, strategy: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    if not content or not content.strip():
        return []
    if strategy == "fixed":
        return chunk_fixed(content, chunk_size, chunk_overlap)
    elif strategy == "semantic":
        return chunk_semantic(content, chunk_size, chunk_overlap)
    else:
        return chunk_recursive(content, chunk_size, chunk_overlap)
