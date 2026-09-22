"""跨平台内容去重 — 内容指纹（SimHash）+ 标题相似度 + 精确哈希。

纯算法模块，无外部依赖（hashlib + difflib，均 stdlib）：
- ``content_hash``：归一化文本的 SHA-256，用于精确去重（可入库索引，等值查询）。
- ``content_fingerprint`` / ``hamming_distance``：63 位 SimHash，用于近似去重（容忍排版/少量措辞差异）。
- ``title_similarity``：标题序列相似度（difflib）。
- ``is_duplicate``：综合判定（指纹汉明距离 + 标题相似度）。
"""

import hashlib
import re
from difflib import SequenceMatcher

_SIMHASH_BITS = 63  # 取 63 位保证指纹为非负整数，安全存入有符号 BIGINT（MySQL/SQLite）
_NORM_RE = re.compile(r"[\W_]+", re.UNICODE)


def normalize_text(text: str) -> str:
    """归一化：去除空白与标点（保留中英文/数字），忽略大小写。

    跨平台同一文章常在排版标点上存在差异，去重时视为等价。
    """
    return _NORM_RE.sub("", text or "").lower()


def content_hash(text: str) -> str:
    """归一化文本的 SHA-256 十六进制摘要（精确去重键）。"""
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def _tokenize(text: str) -> list[str]:
    """字符级 3-gram 分词（对中文友好，无需分词器）。"""
    norm = normalize_text(text)
    if len(norm) < 3:
        return [norm] if norm else []
    return [norm[i : i + 3] for i in range(len(norm) - 2)]


def _hash64(token: str) -> int:
    digest = hashlib.md5(token.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def content_fingerprint(text: str, bits: int = _SIMHASH_BITS) -> int:
    """SimHash 指纹：将文本映射为 bits 位整数，相似文本汉明距离小。"""
    tokens = _tokenize(text)
    if not tokens:
        return 0
    weights = [0] * bits
    for token in tokens:
        h = _hash64(token)
        for i in range(bits):
            if h & (1 << i):
                weights[i] += 1
            else:
                weights[i] -= 1
    fingerprint = 0
    for i in range(bits):
        if weights[i] > 0:
            fingerprint |= 1 << i
    return fingerprint


def hamming_distance(a: int, b: int) -> int:
    """两个整数的汉明距离（不同比特数）。"""
    return bin(a ^ b).count("1")


def content_similar(text_a: str, text_b: str, threshold: int = 3) -> bool:
    """SimHash 汉明距离 ≤ threshold 视为内容近似（63 位经验阈值 3）。"""
    if not text_a or not text_b:
        return False
    return hamming_distance(content_fingerprint(text_a), content_fingerprint(text_b)) <= threshold


def title_similarity(title_a: str, title_b: str) -> float:
    """标题相似度（0~1），去空白忽略大小写后按序列匹配。"""
    if not title_a or not title_b:
        return 0.0
    return SequenceMatcher(None, normalize_text(title_a), normalize_text(title_b)).ratio()


def is_duplicate(
    title_a: str,
    text_a: str,
    title_b: str,
    text_b: str,
    *,
    hamming_threshold: int = 3,
    title_threshold: float = 0.85,
) -> bool:
    """综合判定两篇文章是否重复。

    规则：
    1. 内容指纹汉明距离 ≤ hamming_threshold → 判定重复（强内容匹配）。
    2. 否则，标题相似度 ≥ title_threshold 且汉明距离 ≤ 2*hamming_threshold → 判定重复
       （标题高度一致 + 内容较接近，容忍跨平台排版差异）。
    """
    if not text_a or not text_b:
        return False
    distance = hamming_distance(content_fingerprint(text_a), content_fingerprint(text_b))
    if distance <= hamming_threshold:
        return True
    return title_similarity(title_a, title_b) >= title_threshold and distance <= hamming_threshold * 2
