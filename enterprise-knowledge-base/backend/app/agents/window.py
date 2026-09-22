"""上下文窗口管理 — Token 计数 + 截断"""

from langchain_core.messages import BaseMessage, HumanMessage

from app.agents.llm import count_tokens


def count_message_tokens(message: BaseMessage) -> int:
    content = str(message.content) if hasattr(message, "content") else ""
    return count_tokens(content)


def trim_history(
    messages: list[BaseMessage],
    max_tokens: int = 4000,
) -> list[BaseMessage]:
    """按 token 预算保留**最近**的历史消息。

    从最新往回累加至预算；最后一条（当前问题）即使超预算也保留；
    截断后丢弃开头的非 Human 消息，保证对话以用户提问起始。
    """
    if not messages:
        return []

    kept: list[BaseMessage] = []
    kept_tokens = 0
    for msg in reversed(messages):
        tc = count_message_tokens(msg)
        if kept and kept_tokens + tc > max_tokens:
            break
        kept.append(msg)
        kept_tokens += tc

    kept.reverse()
    while kept and not isinstance(kept[0], HumanMessage):
        kept.pop(0)
    return kept
