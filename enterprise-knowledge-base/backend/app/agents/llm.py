"""LLM 统一调用封装 — DeepSeek via langchain-openai"""

import asyncio
import re
from typing import Iterator

from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

from app.core.config import settings
from app.core.logging import logger


class LLMConfig:
    def __init__(self, api_key: str, provider: str, model: str, base_url: str):
        self.api_key = api_key
        self.provider = provider
        self.model = model
        self.base_url = base_url


def create_llm_config() -> LLMConfig:
    return LLMConfig(
        api_key=settings.llm_api_key,
        provider=settings.llm_provider,
        model=settings.llm_model,
        base_url=settings.llm_base_url,
    )


def _validate_api_key(api_key: str) -> None:
    if not api_key or api_key == "your-api-key-here":
        raise ValueError("LLM_API_KEY not configured")


def create_llm(
    temperature: float = 0.0,
    max_tokens: int = 2048,
    top_p: float | None = None,
    api_key: str | None = None,
) -> BaseChatModel:
    key = api_key or settings.llm_api_key
    _validate_api_key(key)
    top_p_value = top_p if top_p is not None else settings.llm_top_p
    return ChatOpenAI(
        model=settings.llm_model,
        api_key=key,
        base_url=settings.llm_base_url,
        temperature=temperature,
        max_tokens=max_tokens,
        model_kwargs={"top_p": top_p_value},
        timeout=30,
        request_timeout=30,
    )


def clean_response(text: str) -> str:
    """清洗 LLM 输出：删除 Markdown 符号和思考过程，保留加粗和序号层次"""
    if not text or not text.strip():
        return text

    text = text.replace("\r\n", "\n")

    # 1. 删除 <think>...</think> 思考块（含未闭合）
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<think>.*", "", text, flags=re.DOTALL | re.IGNORECASE)

    # 2. 删除 </think> /  等残留标签
    text = re.sub(r"</?\s*(think|response)\s*>", "", text, flags=re.IGNORECASE)

    # 3. 删除开头机械开场白
    text = re.sub(
        r"^\s*(好的[，,]?\s*)?(让我们?来?|我来?)(分析|思考|说明|介绍)一下[：:：]?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"^\s*(首先|第一步)[，,]\s*(我(来|们来)?)?(分析|思考|说明|介绍)[：:：]?\s*",
        "",
        text,
        flags=re.IGNORECASE,
    )

    # 4. 逐行清除行首 Markdown 符号（保留 1./2. 序号和 **加粗**）
    lines: list[str] = []
    for line in text.split("\n"):
        stripped = line.lstrip()
        leading = line[: len(line) - len(stripped)] if stripped else line
        if not stripped:
            lines.append(line)
            continue
        cleaned = re.sub(r"^#{1,6}\s+", "", stripped)
        cleaned = re.sub(r"^>\s+", "", cleaned)
        cleaned = re.sub(r"^[-*]\s+", "", cleaned)
        lines.append(leading + cleaned)
    text = "\n".join(lines)

    # 5. 删除代码块 ```...```
    text = re.sub(r"```[\s\S]*?```", "", text)

    # 6. 删除独立分割线行
    text = re.sub(r"^\s*[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)

    # 7. 删除连续长破折号 / 下划线
    text = re.sub(r"[—]{3,}", "", text)
    text = re.sub(r"[_]{3,}", "", text)

    # 8. 压缩多余空行（3+ → 2）
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


def count_tokens(text: str, model: str = "gpt-3.5-turbo") -> int:
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
    except Exception:
        return len(text) // 2
    return len(enc.encode(text))


async def call_llm_with_retry(
    llm: BaseChatModel,
    messages: list,
    max_retries: int = 3,
    clean: bool = False,
) -> str:
    last_error: Exception | None = None
    for i in range(max_retries):
        try:
            result = await llm.ainvoke(messages)
            content = str(result.content)
            if clean:
                content = clean_response(content)
            return content
        except Exception as e:
            last_error = e
            logger.warning("llm_retry_attempt", attempt=i + 1, max_retries=max_retries, error=str(e))
            if i < max_retries - 1:
                delay = min(1000 * (2 ** i), 8000) / 1000
                await asyncio.sleep(delay)
    raise RuntimeError(f"LLM call failed after {max_retries} retries") from last_error


async def acall_llm_with_retry(
    llm: BaseChatModel,
    messages: list,
    max_retries: int = 3,
    clean: bool = False,
) -> str:
    last_error: Exception | None = None
    for i in range(max_retries):
        try:
            result = await llm.ainvoke(messages)
            content = str(result.content)
            if clean:
                content = clean_response(content)
            return content
        except Exception as e:
            last_error = e
            if i < max_retries - 1:
                delay = min(1000 * (2 ** i), 8000) / 1000
                await asyncio.sleep(delay)
    raise RuntimeError(f"LLM call failed after {max_retries} retries") from last_error


def stream_with_callback(
    llm: BaseChatModel,
    messages: list,
) -> Iterator[str]:
    for chunk in llm.stream(messages):
        if chunk.content:
            yield str(chunk.content)
